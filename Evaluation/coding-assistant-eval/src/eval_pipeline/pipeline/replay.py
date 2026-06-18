"""Replay pipeline: run prompts against the candidate model to generate new outputs."""

from __future__ import annotations

import asyncio

import anthropic

from eval_pipeline.config import get_settings
from eval_pipeline.logging import get_logger
from eval_pipeline.models import LogEntry

logger = get_logger(__name__)
settings = get_settings()


class ReplayPipeline:
    """Generates candidate model outputs for a batch of log entries.

    Old model outputs already exist in the logs -- only the new model needs to run.
    This halves compute cost vs re-running both models from scratch.
    """

    def __init__(self, model: str | None = None, concurrency: int = 5) -> None:
        self._model = model or settings.candidate_model
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._sem = asyncio.Semaphore(concurrency)

    async def generate(self, entry: LogEntry) -> str:
        async with self._sem:
            try:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": entry.prompt}],
                )
                return response.content[0].text
            except Exception as exc:
                logger.warning("replay_failed", entry_id=entry.id, error=str(exc))
                return ""

    async def generate_batch(self, entries: list[LogEntry]) -> dict[str, str]:
        """Returns {entry_id: new_output} for all entries."""
        tasks = [self.generate(entry) for entry in entries]
        results = await asyncio.gather(*tasks)
        return {entry.id: output for entry, output in zip(entries, results)}
