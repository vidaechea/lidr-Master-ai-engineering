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

echo "[devcontainer] Running workspace bootstrap..."
bash .devcontainer/postStart.sh

echo "[devcontainer] Setup complete."
