"""Stress test orchestrator with remote/local modes and CSV output.

Executes multi-turn scenarios with configurable:
  - Scenarios: growth, pivot, contradiction, all
  - Attachment sizes: 0, 5, 20, 50, 100 KB
  - Repeats: N runs per scenario+attachment combination
    - Resume mode: skip scenario+size+repeat batches already complete in CSV

Modes:
  - --http URL: Use httpx to call remote API (e.g., http://localhost:8000)
  - In-process: Use TestClient + services directly (default)

Output: CSV with columns:
  scenario, attachment_size, repeat, turn_number, latency_ms, cost_usd, 
  input_tokens, output_tokens, semantic_cache_hit, llm_cache_hit, fact_recall,
  project_name, mentioned_technologies, team_size, agreed_scope
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Literal

import click

if __name__ == "__main__":
    # Ensure ai-engine is importable
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

log = logging.getLogger(__name__)


class StressTestRunner:
    """Orchestrate stress tests with multiple scenarios, attachment sizes, and repeats."""

    def __init__(
        self,
        http_url: str | None = None,
        verbose: bool = False,
    ):
        """Initialize runner.

        Args:
            http_url: If provided, use httpx to call this URL. Otherwise use TestClient.
            verbose: Show detailed output.
        """
        self.http_url = http_url
        self.verbose = verbose
        self.csv_rows: list[dict] = []

    async def run(
        self,
        scenarios: list[str],
        attachment_sizes: list[int],
        repeats: int,
        output_path: str | None = None,
        resume: bool = True,
    ) -> int:
        """Execute all scenario combinations and generate CSV.

        Args:
            scenarios: List of scenario names (growth, pivot, contradiction).
            attachment_sizes: List of attachment sizes in KB (0, 5, 20, 50, 100).
            repeats: Number of times to repeat each scenario+attachment combination.
            output_path: Path to write CSV results. If None, print to stdout.
            resume: If True and output CSV exists, skip already completed batches.

        Returns:
            Exit code (0 for success).
        """
        from tests.stress.scenarios import (
            MultiTurnScenarioEvaluator,
            ProjectContradictionScenario,
            ProjectGrowthScenario,
            ProjectPivotScenario,
            ScenarioConfig,
        )

        scenario_map = {
            "growth": ProjectGrowthScenario,
            "pivot": ProjectPivotScenario,
            "contradiction": ProjectContradictionScenario,
        }

        # Create evaluator (in-process or http-based)
        evaluator = await self._create_evaluator()

        total_runs = len(scenarios) * len(attachment_sizes) * repeats
        current_run = 0
        turn_counts = [1, 3, 6, 10, 20]
        expected_turns = set(turn_counts)
        completed_batches: set[tuple[str, int, int]] = set()
        existing_row_count = 0

        try:
            if output_path:
                output_exists = Path(output_path).exists()
                if resume and output_exists:
                    completed_batches, existing_row_count = self._load_completed_batches(
                        output_path=output_path,
                        expected_turns=expected_turns,
                    )
                    click.echo(
                        f"  Resume: {len(completed_batches)} completed batches, "
                        f"{existing_row_count} existing rows",
                        err=True,
                    )
                else:
                    self._initialize_csv_file(output_path)

            for scenario_name in scenarios:
                if scenario_name not in scenario_map:
                    click.echo(
                        f"⚠ Unknown scenario: {scenario_name}", err=True
                    )
                    continue

                scenario_class = scenario_map[scenario_name]

                for attachment_size_kb in attachment_sizes:
                    for repeat_idx in range(1, repeats + 1):
                        current_run += 1
                        progress = f"[{current_run}/{total_runs}]"
                        batch_key = (scenario_name, attachment_size_kb, repeat_idx)

                        if batch_key in completed_batches:
                            click.echo(
                                click.style(
                                    f"{progress} {scenario_name} @ {attachment_size_kb}KB "
                                    f"(repeat {repeat_idx}/{repeats}) ↷ skipped (already complete)",
                                    fg="yellow",
                                ),
                                err=True,
                            )
                            continue

                        click.echo(
                            f"{progress} {scenario_name} @ {attachment_size_kb}KB "
                            f"(repeat {repeat_idx}/{repeats})",
                            err=True,
                        )

                        try:
                            scenario = scenario_class()
                            config = ScenarioConfig(
                                scenario=scenario,
                                attachment_size_kb=attachment_size_kb,
                                turn_counts=turn_counts,
                            )

                            result = await evaluator.run_scenario(config)

                            if result.error:
                                click.echo(
                                    click.style(
                                        f"  ✗ Failed: {result.error}",
                                        fg="red",
                                    ),
                                    err=True,
                                )
                            else:
                                cost = float(result.total_cost_usd)
                                drift = result.avg_memory_drift
                                click.echo(
                                    click.style(
                                        f"  ✓ {len(result.turns)} turns, "
                                        f"${cost:.4f}, drift={drift:.1%}",
                                        fg="green",
                                    ),
                                    err=True,
                                )

                                # Extract turn data to CSV rows
                                batch_rows: list[dict] = []
                                for turn in result.turns:
                                    row = self._add_turn_to_csv(
                                        scenario_name=scenario_name,
                                        attachment_size_kb=attachment_size_kb,
                                        repeat_idx=repeat_idx,
                                        turn=turn,
                                    )
                                    batch_rows.append(row)

                                # Flush this scenario+size+repeat batch immediately
                                if output_path and batch_rows:
                                    self._append_csv_rows(output_path, batch_rows)

                        except Exception as e:
                            click.echo(
                                click.style(
                                    f"  ✗ Error: {e}",
                                    fg="red",
                                ),
                                err=True,
                            )
                            if self.verbose:
                                import traceback

                                traceback.print_exc()

            # Write CSV
            row_count = len(self.csv_rows) + existing_row_count
            if row_count > 0:
                if output_path:
                    click.echo(
                        f"✓ Results in {output_path} ({row_count} total rows)",
                        err=True,
                    )
                elif self.csv_rows:
                    self._write_csv(output_path)
                _MIN_ROWS = 50
                if row_count < _MIN_ROWS:
                    click.echo(
                        click.style(
                            f"⚠ Only {row_count} rows collected — expected ≥ {_MIN_ROWS}. "
                            "Consider increasing --repeats or adjusting turn_counts.",
                            fg="yellow",
                        ),
                        err=True,
                    )
                    return 1
                click.echo(
                    click.style(f"✓ Row count {row_count} ≥ {_MIN_ROWS}", fg="green"),
                    err=True,
                )
            else:
                click.echo("⚠ No results collected", err=True)
                return 1

            return 0

        except Exception as e:
            click.echo(
                click.style(f"✗ Fatal error: {e}", fg="red"),
                err=True,
            )
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    async def _create_evaluator(self):
        """Create scenario evaluator.

        When http_url is set, use a real httpx.Client against the remote server.
        Otherwise use in-process FastAPI TestClient.
        """
        from tests.stress.scenarios import MultiTurnScenarioEvaluator

        if self.http_url:
            evaluator = MultiTurnScenarioEvaluator(real_http=True, base_url=self.http_url)
            click.echo(f"  Client: httpx → {self.http_url}", err=True)
        else:
            evaluator = MultiTurnScenarioEvaluator(use_http_client=True)
            click.echo("  Client: in-process TestClient", err=True)

        return evaluator

    def _add_turn_to_csv(
        self,
        scenario_name: str,
        attachment_size_kb: int,
        repeat_idx: int,
        turn,
    ) -> dict:
        """Extract turn data, append to memory, and return the row."""
        # Compute fact recall: satisfied / (satisfied + violated)
        total_facts = len(turn.satisfied_facts) + len(turn.violated_facts)
        fact_recall = (
            len(turn.satisfied_facts) / total_facts if total_facts > 0 else 0.0
        )

        # TODO: Extract cache hit info from turn metadata
        # For now, placeholder values
        semantic_cache_hit = 0  # Will be populated by response metadata
        llm_cache_hit = 0

        row = {
            "scenario": scenario_name,
            "attachment_size_kb": attachment_size_kb,
            "repeat": repeat_idx,
            "turn_number": turn.turn_number,
            "latency_ms": round(turn.latency_ms, 2),
            "cost_usd": float(turn.cost_usd),
            "input_tokens": turn.input_tokens,
            "output_tokens": turn.output_tokens,
            "semantic_cache_hit": semantic_cache_hit,
            "llm_cache_hit": llm_cache_hit,
            "fact_recall": round(fact_recall, 4),
            "project_name": turn.project_name or "",
            "mentioned_technologies": ",".join(turn.mentioned_technologies),
            "team_size": turn.assumed_team_size or "",
            "agreed_scope": turn.agreed_scope or "",
        }

        self.csv_rows.append(row)
        return row

    @staticmethod
    def _csv_fieldnames() -> list[str]:
        return [
            "scenario",
            "attachment_size_kb",
            "repeat",
            "turn_number",
            "latency_ms",
            "cost_usd",
            "input_tokens",
            "output_tokens",
            "semantic_cache_hit",
            "llm_cache_hit",
            "fact_recall",
            "project_name",
            "mentioned_technologies",
            "team_size",
            "agreed_scope",
        ]

    def _initialize_csv_file(self, output_path: str) -> None:
        """Create/truncate CSV file and write header before the run starts."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._csv_fieldnames())
            writer.writeheader()
            f.flush()
            os.fsync(f.fileno())

    def _append_csv_rows(self, output_path: str, rows: list[dict]) -> None:
        """Append rows to CSV and flush to disk immediately."""
        if not rows:
            return

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._csv_fieldnames())
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())

    def _write_csv(self, output_path: str | None) -> None:
        """Write csv_rows to file or stdout."""
        if not self.csv_rows:
            return

        fieldnames = self._csv_fieldnames()

        if output_path:
            # Write to file
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            with open(output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.csv_rows)
        else:
            # Write to stdout
            import io

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.csv_rows)
            click.echo(output.getvalue())

    @staticmethod
    def _load_completed_batches(
        output_path: str,
        expected_turns: set[int],
    ) -> tuple[set[tuple[str, int, int]], int]:
        """Load completed scenario+size+repeat batches from an existing CSV."""
        output = Path(output_path)
        if not output.exists():
            return set(), 0

        turns_by_batch: dict[tuple[str, int, int], set[int]] = {}
        row_count = 0

        with open(output, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_count += 1
                try:
                    key = (
                        str(row["scenario"]),
                        int(row["attachment_size_kb"]),
                        int(row["repeat"]),
                    )
                    turn_number = int(row["turn_number"])
                except (KeyError, TypeError, ValueError):
                    continue

                if key not in turns_by_batch:
                    turns_by_batch[key] = set()
                turns_by_batch[key].add(turn_number)

        completed_batches = {
            key for key, turns in turns_by_batch.items() if expected_turns.issubset(turns)
        }
        return completed_batches, row_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--http",
    type=str,
    default=None,
    help="HTTP base URL for remote mode (e.g., http://localhost:8000). "
    "If omitted, uses in-process TestClient.",
)
@click.option(
    "--scenarios",
    type=str,
    default="growth,pivot,contradiction",
    help="Comma-separated list of scenarios to run.",
)
@click.option(
    "--attachment-sizes",
    type=str,
    default="0,5,20,50,100",
    help="Comma-separated list of attachment sizes (KB) to test.",
)
@click.option(
    "--repeats",
    type=int,
    default=3,
    help="Number of times to repeat each scenario+attachment combination.",
)
@click.option(
    "--output",
    type=str,
    default="evals/stress/results.csv",
    help="Path to write CSV results.",
)
@click.option(
    "--resume/--no-resume",
    default=True,
    help="Resume from existing CSV by skipping completed scenario+size+repeat batches.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Show detailed output.",
)
def main(
    http: str | None,
    scenarios: str,
    attachment_sizes: str,
    repeats: int,
    output: str,
    resume: bool,
    verbose: bool,
) -> None:
    """Run stress tests with configurable scenarios, attachment sizes, and repeats.

    Generates CSV with per-turn metrics for analysis and reporting.
    """
    try:
        # Parse options
        scenario_list = [s.strip() for s in scenarios.split(",")]
        size_list = [int(s.strip()) for s in attachment_sizes.split(",")]

        click.echo(
            "🚀 Stress Test Runner",
            err=True,
        )
        click.echo(f"  Mode: {'HTTP (' + http + ')' if http else 'In-process'}", err=True)
        click.echo(f"  Scenarios: {', '.join(scenario_list)}", err=True)
        click.echo(f"  Attachment sizes: {', '.join(str(s) for s in size_list)} KB", err=True)
        click.echo(f"  Repeats: {repeats}", err=True)
        click.echo(f"  Output: {output}", err=True)
        click.echo(f"  Resume: {'on' if resume else 'off'}", err=True)
        click.echo("", err=True)

        runner = StressTestRunner(http_url=http, verbose=verbose)
        exit_code = asyncio.run(
            runner.run(
                scenarios=scenario_list,
                attachment_sizes=size_list,
                repeats=repeats,
                output_path=output,
                resume=resume,
            )
        )

        sys.exit(exit_code)

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
