"""Drop-in LangGraph middleware.

Wraps a compiled LangGraph graph and intercepts each step to run all
detection layers. Injects corrections, triggers summarization, or creates
human checkpoints based on the detection result.

Usage:
    from loop_detector.middleware.langgraph import LoopDetectionMiddleware, LoopDetectorConfig

    graph = StateGraph(MyState)
    # ... add nodes and edges ...
    compiled = graph.compile()

    protected = LoopDetectionMiddleware(compiled, config=LoopDetectorConfig())
    result = await protected.ainvoke(initial_state, config={...})
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from loop_detector.config import get_settings
from loop_detector.detector.budget import BudgetTracker
from loop_detector.detector.causal import CausalLoopDetector
from loop_detector.detector.fingerprint import FingerprintDetector, make_fingerprint
from loop_detector.detector.progress import ProgressTracker
from loop_detector.detector.semantic import SemanticDetector
from loop_detector.logging import get_logger
from loop_detector.metrics import loop_detections_total, recovery_actions_total
from loop_detector.models import (
    AgentStep,
    DetectionResult,
    LoopSignal,
    RecoveryStrategy,
    SessionStats,
)
from loop_detector.monitor.agent import MonitoringAgent
from loop_detector.recovery.checkpoint import create_human_checkpoint
from loop_detector.recovery.injection import build_correction_message
from loop_detector.recovery.summarizer import force_summarize
from loop_detector.storage.redis_client import get_redis

settings = get_settings()
logger = get_logger(__name__)


@dataclass
class LoopDetectorConfig:
    fingerprint_window: int = 10
    semantic_threshold: float = 0.92
    semantic_window: int = 5
    max_steps: int = 50
    max_tokens: int = 100_000
    progress_window: int = 5
    progress_novelty_threshold: float = 0.05
    consecutive_detections_for_checkpoint: int = 3
    enable_causal: bool = True
    enable_monitoring: bool = True
    goal: str = "Complete the assigned task"


class LoopDetectionMiddleware:
    """Wraps a compiled LangGraph graph with loop detection on every step."""

    def __init__(self, graph: Any, config: LoopDetectorConfig | None = None) -> None:
        self._graph = graph
        self._config = config or LoopDetectorConfig()

    async def ainvoke(
        self,
        state: dict,
        config: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        session_id = (
            (config or {}).get("configurable", {}).get("thread_id", "unknown")
        )

        ctx = _SessionContext(session_id=session_id, cfg=self._config)

        if self._config.enable_monitoring:
            await ctx.monitor.start()

        try:
            result = await self._run_with_detection(state, config, ctx, **kwargs)
        finally:
            if self._config.enable_monitoring:
                await ctx.monitor.stop()

        await ctx.persist_stats()
        return result

    async def _run_with_detection(
        self,
        initial_state: dict,
        config: dict | None,
        ctx: "_SessionContext",
        **kwargs: Any,
    ) -> dict:
        state = dict(initial_state)

        async for event in self._graph.astream(state, config=config, **kwargs):
            for node_name, node_output in event.items():
                if node_name == "__end__":
                    return node_output if isinstance(node_output, dict) else state

                step_result = await self._process_step(
                    node_name=node_name,
                    node_output=node_output,
                    state=state,
                    ctx=ctx,
                )

                if step_result is None:
                    # Forced summarization triggered
                    return state

                if step_result.get("__inject_correction__"):
                    correction = step_result.pop("__inject_correction__")
                    if "messages" in state and isinstance(state["messages"], list):
                        from langchain_core.messages import SystemMessage
                        state["messages"] = state["messages"] + [SystemMessage(content=correction)]
                    logger.info("correction_injected", session_id=ctx.session_id)
                else:
                    state.update(node_output)

        return state

    async def _process_step(
        self,
        node_name: str,
        node_output: dict,
        state: dict,
        ctx: "_SessionContext",
    ) -> dict | None:
        tool_name = node_output.get("tool_name") or node_name
        tool_args = node_output.get("tool_args") or {}
        observation = str(node_output.get("observation") or node_output)
        tokens = int(node_output.get("tokens_used") or 0)

        ctx.stats.total_steps += 1
        ctx.stats.total_tokens += tokens

        args_hash = make_fingerprint(tool_name, tool_args)
        step = AgentStep(
            step=ctx.stats.total_steps,
            tool_name=tool_name,
            tool_args=tool_args,
            args_hash=args_hash,
            observation=observation,
            tokens_used=tokens,
        )
        ctx.steps.append(step)

        signals: list[LoopSignal] = []

        # Layer 2: fingerprint
        fp_signal = ctx.fingerprint.check(step, ctx.session_id)
        if fp_signal:
            signals.append(fp_signal)

        # Layer 3: semantic
        sem_signal = await ctx.semantic.check(step, ctx.session_id)
        if sem_signal:
            signals.append(sem_signal)

        # Layer 4: budget
        budget_signal = ctx.budget.tick(step, ctx.session_id)
        if budget_signal:
            signals.append(budget_signal)

        # Layer 5: progress
        prog_signal = ctx.progress.check(step, ctx.session_id)
        if prog_signal:
            signals.append(prog_signal)

        # Layer 6 (causal, optional)
        if self._config.enable_causal:
            causal_signal = ctx.causal.check(step, ctx.session_id)
            if causal_signal:
                signals.append(causal_signal)

        # Layer 6 (monitoring agent signals)
        monitor_signals = ctx.monitor.pop_signals()
        signals.extend(monitor_signals)

        if not signals:
            ctx.stats.consecutive_detections = 0
            return node_output

        ctx.stats.loop_signals += len(signals)
        ctx.stats.consecutive_detections += 1
        loop_detections_total.labels(signal_type=signals[-1].signal_type.value).inc()

        detection = DetectionResult(
            is_looping=True,
            signals=signals,
            consecutive_detections=ctx.stats.consecutive_detections,
            step=ctx.stats.total_steps,
        )
        detection.recommended_strategy = _pick_strategy(detection, self._config)
        ctx.stats.recovery_strategy = detection.recommended_strategy

        logger.warning(
            "loop_detected",
            session_id=ctx.session_id,
            step=ctx.stats.total_steps,
            strategy=detection.recommended_strategy,
            signals=[s.signal_type.value for s in signals],
        )

        await _persist_signals(ctx.session_id, signals)

        strategy = detection.recommended_strategy
        recovery_actions_total.labels(strategy=strategy.value if strategy else "none").inc()

        if strategy == RecoveryStrategy.HUMAN_CHECKPOINT:
            await create_human_checkpoint(
                session_id=ctx.session_id,
                step=ctx.stats.total_steps,
                result=detection,
                steps=ctx.steps,
                full_state=state,
            )
            return node_output

        if strategy == RecoveryStrategy.FORCE_SUMMARIZE:
            summary = await force_summarize(
                session_id=ctx.session_id,
                goal=self._config.goal,
                steps=ctx.steps,
                result=detection,
            )
            state["final_summary"] = summary
            return None

        # Default: inject correction
        correction = build_correction_message(detection)
        return {"__inject_correction__": correction}


def _pick_strategy(result: DetectionResult, cfg: LoopDetectorConfig) -> RecoveryStrategy:
    from loop_detector.models import LoopSignalType

    if result.consecutive_detections >= cfg.consecutive_detections_for_checkpoint:
        return RecoveryStrategy.HUMAN_CHECKPOINT

    for signal in result.signals:
        if signal.signal_type == LoopSignalType.BUDGET_EXHAUSTED:
            return RecoveryStrategy.FORCE_SUMMARIZE

    return RecoveryStrategy.INJECT_CORRECTION


async def _persist_signals(session_id: str, signals: list[LoopSignal]) -> None:
    try:
        from loop_detector.storage.postgres import AsyncSessionFactory, LoopSignalORM

        async with AsyncSessionFactory() as session:
            for sig in signals:
                orm = LoopSignalORM(
                    id=sig.id,
                    session_id=session_id,
                    signal_type=sig.signal_type.value,
                    step=sig.step,
                    tool_name=sig.tool_name,
                    tool_args_hash=sig.tool_args_hash,
                    similarity_score=sig.similarity_score,
                    message=sig.message,
                    metadata_=sig.metadata,
                )
                session.add(orm)
            await session.commit()
    except Exception:
        logger.exception("signal_persist_failed", session_id=session_id)


@dataclass
class _SessionContext:
    session_id: str
    cfg: LoopDetectorConfig
    stats: SessionStats = field(init=False)
    steps: list[AgentStep] = field(default_factory=list)
    fingerprint: FingerprintDetector = field(init=False)
    semantic: SemanticDetector = field(init=False)
    budget: BudgetTracker = field(init=False)
    progress: ProgressTracker = field(init=False)
    causal: CausalLoopDetector = field(init=False)
    monitor: MonitoringAgent = field(init=False)

    def __post_init__(self) -> None:
        self.stats = SessionStats(session_id=self.session_id)
        self.fingerprint = FingerprintDetector(window=self.cfg.fingerprint_window)
        self.semantic = SemanticDetector(
            window=self.cfg.semantic_window,
            threshold=self.cfg.semantic_threshold,
        )
        self.budget = BudgetTracker(
            max_steps=self.cfg.max_steps,
            max_tokens=self.cfg.max_tokens,
        )
        self.progress = ProgressTracker(
            window=self.cfg.progress_window,
            threshold=self.cfg.progress_novelty_threshold,
        )
        self.causal = CausalLoopDetector()
        self.monitor = MonitoringAgent()

    async def persist_stats(self) -> None:
        try:
            from loop_detector.storage.postgres import AsyncSessionFactory, SessionStatsORM
            from datetime import datetime, timezone

            async with AsyncSessionFactory() as session:
                orm = SessionStatsORM(
                    session_id=self.session_id,
                    total_steps=self.stats.total_steps,
                    total_tokens=self.stats.total_tokens,
                    loop_signals=self.stats.loop_signals,
                    recovery_strategy=self.stats.recovery_strategy.value if self.stats.recovery_strategy else None,
                    last_active=datetime.now(timezone.utc),
                )
                session.add(orm)
                await session.commit()
        except Exception:
            logger.exception("stats_persist_failed", session_id=self.session_id)
