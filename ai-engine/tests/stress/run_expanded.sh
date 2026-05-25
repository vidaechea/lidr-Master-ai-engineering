#!/bin/bash
# Run expanded stress test with more repetitions to reach ≥50 rows
# Increases repeats from 2 → 3 to meet: 3 scenarios × 5 sizes × 3 repeats × N turns ≥ 50 rows

set -e

OUTPUT_CSV="${1:-tests/stress/results_expanded.csv}"
REPORT_PATH="${2:-tests/stress/REPORT_expanded.md}"

echo "🚀 Expanded Stress Test Suite (≥50 rows)"
echo "  CSV Output: $OUTPUT_CSV"
echo "  Report: $REPORT_PATH"
echo ""
echo "Test Matrix:"
echo "  Scenarios: 3 (growth, pivot, contradiction)"
echo "  Attachment sizes: 5 (0, 5, 20, 50, 100 KB)"
echo "  Repeats: 3 (per combination)"
echo "  Expected rows: 3 × 5 × 3 × ~4 turns = ~180 rows"
echo ""

# Run stress tests with expanded parameters
echo "▶ Running expanded stress tests..."
uv run -m tests.stress.run \
  --scenarios growth,pivot,contradiction \
  --attachment-sizes 0,5,20,50,100 \
  --repeats 3 \
  --output "$OUTPUT_CSV" \
  -v

# Check result
if [ -f "$OUTPUT_CSV" ]; then
    ROWS=$(wc -l < "$OUTPUT_CSV")
    DATA_ROWS=$((ROWS - 1))
    echo ""
    echo "✅ CSV generated: $OUTPUT_CSV"
    echo "   Total lines: $ROWS (including header)"
    echo "   Data rows: $DATA_ROWS"
    
    if [ $DATA_ROWS -ge 50 ]; then
        echo "   ✓ CRITERION MET: ≥50 rows ($DATA_ROWS) ✓"
    else
        echo "   ⚠ Below criterion: $DATA_ROWS rows (need ≥50)"
    fi
    
    echo ""
    echo "▶ Generating report..."
    uv run -m tests.stress.report_generator \
      --csv "$OUTPUT_CSV" \
      --output "$REPORT_PATH"
    
    echo ""
    echo "✓ Complete! Report: $REPORT_PATH"
else
    echo "❌ CSV not generated at $OUTPUT_CSV"
    exit 1
fi
