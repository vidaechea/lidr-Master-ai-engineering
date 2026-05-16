#!/usr/bin/env bash
set -euo pipefail

echo "[devcontainer] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential \
  ca-certificates \
  curl \
  pkg-config \
  libpq-dev \
  libatk1.0-0t64 \
  libatk-bridge2.0-0t64 \
  libatspi2.0-0t64 \
  libcups2t64 \
  libxkbcommon0 \
  libgbm1 \
  libasound2t64 \
  libnss3 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libx11-xcb1 \
  libgtk-3-0t64 \
  xvfb
sudo rm -rf /var/lib/apt/lists/*

echo "[devcontainer] Installing uv..."
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

echo "[devcontainer] Syncing Python dependencies (backend)..."
if [[ -f backend/pyproject.toml ]]; then
  pushd backend >/dev/null
  uv sync
  popd >/dev/null
fi

echo "[devcontainer] Syncing Python dependencies (ai-engine)..."
if [[ -f estimator-cag/pyproject.toml ]]; then
  pushd estimator-cag >/dev/null
  uv sync
  popd >/dev/null
fi

echo "[devcontainer] Installing frontend dependencies..."
if [[ -f frontend/package-lock.json ]]; then
  pushd frontend >/dev/null
  npm ci
  npx playwright install chromium
  popd >/dev/null
fi

echo "[devcontainer] Setup complete."
