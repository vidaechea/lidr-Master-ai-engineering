# Synthetic Multi-Turn Stress Scenarios

Stress tests that measure system behavior across multi-turn conversational workflows designed to expose edge cases and verify memory retention.

## Quick Start

### Run Full Suite (Tests + Report) - ONE COMMAND

```bash
# Complete pipeline: test → analyze → report
bash tests/evals/stress/run_full.sh
```

Output files:
- `tests/evals/stress/results.csv` - All turn-level metrics
- `tests/evals/stress/REPORT.md` - Executive summary with tables & analysis

### Run Tests Only

```bash
# With default scenarios (growth, pivot, contradiction), attachment sizes (0-100KB), repeats=2
uv run -m evals.stress.run

# With custom options
uv run -m evals.stress.run \
  --scenarios growth,pivot,contradiction \
  --attachment-sizes 0,5,20,50,100 \
  --repeats 3 \
  --output tests/evals/stress/results.csv \
  -v  # Verbose

# Quick test (single repeat, no attachments)
uv run -m evals.stress.run \
  --scenarios growth \
  --attachment-sizes 0 \
  --repeats 1 \
  --output /tmp/quick_test.csv
```

**Options:**
- `--scenarios`: comma-separated (growth, pivot, contradiction). Default: all.
- `--attachment-sizes`: comma-separated KB (0, 5, 20, 50, 100). Default: 0-100.
- `--repeats`: iterations per scenario+size combo. Default: 2.
- `--output`: CSV path. Default: `tests/evals/stress/results.csv`.
- `--http URL`: Remote API mode (not yet implemented; parsed only).
- `-v`: Verbose output.

### Generate Report from CSV

```bash
# Generate report from existing CSV
uv run -m tests.stress.report_generator \
  --csv tests/evals/stress/results.csv \
  --output tests/evals/stress/REPORT.md
```

**Report Contents:**
- **Summary Table**: P50/P95 latency, total cost, cache hit %, fact recall % per scenario
- **Metric Curves** (ASCII tables):
  - Latency vs input tokens
  - Cumulative cost vs turn number
  - Fact recall vs attachment size
- **Analysis** (2 paragraphs): "Where CAG breaks down and why" + performance impact

## Overview

Three scenario profiles test different aspects of the estimation system:

### 1. **Project Growth** (`growth_01`)

**Narrative:** A SaaS platform (TaskMaster) evolves incrementally.

| Turn | Event | Key Addition |
|------|-------|--------------|
| 1 | MVP | Landing page, contact form (React, Node.js, PostgreSQL) |
| 3 | Auth | User authentication with JWT |
| 6 | Multi-tenant | Tenant isolation and data partitioning |
| 10 | Audit | Tamper-proof audit logging |
| 20 | Export | CSV export with background jobs |

**Measures:**
- **Cost curve**: Monotonically increasing (more complexity = higher cost)
- **Project name survival**: "TaskMaster" persists through all 5 turns
- **Technology accumulation**: Technologies are added, never removed (React, JWT, audit, CSV all present at T20)

**Expected memory drift:** Low (< 30%) — facts are coherent and building on prior turns

---

### 2. **Project Pivot** (`pivot_01`)

**Narrative:** Technology decision changes mid-conversation.

| Turn | Event | Tech Stack |
|------|-------|-----------|
| 1-4 | Initial planning | React web app + REST API |
| 5 | **PIVOT** | Switch to **Flutter** (mobile), keep REST API |
| 6-20 | Consolidation | Flutter + FastAPI backend |

**Measures:**
- **Stack recognition**: Flutter is identified as primary technology by T20
- **Pivot cleanness**: React is superseded (not accumulated) in metadata
- **Project continuity**: "SalesFlow" name survives the pivot

**Expected memory drift:** Moderate (20-40%) — the pivot is a change, but the system should handle it gracefully

---

### 3. **Project Contradiction** (`contradiction_01`)

**Narrative:** Conflicting requirements introduce ambiguity.

| Turn | Event | Budget |
|------|-------|--------|
| 1 | Initiation | LogHub logistics platform |
| 3 | Budget stated | **€30,000** |
| 5 | Scope grows | Still assuming €30k |
| 8 | **CONTRADICTION** | **New budget: €80,000** |
| 15-20 | Alignment | Scope now matches €80k budget |

**Measures:**
- **Contradiction detection**: System recognizes the budget conflict
- **Resolution quality**: Final estimate uses €80k (later value wins or is explicitly anchored)
- **Fact consistency**: Budget value is unambiguous at T20

**Expected memory drift:** Spike at T8 (contradiction), recovery afterward

---

## Running the Scenarios

### CLI Runner (Recommended)

The stress scenarios are best executed as a module to ensure proper Python path resolution:

```bash
# Run all three scenarios
uv run -m evals.stress.runner --scenario all

# Run a single scenario
uv run -m evals.stress.runner --scenario growth
uv run -m evals.stress.runner --scenario pivot
uv run -m evals.stress.runner --scenario contradiction

# Verbose output
uv run -m evals.stress.runner --scenario all --verbose

# Save results to JSON
uv run -m evals.stress.runner --scenario all --json results/stress_2026-05-23.json
```

Or use the provided shell wrapper:

```bash
bash tests/evals/stress/run.sh --scenario all
bash tests/evals/stress/run.sh --scenario growth --verbose
```

### Pytest Integration

```bash
# Run as pytest tests (with slow + llm_live markers)
pytest -m "slow and llm_live" tests/evals/test_stress_scenarios.py

# Run a single test
pytest tests/evals/test_stress_scenarios.py::test_project_growth_scenario -m "slow and llm_live"

# With coverage
pytest tests/evals/test_stress_scenarios.py --cov=evals --cov-report=html -m "slow and llm_live"
```

### Direct Python

```python
import asyncio
from evals.stress.scenarios import (
    ProjectGrowthScenario,
    ScenarioConfig,
    MultiTurnScenarioEvaluator,
)

async def main():
    evaluator = MultiTurnScenarioEvaluator(use_http_client=True)
    config = ScenarioConfig(scenario=ProjectGrowthScenario())
    result = await evaluator.run_scenario(config)
    print(result.to_dict())

asyncio.run(main())
```

## Output

Each scenario execution produces:

### Per-Turn Metrics

```json
{
  "turn_number": 1,
  "transcript": "...",
  "cost_usd": 0.0012,
  "tokens": {"in": 400, "out": 200},
  "latency_ms": 523.4,
  "project_name": "TaskMaster",
  "technologies": ["React", "Node.js", "PostgreSQL"],
  "memory_drift": 0.0,
  "satisfied_facts": 3,
  "violated_facts": 0
}
```

### Aggregate Metrics

```json
{
  "scenario_id": "growth_01",
  "profile": "growth",
  "total_cost_usd": 0.0048,
  "cost_curve": [0.0012, 0.0024, 0.0038, 0.0042, 0.0048],
  "avg_memory_drift": 0.08,
  "final_project_name": "TaskMaster",
  "final_technologies": ["React", "Node.js", "PostgreSQL", "JWT", "audit", "CSV"],
  "error": null
}
```

## Interpretation

### Memory Drift Metric

**Definition:** Ratio of violated facts to total facts per turn.

```
memory_drift = (facts_violated) / (facts_violated + facts_satisfied)
```

| Drift | Interpretation |
|-------|---|
| 0.0–0.1 | Excellent memory retention |
| 0.1–0.3 | Good retention, minor inconsistencies |
| 0.3–0.5 | Moderate drift, some facts lost |
| 0.5–1.0 | Poor retention, significant drift |

### Cost Curve

The cumulative cost across turns should increase monotonically (or stay flat).
A decrease indicates a caching hit or error.

Example growth scenario:
```
Turn 1: $0.0012 (cumulative: $0.0012)
Turn 3: $0.0012 (cumulative: $0.0024)
Turn 6: $0.0014 (cumulative: $0.0038)
Turn 10: $0.0004 (cumulative: $0.0042)  ← Cache hit?
Turn 20: $0.0006 (cumulative: $0.0048)
```

### Project Name Survival

For growth and pivot scenarios, the project name should persist unchanged.
If it changes or disappears, this indicates a metadata management issue.

### Technology Handling

- **Growth scenario**: Technologies should accumulate (React + JWT + audit + CSV)
- **Pivot scenario**: New technology (Flutter) should appear; old (React) should be superseded
- **Contradiction scenario**: Stack should be consistent (no mixing of conflicting versions)

## Integration with MemoryDriftMetric

The FactTracker system integrates with DeepEval:

```python
from tests.evals.deterministic_metrics import MemoryDriftMetric
from deepeval.test_case import LLMTestCase
import deepeval

# Create metric
metric = MemoryDriftMetric(threshold=0.2)  # Allow 20% drift

# Create test case from scenario result
test_case = LLMTestCase(
    input=f"Scenario: {scenario_id}\n{conversation}",
    actual_output=f"Final state: {final_metadata}",
)

# Evaluate
metric.measure(test_case)
deepeval.assert_test(test_case, [metric])
```

## Troubleshooting

### "Module not found: evals.stress.scenarios"

Ensure the ai-engine root is in PYTHONPATH:
```bash
export PYTHONPATH="${PYTHONPATH}:/path/to/ai-engine"
uv run tests/evals/stress/runner.py --scenario all
```

### API key errors

Verify environment variables:
```bash
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY
```

### Rate limiting or timeout

Reduce turn counts in `ScenarioConfig`:
```python
config = ScenarioConfig(
    scenario=ProjectGrowthScenario(),
    turn_counts=[1, 3]  # Only 2 turns instead of 5
)
```

### Memory/drift spike at contradiction turn

This is expected! The contradiction turn (T8 in contradiction scenario) will show
elevated memory drift because the system is reconciling conflicting information.
This drift should resolve in subsequent turns as the new fact is established.

## Design Rationale

### Why multi-turn?

- Single-turn estimation tests are insufficient for conversational systems
- Multi-turn reveals memory, context window, and metadata mutation behavior
- Cost and latency curves are only visible across many turns

### Why synthetic?

- Golden datasets are curated for quality; synthetic tests stress edge cases
- Scenarios can be parameterized (different N values, contradiction types, etc.)
- Synthetic narratives expose system weaknesses (technology pivots, contradictions)

### Why FactTracker?

- Objective verification of memory (independent of LLM judge)
- Composable with DeepEval metrics
- Measures system behavior, not subjective quality

## References

- [FactTracker design](../../evals/stress/scenarios.py#L47)
- [Scenario profiles](../../evals/stress/scenarios.py#L244)
- [MemoryDriftMetric](../../tests/evals/metrics_stress.py#L17)
- [Session API](../../app/routers/sessions.py)
- [ProjectMetadata](../../app/services/sessions.py#L165)
