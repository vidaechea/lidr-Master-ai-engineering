#!/bin/bash
# Quick Start: Large Attachment Scenario

echo "🚀 LARGE ATTACHMENT SCENARIO - Quick Start"
echo "=========================================="
echo ""
echo "This scenario measures system performance with file attachments:"
echo "  - Latency (time to complete estimation)"
echo "  - Cost (LLM token cost)"
echo "  - Recall (does response mention attachment content?)"
echo ""
echo "Attachment sizes tested: 0 KB, 5 KB, 20 KB, 50 KB, 100 KB"
echo ""

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/ai-engine" || exit 1

# Check if dependencies are available
echo "📦 Checking dependencies..."
if ! python3 -c "import reportlab" 2>/dev/null; then
    echo "  ⚠️  reportlab not installed (optional)"
    echo "     Install with: pip install reportlab"
fi

echo ""
echo "🎯 OPTIONS:"
echo ""
echo "  Option 1: Run scenario with auto-analysis (RECOMMENDED)"
echo "    bash tests/evals/stress/scripts/test_large_attachments.sh"
echo ""
echo "  Option 2: Run scenario only"
echo "    uv run -m evals.stress.runner large_attachment --json results.json"
echo ""
echo "  Option 3: Run all scenarios (including large attachments)"
echo "    uv run -m evals.stress.runner all --json all_results.json"
echo ""
echo "  Option 4: Analyze existing results"
echo "    python tests/stress/tools/analyze_stress_results.py /path/to/results.json"
echo ""
echo "  Option 5: See example of result interpretation"
echo "    python tests/stress/tools/interpret_stress_metrics.py"
echo ""
echo "📖 For full documentation:"
echo "    cat evals/stress/docs/LARGE_ATTACHMENTS.md"
echo ""
