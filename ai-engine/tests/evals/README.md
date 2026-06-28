# Evaluation Suite

CLI runner for assessment of estimation pipelines via LLM-as-judge (DeepEval GEval) and deterministic metrics for multi-turn validation.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Command Reference](#command-reference)
   - [actor - Standard Pipeline](#actor---standard-pipeline-evaluation)
   - [acb - Actor-Critic-Boss](#acb---actor-critic-boss-pipeline-evaluation)
   - [all - Full Suite](#all---full-suite)
   - [info - Coverage & Cost](#info---coverage--cost-information)
4. [Deterministic Metrics](#deterministic-metrics)
   - [LatencyBudgetMetric](#latencybudgetmetric)
   - [CostBudgetMetric](#costbudgetmetric)
   - [MemoryDriftMetric](#memorydriftmetric)
5. [Environment Setup](#environment-setup)
6. [Test Markers](#test-markers)
7. [Cost Considerations](#cost-considerations)
8. [Troubleshooting](#troubleshooting)
9. [Architecture](#architecture)
10. [Adding New Tests](#adding-new-tests)
11. [References](#references)

## Overview

The evaluation suite provides two primary modes:

- **`actor`**: Standard estimation pipeline (non-feedback)
- **`acb`**: Actor-Critic-Boss pipeline with iterative feedback

Both modes use LLM judges (Claude Haiku via DeepEval) to measure subjective quality
metrics like scope coherence, risk coverage, and (for ACB) convergence quality.

Additionally, the suite includes **deterministic metrics** for multi-turn evaluation:
- **LatencyBudgetMetric** — Verify response latency stays within bounds
- **CostBudgetMetric** — Verify LLM costs stay within budget
- **MemoryDriftMetric** — Verify facts are retained across conversation turns

## Quick Start

```bash
# Show available commands
uv run -m tests.evals.eval_runner --help

# Evaluate standard estimation pipeline
uv run -m tests.evals.eval_runner actor

# Evaluate ACB feedback-loop pipeline
uv run -m tests.evals.eval_runner acb

# Run both modes
uv run -m tests.evals.eval_runner all

# Show cost and coverage info
uv run -m tests.evals.eval_runner info

# Evaluate full RAG generation with the four RAGAS metrics
uv sync --extra evals
uv run python scripts/eval_ragas_generation.py --base-url http://localhost:8001 --rerank
```

The RAGAS runner uses the golden set in `tests/evals/ragas_generation_golden_set.json` and reports:

- answer relevancy
- faithfulness
- contextual precision
- contextual recall
- grounded vs. ungrounded line items
- dangling line-level citation references

## Command Reference

### `actor` - Standard Pipeline Evaluation

Tests the core estimation endpoint without feedback loops.

```bash
uv run -m tests.evals.eval_runner actor
uv run -m tests.evals.eval_runner actor --verbose      # Detailed output (pytest -vv)
uv run -m tests.evals.eval_runner actor --junit        # Generate XML report
```

**Coverage:**
- Test file: `tests/evals/test_llm_judge.py`
- Test cases: 3 golden cases
- Metrics:
  - `ScopeCoherence` (threshold: 0.7) — do phases match described scope?
  - `RiskCoverage` (threshold: 0.6) — are key technical risks identified?
- Cost: ~12 LLM calls per run
- Duration: ~3–5 minutes

### `acb` - Actor-Critic-Boss Pipeline Evaluation

Tests the multi-agent feedback loop pipeline (actor proposes, critic reviews, boss decides).

```bash
uv run -m tests.evals.eval_runner acb
uv run -m tests.evals.eval_runner acb --verbose       # Detailed output
uv run -m tests.evals.eval_runner acb --junit         # Generate XML report
```

**Coverage:**
- Test file: `tests/evals/test_acb_quality.py`
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
uv run -m tests.evals.eval_runner all
uv run -m tests.evals.eval_runner all --verbose       # Detailed output
uv run -m tests.evals.eval_runner all --junit         # Generate reports for both
```

- **Total cost:** ~30 LLM calls
- **Duration:** ~10–15 minutes

### `info` - Coverage & Cost Information

Displays test coverage, cost estimates, and environment requirements.

```bash
uv run -m tests.evals.eval_runner info
```

## Deterministic Metrics

The suite includes three **deterministic, reusable metrics** for multi-turn evaluation pipelines. These metrics use exact string matching (no LLM-as-judge) and are located in `tests/evals/deterministic_metrics.py`.

### Design Rationale

**Why deterministic?**
- **Reproducibility**: Same input always produces same output
- **Debuggability**: Easy to trace why a metric passed or failed
- **Cost**: No additional LLM calls (already expensive in stress scenarios)
- **Performance**: Microsecond evaluation vs. multi-second LLM calls

**Why in workspace root?**
- **Modularity**: General-purpose tools, not specific to stress testing
- **Reusability**: Can be used by actor, ACB, and stress evaluation modes
- **Discoverability**: `from tests.evals.deterministic_metrics import X` is clear

### MetricResult Pattern

All metrics return a standardized `MetricResult`:

```python
@dataclass
class MetricResult:
    name: str          # Metric identifier
    score: float       # 0.0 to 1.0 (1.0 is ideal)
    passed: bool       # Boolean pass/fail
    details: str       # Human-readable explanation
```

---

### LatencyBudgetMetric

**Purpose**: Verify that LLM response latency stays within allowed bounds.

**Score**: 
- `1.0` if `latency_ms ≤ budget_ms`
- `0.0` if exceeded

**Usage**:

```python
from tests.evals.deterministic_metrics import LatencyBudgetMetric
from app.schemas.observation import TurnObservedEvent

metric = LatencyBudgetMetric(budget_ms=5000)  # 5 seconds
observation = TurnObservedEvent(...)  # Populated from actual turn

result = metric.evaluate(observation)
print(f"✓ {result.passed}: {result.details}")
# ✓ True: Latency 2500.5ms within budget 5000ms
```

**Input**: Any object with `latency_ms` attribute (float, milliseconds)

**Output**: `MetricResult` with binary score (1.0 or 0.0)

---

### CostBudgetMetric

**Purpose**: Verify that LLM call costs stay within operational budgets.

**Score**:
- `1.0` if `cost_usd ≤ budget_usd`
- `0.0` if exceeded

**Usage**:

```python
from tests.evals.deterministic_metrics import CostBudgetMetric

metric = CostBudgetMetric(budget_usd=0.05)  # $0.05 per turn
observation = TurnObservedEvent(...)

result = metric.evaluate(observation)
print(f"Cost: ${result.details}")
# Cost: $0.005000 within budget $0.050000
```

**Input**: Any object with `cost_usd` attribute (float, USD)

**Output**: `MetricResult` with binary score (1.0 or 0.0)

---

### MemoryDriftMetric

**Purpose**: Track fact retention across multi-turn conversations.

**Score**:
- `1.0` if fact is found (case-insensitive) in any declared field
- `0.0` if fact is not found

**Searches across**:
- `summary` — Conversation summary text
- `anchors` — Extracted key information anchors (list of dicts or strings)
- `metadata` — ProjectMetadata fields (project_name, mentioned_technologies, agreed_scope, assumed_team_size)

**Usage**:

```python
from tests.evals.deterministic_metrics import MemoryDriftMetric
from app.services.sessions import Session

metric = MemoryDriftMetric(
    fact="React",
    where=["summary", "anchors", "metadata"]
)

# Simulate session state with multiple turns
snapshot = type('Snapshot', (), {
    'summary': 'User said we will use React for the frontend.',
    'anchors': [
        {'anchor_type': 'tech', 'key_information': 'React'},
        {'anchor_type': 'budget', 'key_information': '€50k'}
    ],
    'metadata': session.metadata  # ProjectMetadata instance
})()

result = metric.evaluate(snapshot)
print(f"Memory drift: {result.details}")
# Memory drift: Fact 'react' found in: summary, anchors, metadata
```

**Case Sensitivity**: All searches are case-insensitive (converted to lowercase).

**Matching**:
- **Text fields** (summary, agreed_scope): Substring match
- **Technologies list**: Exact word match
- **Project name**: Substring match
- **Anchors**: Searches all dict values as substrings

**Input**: Any object with optional `summary`, `anchors`, `metadata` attributes

**Output**: `MetricResult` with binary score (1.0 or 0.0)

---

### Integration Examples

#### Stress Test Evaluation

```python
from tests.evals.deterministic_metrics import LatencyBudgetMetric, CostBudgetMetric, MemoryDriftMetric
from tests.stress.scenarios import MultiTurnScenarioEvaluator, ProjectGrowthScenario

evaluator = MultiTurnScenarioEvaluator(service=EstimationService())
scenario_result = await evaluator.run(ProjectGrowthScenario().config())

# Evaluate performance constraints
latency_metric = LatencyBudgetMetric(budget_ms=3000)
cost_metric = CostBudgetMetric(budget_usd=0.10)

all_passed = True
for turn_obs in scenario_result.turns:
    latency_result = latency_metric.evaluate(turn_obs)
    cost_result = cost_metric.evaluate(turn_obs)
    
    if not (latency_result.passed and cost_result.passed):
        all_passed = False
        print(f"Turn {turn_obs.turn_index}: {latency_result.details}")
        print(f"               {cost_result.details}")
```

#### Session Validation

```python
# After a multi-turn session, validate that critical facts persist
facts_to_check = [
    ("React", ["summary", "metadata"]),
    ("€50,000", ["metadata", "anchors"]),
    ("5 engineers", ["summary"]),
]

for fact, locations in facts_to_check:
    metric = MemoryDriftMetric(fact=fact, where=locations)
    result = metric.evaluate(session_snapshot)
    
    if not result.passed:
        print(f"⚠ Memory drift detected: {fact} not found")
```

---

### Testing Deterministic Metrics

All metrics are tested via `tests/unit/test_metrics.py` (21 test cases):

```bash
# Run all metric tests
uv run -m pytest tests/unit/test_metrics.py -v

# Run specific metric tests
uv run -m pytest tests/unit/test_metrics.py::TestLatencyBudgetMetric -v
uv run -m pytest tests/unit/test_metrics.py::TestMemoryDriftMetric -v
```

**Test Coverage**:
- Boundary cases (at/exceeding budget)
- Missing fields (graceful fallback)
- Case-insensitive search
- Multi-location fact matching
- Input validation (negative budgets, invalid fields)

---

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
pytest -m slow tests/evals/

# Run tests that make real LLM API calls
pytest -m llm_live tests/evals/

# Run slow + live tests (what eval_runner does)
pytest -m "slow and llm_live" tests/evals/

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

The evaluation suite uses Claude Haiku for the judge, which is intentionally
cheaper and faster than larger models. Adjust thresholds if switching to a
different judge model.

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
1. Test files exist (`tests/evals/test_*.py`)
2. Tests are marked with `@pytest.mark.slow` and/or `@pytest.mark.llm_live`
3. API keys are valid and not rate-limited

### Threshold mismatches
The thresholds in the metrics (e.g., `threshold=0.7` for scope coherence)
are calibrated on test data. If your domain or generation model differs,
adjust thresholds in the respective test files (`tests/evals/test_*.py`).

## Architecture

```
tests/evals/
├── __init__.py                          # Package definition
├── eval_runner.py                       # CLI entry point (Click-based)
├── deterministic_metrics.py             # Reusable deterministic metrics
├── deterministic_metrics_quickstart.py  # Examples for metrics usage
├── golden_dataset.py                    # Golden cases for parametrization
├── test_llm_judge.py                    # Actor mode: LLM judge tests
├── test_acb_quality.py                  # ACB mode: ACB quality tests
├── test_soft_determinism.py             # Family 2: Soft determinism tests
└── README.md                            # This file

tests/stress/
├── runner.py                            # Stress test orchestrator
├── scenarios.py                         # Multi-turn scenario definitions
├── report_generator.py                  # CSV → markdown report
├── generators/                          # PDF generation utilities
├── metrics/                             # Stress-specific metrics (DeepEval)
├── tools/
│   ├── analyze_stress_results.py        # Analyze stress test results
│   └── interpret_stress_metrics.py      # Interpret metrics narratively
└── ...more files
```

## Adding New Tests

To add a new evaluation test:

1. Create a new test file in `tests/evals/test_*.py`
2. Import `pytestmark = [pytest.mark.slow, pytest.mark.llm_live]`
3. Define test functions with parametrization using `GOLDEN_CASES`
4. Add a new command in `tests/evals/eval_runner.py` if you want a dedicated CLI mode

Example:

```python
# tests/evals/test_my_eval.py
import pytest
from tests.evals.golden_dataset import GOLDEN_CASES

pytestmark = [pytest.mark.slow, pytest.mark.llm_live]

@pytest.mark.parametrize("golden", GOLDEN_CASES, ids=[g["id"] for g in GOLDEN_CASES])
def test_my_metric(golden: dict):
    # Your test logic here
    pass
```

Then invoke via:
```bash
pytest -m "slow and llm_live" tests/evals/test_my_eval.py
```

## References

- DeepEval: https://docs.confident-ai.com/
- GEval metric: https://docs.confident-ai.com/docs/metrics-llm-as-judge
- FastAPI testing: https://fastapi.tiangolo.com/advanced/testing-dependencies/
- [deterministic_metrics.py](./deterministic_metrics.py) — Metric implementations
- [deterministic_metrics_quickstart.py](./deterministic_metrics_quickstart.py) — Usage examples
- [test_metrics.py](../unit/test_metrics.py) — Full metric test suite
