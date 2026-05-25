#!/bin/bash
# Quick reference for running evaluations
# Place this file in the ai-engine root for easy access

echo "📊 Estimation Pipeline Evaluation Suite"
echo "========================================"
echo ""
echo "Quick Commands:"
echo "  uv run evals/run.py actor       # Evaluate standard pipeline"
echo "  uv run evals/run.py acb         # Evaluate ACB pipeline"
echo "  uv run evals/run.py all         # Run all evaluations"
echo "  uv run evals/run.py info        # Show cost & coverage info"
echo ""
echo "With Options:"
echo "  uv run evals/run.py actor -v    # Verbose output"
echo "  uv run evals/run.py acb --junit # Generate JUnit XML report"
echo ""
echo "Direct pytest (if you prefer):"
echo "  pytest -m 'slow and llm_live' tests/eval/"
echo ""
