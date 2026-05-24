# Deterministic Metrics for Stress Testing

## Overview

`evals/metrics.py` provides three deterministic metrics for evaluating multi-turn estimation pipelines:

1. **LatencyBudgetMetric** — Measure if latency respects budget constraints
2. **CostBudgetMetric** — Measure if LLM costs stay within budget
3. **MemoryDriftMetric** — Measure if facts declared in early turns are retained in later turns

All metrics follow a **deterministic** pattern (no embeddings, no LLM-as-judge) and use simple, predictable string matching with the `MetricResult` container.

## Design Rationale

### Location: `evals/metrics.py` vs. `evals/stress/metrics.py`

We chose **`evals/metrics.py`** (workspace root of evals) instead of `evals/stress/metrics.py` because:

- **Modularity**: These metrics are general-purpose evaluation tools, not specific to stress testing
- **Reusability**: Can be used by both stress scenarios and other evaluation modes (actor, ACB)
- **Clarity**: Mirrors Python's standard organization: `evals.metrics` is a natural module name
- **Separation**: Keeps deterministic metrics separate from DeepEval-based metrics in `evals.stress.metrics.stress_metrics`

### Why Deterministic? (No LLM-as-Judge)

- **Reproducibility**: Same input always produces same output
- **Debuggability**: Easy to trace why a metric passed or failed
- **Cost**: No additional LLM calls (already expensive in stress scenarios)
- **Performance**: Microsecond evaluation vs. multi-second LLM calls

## MetricResult Pattern

All metrics return a standardized `MetricResult`:

```python
@dataclass
class MetricResult:
    name: str          # Metric identifier
    score: float       # 0.0 to 1.0 (1.0 is ideal)
    passed: bool       # Boolean pass/fail
    details: str       # Human-readable explanation
```

This pattern is compatible with logging, dashboards, and CI/CD assertions.

---

## LatencyBudgetMetric

**Purpose**: Verify that LLM response latency stays within allowed bounds.

**Score**: 
- `1.0` if `latency_ms ≤ budget_ms`
- `0.0` if exceeded

**Usage**:

```python
from evals.metrics import LatencyBudgetMetric
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

## CostBudgetMetric

**Purpose**: Verify that LLM call costs stay within operational budgets.

**Score**:
- `1.0` if `cost_usd ≤ budget_usd`
- `0.0` if exceeded

**Usage**:

```python
from evals.metrics import CostBudgetMetric

metric = CostBudgetMetric(budget_usd=0.05)  # $0.05 per turn
observation = TurnObservedEvent(...)

result = metric.evaluate(observation)
print(f"Cost: ${result.details}")
# Cost: $0.005000 within budget $0.050000
```

**Input**: Any object with `cost_usd` attribute (float, USD)

**Output**: `MetricResult` with binary score (1.0 or 0.0)

---

## MemoryDriftMetric

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
from evals.metrics import MemoryDriftMetric
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

## Integration Examples

### Stress Test Evaluation

```python
from evals.metrics import LatencyBudgetMetric, CostBudgetMetric, MemoryDriftMetric
from evals.stress.scenarios import MultiTurnScenarioEvaluator, ProjectGrowthScenario

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

# Evaluate memory drift of key facts
memory_metric = MemoryDriftMetric(
    fact="project_name",
    where=["metadata"]
)

# ... check if project_name was retained through all turns
```

### Session Validation

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

## Testing

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

## Design Notes

### Why Binary Scores?

- **Simplicity**: Pass/fail is easier to reason about than 0.0-1.0 gradients
- **Budgets**: Latency/cost budgets are inherently binary constraints
- **Memory**: Fact presence is binary (found or not found)
- **Composability**: Easy to combine multiple binary metrics via AND/OR logic

### Why No Fuzzy Matching?

- **Determinism**: Exact matches guarantee reproducibility
- **Debuggability**: Easier to understand why a test failed
- **No hidden assumptions**: No magic LLM scoring or heuristics
- **Performance**: O(n) substring search vs. O(n²) fuzzy algorithms

### Why Metrics in Workspace Root?

- **Discoverability**: `from evals.metrics import X` is intuitive
- **Separation of concerns**: Stress-specific logic stays in `evals.stress.metrics`
- **Reusability**: Other evaluation modes can import these metrics
- **Future extensibility**: Easy to add more deterministic metrics later

---

## See Also

- [evals/stress/metrics/stress_metrics.py](../stress/metrics/stress_metrics.py) — DeepEval-based metrics
- [app/schemas/observation.py](../../app/schemas/observation.py) — TurnObservedEvent schema
- [app/services/sessions.py](../../app/services/sessions.py) — Session and ProjectMetadata classes
- [tests/unit/test_metrics.py](../../tests/unit/test_metrics.py) — Full test suite
