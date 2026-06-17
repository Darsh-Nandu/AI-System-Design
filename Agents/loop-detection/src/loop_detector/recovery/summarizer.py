"""Recovery Strategy 2: Forced summarization.

When the step or token budget is exhausted, the agent is forced to call
summarize_and_halt instead of being silently killed.
This preserves the reasoning state and gives the user a useful partial result.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic

from loop_detector.config import get_settings
from loop_detector.logging import get_logger
from loop_detector.models import AgentStep, DetectionResult

settings = get_settings()
logger = get_logger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_SUMMARIZE_SYSTEM = """You are summarising the progress of an AI agent that ran out of its step budget.
Your job is to produce a clear, useful summary for the user that includes:
1. What the agent was trying to accomplish
2. What steps it successfully completed
3. What it tried but failed at, and why
4. What information is still missing to complete the task
5. A recommended next action for the user

Be direct and honest. Do not speculate beyond what is in the step history."""


async def force_summarize(
    session_id: str,
    goal: str,
    steps: list[AgentStep],
    result: DetectionResult,
) -> str:
    """Ask Claude to summarize the agent's progress before halting."""
    logger.info(
        "forced_summarization",
        session_id=session_id,
        total_steps=len(steps),
        budget_signal=result.signals[-1].signal_type if result.signals else "unknown",
    )

    step_log = "\n".join(
        f"Step {s.step}: {s.tool_name}({_truncate(str(s.tool_args), 100)}) -> {_truncate(s.observation, 200)}"
        for s in steps[-20:]  # send last 20 steps to stay within token limits
    )

    content = (
        f"Task goal: {goal}\n\n"
        f"Budget exhaustion signal: {result.signals[-1].message if result.signals else 'budget exceeded'}\n\n"
        f"Recent step history (last {min(len(steps), 20)} steps):\n{step_log}"
    )

    response = await _client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=_SUMMARIZE_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )

    summary = response.content[0].text.strip()
    logger.info("summarization_complete", session_id=session_id)
    return summary


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
