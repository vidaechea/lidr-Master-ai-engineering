"""CLI runner for LLM evaluation suite.

Executes evaluation tests with different modes:
  - actor: Evaluate the standard estimation pipeline
  - acb: Evaluate the Actor-Critic-Boss pipeline with feedback loops

Both modes run LLM-judge tests (DeepEval GEval) to measure subjective quality
metrics like scope coherence, risk coverage, and (for ACB) convergence quality.

Cost Estimation
---------------
Each test mode calls the estimation service multiple times and uses DeepEval
metrics which call an LLM judge (Claude Haiku). Budget accordingly:
  - actor mode: ~12 LLM calls per run (2 per golden × 3 goldens × 2 metrics)
  - acb mode: ~18 LLM calls per run (3 per ACB call × 3 goldens × 2 metrics)

Environment
-----------
Requires ANTHROPIC_API_KEY and OPENAI_API_KEY (for LiteLLM). 
If LLM provider keys are missing, tests will be skipped at runtime.

Usage
-----
  uv run -m tests.evals.eval_runner actor           # Test standard estimation
  uv run -m tests.evals.eval_runner acb             # Test ACB pipeline
  uv run -m tests.evals.eval_runner acb --verbose   # Show detailed output
  uv run -m tests.evals.eval_runner --help          # Show all options
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

import click

# Ensure ai-engine is importable from this script
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Evaluation runner logic
# ---------------------------------------------------------------------------


class EvalRunner:
    """Execute evaluation tests via pytest with structured output."""

    def __init__(self, verbose: bool = False, junit_report: bool = False):
        self.verbose = verbose
        self.junit_report = junit_report

    def run(self, mode: Literal["actor", "acb"]) -> int:
        """Execute evaluation for the specified mode.
        
        Args:
            mode: Either "actor" (standard estimation) or "acb" (feedback loops)
            
        Returns:
            Exit code from pytest (0 = success, non-zero = failure)
        """
        import subprocess

        # Build pytest command
        cmd = ["pytest"]

        # Select test file based on mode
        if mode == "actor":
            test_target = "tests/evals/test_llm_judge.py"
            click.echo("🔍 Running actor mode: standard estimation pipeline evaluation", err=True)
            click.echo(
                "   Cost: ~12 LLM calls (2 per golden × 3 goldens × 2 metrics)",
                err=True,
            )
        elif mode == "acb":
            test_target = "tests/evals/test_acb_quality.py"
            click.echo("🔄 Running ACB mode: Actor-Critic-Boss pipeline evaluation", err=True)
            click.echo(
                "   Cost: ~18 LLM calls (3 per ACB call × 3 goldens × 2 metrics)",
                err=True,
            )
        else:
            raise ValueError(f"Unknown mode: {mode}")

        cmd.append(test_target)

        # Always include slow and llm_live markers
        cmd.extend(["-m", "slow and llm_live"])

        # Add verbosity flag
        if self.verbose:
            cmd.append("-vv")
            cmd.append("--tb=short")
        else:
            cmd.append("-v")

        # Add junit report if requested
        if self.junit_report:
            report_path = f"eval_report_{mode}.xml"
            cmd.append(f"--junit-xml={report_path}")
            click.echo(f"   Report: {report_path}", err=True)

        click.echo("", err=True)

        # Run pytest
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        return result.returncode

    def run_all(self) -> int:
        """Execute both actor and ACB evaluation modes sequentially.
        
        Returns:
            Exit code (0 if all pass, non-zero if any fail)
        """
        click.echo("🚀 Running full evaluation suite (actor + acb)", err=True)
        click.echo("", err=True)

        # Run actor mode
        actor_exit = self.run("actor")
        actor_passed = actor_exit == 0

        click.echo("", err=True)
        click.echo("=" * 70, err=True)
        click.echo("", err=True)

        # Run ACB mode
        acb_exit = self.run("acb")
        acb_passed = acb_exit == 0

        # Summary
        click.echo("", err=True)
        click.echo("=" * 70, err=True)
        click.echo("📊 Evaluation Summary", err=True)
        click.echo(f"  Actor mode: {'✓ PASSED' if actor_passed else '✗ FAILED'}", err=True)
        click.echo(f"  ACB mode:   {'✓ PASSED' if acb_passed else '✗ FAILED'}", err=True)
        click.echo("", err=True)

        # Return failure if any mode failed
        return 0 if (actor_passed and acb_passed) else 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Evaluation suite runner for estimation pipelines.
    
    Select a mode (actor or acb) or run all tests:
    
      evals/run.py actor          # Evaluate standard estimation
      evals/run.py acb            # Evaluate ACB pipeline
      evals/run.py all            # Run both modes
    """
    # If no command provided, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output (pytest -vv)",
)
@click.option(
    "--junit",
    is_flag=True,
    help="Generate JUnit XML report",
)
def actor(verbose: bool, junit: bool) -> None:
    """Evaluate the standard (non-ACB) estimation pipeline.
    
    Runs tests from test_llm_judge.py with GEval metrics:
      - ScopeCoherence: phases match described scope
      - RiskCoverage: risks cover main technical areas
    
    Cost: ~12 LLM calls per run
    """
    runner = EvalRunner(verbose=verbose, junit_report=junit)
    exit_code = runner.run("actor")
    sys.exit(exit_code)


@cli.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output (pytest -vv)",
)
@click.option(
    "--junit",
    is_flag=True,
    help="Generate JUnit XML report",
)
def acb(verbose: bool, junit: bool) -> None:
    """Evaluate the Actor-Critic-Boss (ACB) feedback-loop pipeline.
    
    Runs tests from test_acb_quality.py with additional GEval metrics:
      - ACBScopeCoherence: final estimate matches project scope
      - ACBRiskCoverage: risks cover key technical areas
      - ACBConvergence: feedback from critic is incorporated
    
    The ACB pipeline is a three-agent loop where the critic reviews the actor's
    draft and the boss decides whether to accept, request revision, or reject.
    
    Cost: ~18 LLM calls per run (more than actor because 3-agent pipeline)
    """
    runner = EvalRunner(verbose=verbose, junit_report=junit)
    exit_code = runner.run("acb")
    sys.exit(exit_code)


@cli.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output (pytest -vv)",
)
@click.option(
    "--junit",
    is_flag=True,
    help="Generate JUnit XML report for each mode",
)
def all(verbose: bool, junit: bool) -> None:
    """Run the full evaluation suite: both actor and ACB modes.
    
    Sequentially executes:
      1. actor mode (~12 LLM calls)
      2. acb mode (~18 LLM calls)
    
    Total cost: ~30 LLM calls per run
    
    Returns exit code 0 only if all modes pass.
    """
    runner = EvalRunner(verbose=verbose, junit_report=junit)
    exit_code = runner.run_all()
    sys.exit(exit_code)


@cli.command()
def info() -> None:
    """Show cost estimates and test coverage information."""
    info_text = """
📊 Evaluation Suite Information
═══════════════════════════════════════════════════════════════════════════

Mode: actor
  File: tests/evals/test_llm_judge.py
  Test Cases: 3 golden cases (small_landing_page, medium_web_app, large_complex)
  Metrics: ScopeCoherence (threshold: 0.7), RiskCoverage (threshold: 0.6)
  Cost: 2 LLM calls/golden × 3 goldens × 2 metrics = ~12 calls
  Duration: ~3-5 minutes (depends on model latency)

Mode: acb
  File: tests/evals/test_acb_quality.py
  Test Cases: 3 golden cases with ACB pipeline (max 2 iterations)
  Metrics: ACBScopeCoherence (0.6), ACBRiskCoverage (0.3), ACBConvergence (0.5)
  Pipeline: Actor → Critic → Boss (3 LLM calls per golden, configurable iterations)
  Cost: 3 LLM/golden × 3 goldens (1 iter) + judge = ~18 calls per run
  Duration: ~5-8 minutes

Combined (all)
  Total Cost: ~30 LLM calls
  Duration: ~10-15 minutes

Environment Requirements
  ✓ ANTHROPIC_API_KEY - Required for Claude Haiku judge
  ✓ OPENAI_API_KEY - Required for LiteLLM router

Markers
  --mark slow: Tests marked as slow (multiple LLM calls)
  --mark llm_live: Tests that make real API calls (not mocked)
  
  Run without slow tests: pytest -m "not slow" tests/
  Run only unit tests: pytest tests/unit/
"""
    click.echo(info_text)


if __name__ == "__main__":
    cli()
