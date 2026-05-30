# Dev Container Setup

This repository includes a multi-service dev container under `.devcontainer/`.

## Files

- `devcontainer.json`: VS Code dev container definition (build, features, extensions, hooks).
- `Dockerfile`: base image for the container (`python:3.12-bookworm`) and apt source fix.
- `postCreate.sh`: one-time setup after container creation.
- `postStart.sh`: idempotent workspace bootstrap (runs on every start).

## What happens on container create/start

1. Build container from `.devcontainer/Dockerfile`.
2. Install VS Code features from `devcontainer.json`:
   - Node 20
   - Docker-outside-of-Docker
3. Run `postCreate.sh`:
   - installs system packages needed by backend/ai-engine and browser-based frontend tests
   - calls `postStart.sh`
4. Run `postStart.sh`:
   - ensures `uv` exists
   - runs `uv sync` in `backend/` and `ai-engine/` when `pyproject.toml` is present
   - runs `npm ci` in `frontend/` when `package-lock.json` exists and Angular CLI is missing

## Dependency source of truth

- Inside dev container, Python dependencies are installed with `uv sync` from each component `pyproject.toml`.
- `ai-engine/requirements.txt` remains useful for local pip workflows (especially Windows local virtualenv usage).

## Rebuild / validate commands

```bash
# From repo root in the dev container terminal
cd backend && uv sync
cd ../ai-engine && uv sync
cd ../frontend && npm ci
```

If the environment drifts, use VS Code command: `Dev Containers: Rebuild Container`.
