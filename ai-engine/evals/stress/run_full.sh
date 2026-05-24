#!/bin/bash
# Orchestrate complete stress test suite: run tests + generate report

set -e

OUTPUT_CSV="${1:-evals/stress/results.csv}"
REPORT_PATH="${2:-evals/stress/REPORT.md}"

echo "🚀 Stress Test Suite"
echo "  CSV Output: $OUTPUT_CSV"
echo "  Report: $REPORT_PATH"
echo ""

# Run stress tests
echo "▶ Running stress tests..."
uv run -m evals.stress.run \
  --scenarios growth,pivot,contradiction \
  --attachment-sizes 0,5,20,50,100 \
  --repeats 2 \
  --output "$OUTPUT_CSV" \
  -v

echo ""
echo "▶ Generating report..."
uv run -m evals.stress.gen_report \
  --csv "$OUTPUT_CSV" \
  --output "$REPORT_PATH"

echo ""
echo "✓ Complete! Report: $REPORT_PATH"
