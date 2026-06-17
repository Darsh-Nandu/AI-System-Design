"""Layer 6: Monitoring agent (separate asyncio task).

Watches tool execution in real time. Unlike the other layers which run
synchronously per step, this runs as a background process and can
interrupt a stuck tool call mid-execution.

On detecting a stall, it sends a structured error message back to the
main agent context -- not a silent kill.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loop_detector.logging import get_logger
from loop_detector.metrics import monitor_timeouts_total
from loop_detector.models import LoopSignal, LoopSignalType, ToolExecution

logger = get_logger(__name__)


class ToolExecutionContext:
    """Thread-safe context for a single running tool call."""

    def __init__(self, tool_name: str, args: dict, timeout_seconds: float) -> None:
        self.execution = ToolExecution(tool_name=tool_name, args=args)
        self.timeout_seconds = timeout_seconds
        self._cancel_event = asyncio.Event()
        self._done_event = asyncio.Event()

    def complete(self, result: str) -> None:
        self.execution.result = result
        self.execution.finished_at = datetime.now(timezone.utc)
        self._done_event.set()

    def fail(self, error: str) -> None:
        self.execution.error = error
        self.execution.finished_at = datetime.now(timezone.utc)
        self._done_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def is_done(self) -> bool:
        return self._done_event.is_set()


class MonitoringAgent:
    """Background agent that watches active tool executions for stalls."""

    def __init__(self, poll_interval: float = 5.0) -> None:
        self._poll_interval = poll_interval
        self._active: dict[str, ToolExecutionContext] = {}
        self._signals: list[LoopSignal] = []
        self._running = False
        self._task: asyncio.Task | None = None

    def register(self, exec_id: str, ctx: ToolExecutionContext) -> None:
        self._active[exec_id] = ctx

    def complete(self, exec_id: str, result: str) -> None:
        if exec_id in self._active:
            self._active[exec_id].complete(result)
            del self._active[exec_id]

    def fail(self, exec_id: str, error: str) -> None:
        if exec_id in self._active:
            self._active[exec_id].fail(error)
            del self._active[exec_id]

    def pop_signals(self) -> list[LoopSignal]:
        signals = list(self._signals)
        self._signals.clear()
        return signals

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("monitoring_agent_started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("monitoring_agent_stopped")

    async def _watch_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._poll_interval)
            now = datetime.now(timezone.utc)
            stalled: list[str] = []

            for exec_id, ctx in list(self._active.items()):
                if ctx.is_done:
                    stalled.append(exec_id)
                    continue

                elapsed = (now - ctx.execution.started_at).total_seconds()
                if elapsed > ctx.timeout_seconds:
                    logger.warning(
                        "tool_timeout_detected",
                        exec_id=exec_id,
                        tool=ctx.execution.tool_name,
                        elapsed_s=elapsed,
                        timeout_s=ctx.timeout_seconds,
                    )
                    monitor_timeouts_total.inc()
                    ctx.execution.timed_out = True
                    ctx.cancel()

                    self._signals.append(LoopSignal(
                        session_id=exec_id.split(":")[0],
                        signal_type=LoopSignalType.TOOL_TIMEOUT,
                        step=-1,
                        tool_name=ctx.execution.tool_name,
                        message=(
                            f"Tool '{ctx.execution.tool_name}' stalled: "
                            f"{elapsed:.1f}s elapsed, timeout was {ctx.timeout_seconds:.1f}s. "
                            "The tool may be waiting on a hung external service. "
                            "Consider using an alternative tool or retrying with a smaller input."
                        ),
                        metadata={
                            "elapsed_s": elapsed,
                            "timeout_s": ctx.timeout_seconds,
                        },
                    ))
                    stalled.append(exec_id)

            for exec_id in stalled:
                self._active.pop(exec_id, None)
