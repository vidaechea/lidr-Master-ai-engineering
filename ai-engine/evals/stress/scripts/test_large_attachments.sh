#!/bin/bash
# Large Attachment Scenario Test Runner
# Executes the large attachment stress test and provides detailed analysis

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$PROJECT_ROOT/ai-engine"

OUTPUT_DIR="evals/stress/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/large_attachment_${TIMESTAMP}.json"

echo "🚀 Starting Large Attachment Scenario Test"
echo "   Output: $OUTPUT_FILE"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Run the scenario
echo "⏳ Running scenario..."
uv run -m evals.stress.runner large_attachment --json "$OUTPUT_FILE"

# Check if output file was created
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "❌ Failed to generate results file"
    exit 1
fi

echo ""
echo "📊 Analyzing results..."
echo ""

# Run analysis
python evals/stress/tools/analyze.py "$OUTPUT_FILE"

echo ""
echo "✅ Complete!"
echo ""
echo "Results saved to: $OUTPUT_FILE"
