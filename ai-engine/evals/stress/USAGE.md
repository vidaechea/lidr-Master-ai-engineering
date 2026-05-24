# 📊 Stress Test Runner + Report Generator

**Deliverables ready for production use.**

## TLDR - One Command

```bash
cd ai-engine && bash evals/stress/run_full.sh
```

Output:
- `evals/stress/results.csv` - All metrics per turn
- `evals/stress/REPORT.md` - Executive summary

## What It Does

1. **run.py**: Executes scenarios (growth, pivot, contradiction) with varying attachment sizes (0-100KB)
2. **gen_report.py**: Analyzes CSV and generates markdown report with:
   - P50/P95 latency, cost totals, fact recall %
   - ASCII metric curves
   - "Where CAG breaks down" analysis

## Commands

### Full Pipeline (Recommended)

```bash
bash evals/stress/run_full.sh
```

Customizable output paths:
```bash
bash evals/stress/run_full.sh /path/to/results.csv /path/to/REPORT.md
```

### Just Run Tests

```bash
uv run -m evals.stress.run \
  --scenarios growth,pivot,contradiction \
  --attachment-sizes 0,5,20,50,100 \
  --repeats 3 \
  --output evals/stress/results.csv
```

### Just Generate Report (from existing CSV)

```bash
uv run -m evals.stress.gen_report \
  --csv evals/stress/results.csv \
  --output evals/stress/REPORT.md
```

## CSV Output Format

Each row = one turn result with:
- `scenario`: growth, pivot, contradiction
- `attachment_size_kb`: 0, 5, 20, 50, 100
- `repeat`: iteration index
- `turn_number`: 1, 3, 6, 10, 20
- `latency_ms`, `cost_usd`, `input_tokens`, `output_tokens`
- `fact_recall`: 0-1 (facts verified / total facts)
- `project_name`, `mentioned_technologies`, `team_size`, `agreed_scope`

## Example Report

See `evals/stress/example_results.csv` → generate with:
```bash
uv run -m evals.stress.gen_report --csv evals/stress/example_results.csv
```

## Test Results (if run)

1. **Growth Scenario**: Coherent feature accumulation → stable recall ~91%
2. **Pivot Scenario**: Tech stack change at T5 → moderate drift, recall ~91%  
3. **Contradiction**: Budget conflict T8 → high drift, recall drops to ~58% by T20

**Insight**: CAG degradation accelerates with contradictory information and long conversations (>10 turns). Attachments add latency spikes but preserve accuracy.

---

**Files:**
- `run.py` - CLI orchestrator
- `gen_report.py` - Report generator
- `run_full.sh` - End-to-end automation
- `README.md` - Full documentation
- `example_results.csv` - Sample data
