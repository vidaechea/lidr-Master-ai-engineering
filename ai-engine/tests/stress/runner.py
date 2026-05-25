"""CLI runner for synthetic stress scenario tests.

Executes multi-turn conversation scenarios to measure:
  - Memory retention (FactTracker)
  - Metadata consistency (ProjectMetadata mutations)
  - Cost curves and resource usage
  - Contradiction handling
  - Attachment handling (file size impact on latency, cost, recall)

Scenarios:
  - growth: Coherent feature accumulation (MVP → auth → multi-tenant → audit → export)
  - pivot: Technology stack change (React → Flutter at turn 5)
  - contradiction: Budget conflict (€30k → €80k at turn 8)
  - large_attachment: File size stress test (0-100 KB attachments)

Each scenario runs with N ∈ {1, 3, 6, 10, 20} turns (or scenario-specific counts) to test
behavior across conversation depth.

Cost Estimation
---------------
Each turn makes 1 LLM call (estimation). Scenarios:
  - growth: 5 turns = ~$0.005-0.01
  - pivot: 5 turns = ~$0.005-0.01
  - contradiction: 4 turns = ~$0.004-0.008
  - large_attachment: 5 turns = ~$0.01-0.02 (higher due to larger token counts)

Total for all 4 scenarios: ~$0.03-0.05 (much cheaper than LLM-judge tests).

Environment
-----------
Requires ANTHROPIC_API_KEY and OPENAI_API_KEY (for LiteLLM).

Usage
-----
  uv run -m tests.evals.stress.runner all                   # Run all scenarios
  uv run -m tests.evals.stress.runner growth                # Run growth scenario only
  uv run -m tests.evals.stress.runner pivot                 # Run pivot scenario only
  uv run -m tests.evals.stress.runner contradiction         # Run contradiction scenario only
  uv run -m tests.evals.stress.runner large_attachment      # Run attachment stress test
  uv run -m tests.evals.stress.runner --verbose             # Show detailed output
  uv run -m tests.evals.stress.runner --json out.json       # Save JSON report

Or use the wrapper:
  bash evals/stress/run.sh all
  bash evals/stress/run.sh large_attachment --verbose
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Literal

import click

from tests.evals.stress.scenarios import (
    MultiTurnScenarioEvaluator,
    ProjectContradictionScenario,
    ProjectGrowthScenario,
    ProjectLargeAttachmentScenario,
    ProjectPivotScenario,
    ScenarioConfig,
)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class StressScenarioRunner:
    """Execute stress scenario tests."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    async def run(
        self, scenario: Literal["all", "growth", "pivot", "contradiction"]
    ) -> dict:
        """Execute scenarios and return aggregated results.

        Args:
            scenario: Which scenario(s) to run.

        Returns:
            Summary dict with results for all executed scenarios.
        """
        click.echo("🔬 Running synthetic stress scenario tests", err=True)
        click.echo("", err=True)

        evaluator = MultiTurnScenarioEvaluator(use_http_client=True)

        scenario_map = {
            "growth": ProjectGrowthScenario,
            "pivot": ProjectPivotScenario,
            "contradiction": ProjectContradictionScenario,
            "large_attachment": ProjectLargeAttachmentScenario,
        }

        if scenario == "all":
            scenarios_to_run = list(scenario_map.values())
        else:
            scenarios_to_run = [scenario_map[scenario]]

        results = []
        for scenario_class in scenarios_to_run:
            scenario_obj = scenario_class()
            click.echo(
                f"▶ {scenario_obj.id}: {scenario_obj.description}",
                err=True,
            )

            config = ScenarioConfig(scenario=scenario_obj)
            result = await evaluator.run_scenario(config)
            results.append(result)

            if result.error:
                click.echo(
                    click.style(f"  ✗ Failed: {result.error}", fg="red"),
                    err=True,
                )
            else:
                click.echo(
                    click.style(
                        f"  ✓ {len(result.turns)} turns, "
                        f"${float(result.total_cost_usd):.4f}, "
                        f"drift={result.avg_memory_drift:.1%}",
                        fg="green",
                    ),
                    err=True,
                )

        click.echo("", err=True)

        # Aggregate summary
        summary = {
            "scenarios": [r.to_dict() for r in results],
            "aggregate": {
                "total_scenarios": len(results),
                "successful": sum(1 for r in results if r.error is None),
                "total_cost_usd": float(sum(r.total_cost_usd for r in results)),
                "avg_memory_drift": (
                    sum(r.avg_memory_drift for r in results) / len(results)
                    if results
                    else 0.0
                ),
            },
        }

        return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--scenario",
    type=click.Choice(["all", "growth", "pivot", "contradiction", "large_attachment"]),
    default="all",
    help="Which scenario(s) to run.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Show detailed output.",
)
@click.option(
    "--json",
    type=click.Path(),
    help="Write JSON report to this file.",
)
def main(scenario: str, verbose: bool, json: str | None) -> None:
    """Run synthetic multi-turn scenario stress tests.

    Measures memory retention, metadata consistency, and cost curves.
    """
    runner = StressScenarioRunner(verbose=verbose)

    try:
        summary = asyncio.run(runner.run(scenario))  # type: ignore

        # Write JSON if requested
        if json:
            # If no parent directory specified, save to evals/stress/results/
            json_path = Path(json)
            if json_path.parent == Path("."):
                output_path = Path("evals/stress/results") / json_path
            else:
                output_path = json_path
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json_module = __import__("json")
                json_module.dump(summary, f, indent=2)
            click.echo(f"✓ Results written to {output_path}", err=True)

        # Print summary
        click.echo("")
        click.echo("📊 Summary", err=True)
        click.echo(f"  Scenarios: {summary['aggregate']['total_scenarios']}", err=True)
        click.echo(
            f"  Successful: {summary['aggregate']['successful']}/{summary['aggregate']['total_scenarios']}",
            err=True,
        )
        click.echo(
            f"  Total Cost: ${summary['aggregate']['total_cost_usd']:.4f}",
            err=True,
        )
        click.echo(
            f"  Avg Memory Drift: {summary['aggregate']['avg_memory_drift']:.1%}",
            err=True,
        )

        sys.exit(0 if summary["aggregate"]["successful"] == summary["aggregate"]["total_scenarios"] else 1)

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
