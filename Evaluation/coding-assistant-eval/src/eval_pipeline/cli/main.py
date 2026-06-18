"""CLI runner for the eval pipeline."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from eval_pipeline.config import get_settings
from eval_pipeline.dataset.loader import iter_log_entries
from eval_pipeline.logging import configure_logging
from eval_pipeline.models import EvalRun
from eval_pipeline.pipeline.orchestrator import EvalOrchestrator
from eval_pipeline.storage.postgres import create_tables

app = typer.Typer(help="Coding assistant eval pipeline CLI")
console = Console()
settings = get_settings()


@app.command()
def run(
    baseline: str = typer.Option(..., help="Baseline model name (used for labelling)"),
    candidate: str = typer.Option(
        default=None, help="Candidate model to evaluate (defaults to config)"
    ),
    suite: str = typer.Option(default="default", help="Suite name for the registry"),
    per_task: int = typer.Option(default=50, help="Entries per task type"),
) -> None:
    """Run a full eval comparing baseline vs candidate model."""
    configure_logging(settings.log_level)

    async def _run() -> None:
        await create_tables()
        entries = [e async for e in iter_log_entries()]

        if not entries:
            console.print("[yellow]No log entries found. Seed the database first.[/yellow]")
            raise typer.Exit(1)

        eval_run = EvalRun(
            suite_name=suite,
            baseline_model=baseline,
            candidate_model=candidate or settings.candidate_model,
        )

        orchestrator = EvalOrchestrator(candidate_model=candidate)
        result = await orchestrator.run(eval_run, entries, per_task_type=per_task)

        if result.summary:
            _print_scorecard(result)
        else:
            console.print(f"[red]Run failed: {result.error}[/red]")
            raise typer.Exit(1)

    asyncio.run(_run())


def _print_scorecard(run: EvalRun) -> None:
    s = run.summary
    assert s is not None

    decision_color = {"ship": "green", "hold": "red", "review": "yellow"}[s.ship_decision.value]

    console.print(f"\n[bold]Eval Run[/bold]: {run.id}")
    console.print(f"  Baseline:  {run.baseline_model}")
    console.print(f"  Candidate: {run.candidate_model}")
    console.print(f"  Decision:  [{decision_color}]{s.ship_decision.value.upper()}[/{decision_color}]")

    for reason in s.decision_reasons:
        console.print(f"    - {reason}")

    table = Table(title="Scorecard", show_header=True)
    table.add_column("Task Type")
    table.add_column("Baseline", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Delta", justify="right")

    def _delta_str(old: float, new: float) -> str:
        d = new - old
        color = "green" if d >= 0 else "red"
        return f"[{color}]{d:+.1%}[/{color}]"

    table.add_row(
        "Code Generation (pass rate)",
        f"{s.code_gen_old_pass_rate:.1%}",
        f"{s.code_gen_new_pass_rate:.1%}",
        _delta_str(s.code_gen_old_pass_rate, s.code_gen_new_pass_rate),
    )
    table.add_row(
        "Bug Fixing (pass rate)",
        f"{s.bug_fix_old_pass_rate:.1%}",
        f"{s.bug_fix_new_pass_rate:.1%}",
        _delta_str(s.bug_fix_old_pass_rate, s.bug_fix_new_pass_rate),
    )
    table.add_row(
        "Code Explanation (judge score)",
        f"{s.explanation_old_score:.3f}",
        f"{s.explanation_new_score:.3f}",
        _delta_str(s.explanation_old_score, s.explanation_new_score),
    )

    console.print(table)
    console.print(f"\n  Total entries: {s.total_entries}")
    console.print(f"  Filtered by similarity: {s.filtered_by_similarity} ({s.filtered_by_similarity / max(s.total_entries, 1):.0%})")
    console.print(f"  Regressions: {s.regression_count}  |  Improvements: {s.improvement_count}")
    console.print(f"  Weighted regression score: {s.weighted_regression_score:.2f}\n")
