"""Run a full eval comparing two models using seeded sample logs."""

from __future__ import annotations

import asyncio
import sys

from rich.console import Console

from eval_pipeline.dataset.loader import iter_log_entries
from eval_pipeline.logging import configure_logging
from eval_pipeline.models import EvalRun
from eval_pipeline.pipeline.orchestrator import EvalOrchestrator
from eval_pipeline.storage.postgres import create_tables

configure_logging()
console = Console()


async def _run(baseline: str, candidate: str) -> None:
    await create_tables()

    entries = [e async for e in iter_log_entries()]
    if not entries:
        console.print("[yellow]No entries found. Run seed_logs.py first.[/yellow]")
        sys.exit(1)

    run = EvalRun(
        suite_name="demo",
        baseline_model=baseline,
        candidate_model=candidate,
    )

    orchestrator = EvalOrchestrator(candidate_model=candidate)
    result = await orchestrator.run(run, entries, per_task_type=10)

    if result.summary:
        s = result.summary
        console.print(f"\n[bold]Decision: {s.ship_decision.value.upper()}[/bold]")
        for reason in s.decision_reasons:
            console.print(f"  - {reason}")
        console.print(f"\n  Code gen: {s.code_gen_old_pass_rate:.1%} -> {s.code_gen_new_pass_rate:.1%}")
        console.print(f"  Bug fix:  {s.bug_fix_old_pass_rate:.1%} -> {s.bug_fix_new_pass_rate:.1%}")
        console.print(f"  Explain:  {s.explanation_old_score:.3f} -> {s.explanation_new_score:.3f}")
    else:
        console.print(f"[red]Run failed: {result.error}[/red]")


def main() -> None:
    baseline = sys.argv[1] if len(sys.argv) > 1 else "gpt-4-0613"
    candidate = sys.argv[2] if len(sys.argv) > 2 else "claude-sonnet-4-6"
    asyncio.run(_run(baseline, candidate))


if __name__ == "__main__":
    main()
