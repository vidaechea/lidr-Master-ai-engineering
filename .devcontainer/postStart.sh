#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

ensure_uv() {
  echo "[devcontainer] Ensuring uv is available..."
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  uv --version
}

sync_python_project() {
  local project_dir="$1"
  local label="$2"

  if [[ ! -f "$project_dir/pyproject.toml" ]]; then
    return
  fi

  echo "[devcontainer] Syncing Python dependencies (${label})..."
  pushd "$project_dir" >/dev/null
  uv sync
  popd >/dev/null
}

ensure_frontend_dependencies() {
  if [[ ! -f frontend/package-lock.json ]]; then
    return
  fi

  echo "[devcontainer] Checking frontend dependencies..."
  pushd frontend >/dev/null

  if [[ ! -x node_modules/.bin/ng ]]; then
    echo "[devcontainer] frontend/node_modules missing or incomplete; running npm ci..."
    npm ci
  else
    echo "[devcontainer] frontend dependencies already installed."
  fi

  popd >/dev/null
}

ensure_uv
sync_python_project backend "backend"
sync_python_project estimator-cag "ai-engine"
ensure_frontend_dependencies

echo "[devcontainer] Workspace bootstrap complete."