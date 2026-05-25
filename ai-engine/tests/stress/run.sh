#!/usr/bin/env bash
# Convenient wrapper to run synthetic stress scenarios
# Usage: ./evals/stress/run.sh [options]

cd "$(dirname "$0")/../.." || exit 1
uv run -m evals.stress.runner "$@"
