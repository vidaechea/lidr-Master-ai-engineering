# Evaluation Suite

CLI runner for assessment of estimation pipelines via LLM-as-judge (DeepEval GEval).

## Overview

The evaluation suite provides two primary modes:

- **`actor`**: Standard estimation pipeline (non-feedback)
- **`acb`**: Actor-Critic-Boss pipeline with iterative feedback

Both modes use LLM judges (Claude Haiku via DeepEval) to measure subjective quality
metrics like scope coherence, risk coverage, and (for ACB) convergence quality.

## Quick Start

```bash
# Show available commands
uv run evals/run.py --help

# Evaluate standard estimation pipeline
uv run evals/run.py actor

# Evaluate ACB feedback-loop pipeline
uv run evals/run.py acb

# Run both modes
uv run evals/run.py all

# Show cost and coverage info
uv run evals/run.py info
```

## Command Reference

### `actor` - Standard Pipeline Evaluation

Tests the core estimation endpoint without feedback loops.

```bash
uv run evals/run.py actor
uv run evals/run.py actor --verbose      # Detailed output (pytest -vv)
uv run evals/run.py actor --junit        # Generate XML report
```

**Coverage:**
- Test file: `tests/eval/test_llm_judge.py`
- Test cases: 3 golden cases
- Metrics:
  - `ScopeCoherence` (threshold: 0.7) — do phases match described scope?
  - `RiskCoverage` (threshold: 0.6) — are key technical risks identified?
- Cost: ~12 LLM calls per run
- Duration: ~3–5 minutes

### `acb` - Actor-Critic-Boss Pipeline Evaluation

Tests the multi-agent feedback loop pipeline (actor proposes, critic reviews, boss decides).

```bash
uv run evals/run.py acb
uv run evals/run.py acb --verbose       # Detailed output
uv run evals/run.py acb --junit         # Generate XML report
```

**Coverage:**
- Test file: `tests/eval/test_acb_quality.py`
- Test cases: 3 golden cases with up to 2 iterations per case
- Metrics:
  - `ACBScopeCoherence` (threshold: 0.6)
  - `ACBRiskCoverage` (threshold: 0.3)
  - `ACBConvergence` (threshold: 0.5) — do critic issues get addressed?
- Cost: ~18 LLM calls per run
- Duration: ~5–8 minutes

### `all` - Full Suite

Sequentially runs both `actor` and `acb` modes.

```bash
uv run evals/run.py all
uv run evals/run.py all --verbose       # Detailed output
uv run evals/run.py all --junit         # Generate reports for both
```

- **Total cost:** ~30 LLM calls
- **Duration:** ~10–15 minutes

### `info` - Coverage & Cost Information

Displays test coverage, cost estimates, and environment requirements.

```bash
uv run evals/run.py info
```

## Environment Setup

The evaluation suite requires:

1. **Anthropic API key** (for Claude Haiku LLM judge)
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. **OpenAI API key** (for LiteLLM provider routing)
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

Both can be set in your shell profile or in a `.env` file (loaded by the app config).

## Test Markers

The underlying pytest tests use markers to control execution:

```bash
# Run only slow tests (default for evals)
pytest -m slow tests/eval/

# Run tests that make real LLM API calls
pytest -m llm_live tests/eval/

# Run slow + live tests (what evals/run.py does)
pytest -m "slow and llm_live" tests/eval/

# Skip slow tests
pytest -m "not slow" tests/
```

The CLI runner automatically applies `-m "slow and llm_live"` to ensure
the evaluation suite runs with real LLM calls.

## Cost Considerations

Each LLM call incurs a cost depending on your provider:

### Actor Mode (~12 calls)
- 3 golden cases
- 2 metrics per case
- 2 LLM calls per metric (one to the estimation service, one to the judge)
- Total: 2 × 3 × 2 = 12 calls

### ACB Mode (~18 calls)
- 3 golden cases
- 3 agent calls per golden (actor + critic + boss = 3 LLM calls)
- 2 metrics per case (judge makes 2 calls)
- Total: (3 agent + 2 judge) × 3 = ~15–18 calls

### Combined (~30 calls)
Running `all` incurs both.

### Model Choice

The evaluation suite uses Claude Haiku (claude-haiku-4-5-20251001) for the judge,
which is intentionally cheaper and faster than larger models. Adjust thresholds
if switching to a different judge model.

## Troubleshooting

### "deepeval not installed"
```bash
uv add deepeval
```

### API keys not found
Ensure `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are in your environment:
```bash
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY
```

Or check the app config (`app/config.py`) to see where it looks for keys.

### Tests skipped at runtime
If no test methods run, check that:
1. Test files exist (`tests/eval/test_*.py`)
2. Tests are marked with `@pytest.mark.slow` and/or `@pytest.mark.llm_live`
3. API keys are valid and not rate-limited

### Threshold mismatches
The thresholds in the metrics (e.g., `threshold=0.7` for scope coherence)
are calibrated on test data. If your domain or generation model differs,
adjust thresholds in the respective test files (`tests/eval/test_*.py`).

## Architecture

```
evals/
├── __init__.py           # Package definition
├── run.py                # CLI entry point (Click-based)
└── README.md             # This file

tests/eval/
├── __init__.py
├── conftest.py
├── golden_dataset.py     # Shared golden cases for parametrization
├── test_llm_judge.py     # Actor mode: standard pipeline evals
├── test_acb_quality.py   # ACB mode: feedback-loop evals
└── test_soft_determinism.py
```

## Adding New Tests

To add a new evaluation test:

1. Create a new test file in `tests/eval/test_*.py`
2. Import `pytestmark = [pytest.mark.slow, pytest.mark.llm_live]`
3. Define test functions with parametrization using `GOLDEN_CASES`
4. Add a new command in `evals/run.py` if you want a dedicated CLI mode

Example:

```python
# tests/eval/test_my_eval.py
import pytest
from tests.eval.golden_dataset import GOLDEN_CASES

pytestmark = [pytest.mark.slow, pytest.mark.llm_live]

@pytest.mark.parametrize("golden", GOLDEN_CASES, ids=[g["id"] for g in GOLDEN_CASES])
def test_my_metric(golden: dict):
    # Your test logic here
    pass
```

Then invoke via:
```bash
pytest -m "slow and llm_live" tests/eval/test_my_eval.py
```

## References

- DeepEval: https://docs.confident-ai.com/
- GEval metric: https://docs.confident-ai.com/docs/metrics-llm-as-judge
- FastAPI testing: https://fastapi.tiangolo.com/advanced/testing-dependencies/
