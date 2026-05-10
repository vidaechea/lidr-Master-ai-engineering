# estimator-cag

REST API that generates software effort estimates from meeting transcriptions. It implements a **Context-Augmented Generation (CAG)** approach: curated reference examples are injected into the system prompt so the model always produces structured, consistent estimates.

## Features

- **CAG pipeline** — static estimation examples in the system prompt; the model always returns a coherent format.
- **Multi-provider support** — OpenAI and Anthropic, switchable via environment variable.
- **Multi-turn sessions** — continuous conversation; context is preserved across turns.
- **Pre-call requirements extraction** — optional step that distils the raw transcript into structured requirements before estimating.
- **Redis cache** — identical requests are served from cache without calling the LLM.
- **Token and cost tracking** — every response includes token counts and per-turn / cumulative USD cost.
- **Streamlit chat UI** — web interface to paste transcriptions and receive estimates without writing code.

## Project structure

```
estimator-cag/
├── app/                  # FastAPI application
│   ├── routers/          # REST endpoints
│   ├── services/         # LLM logic, cache, helpers
│   └── prompts/          # Jinja2 templates and CAG examples
├── tests/                # Unit and integration tests
├── streamlit_app.py      # Chat UI entry point
├── docker-compose.yml    # API + Redis (Streamlit runs locally)
├── main.py               # Uvicorn entry point
└── pyproject.toml
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/examples` | Returns the CAG reference examples loaded into the prompt |
| `POST` | `/api/v1/estimate` | Generates an effort estimate from a meeting transcription |

### `POST /api/v1/estimate`

**Request body**

```json
{
  "transcription": "<meeting transcription or project description>"
}
```

**Response body**

```json
{
  "estimation": "## Estimate: ...",
  "model": "gpt-4o-mini",
  "input_tokens": 620,
  "output_tokens": 310,
  "turn_cost_usd": 0.000279,
  "total_cost_usd": 0.000279,
  "cache_hit": false
}
```

**Error responses**

| Status | Condition |
|--------|-----------|
| `413` | Estimated input tokens exceed the model's context window |
| `422` | `transcription` field missing from the request body |
| `500` | LLM provider returned an unexpected error |

## Setup

### 1. Configure environment variables

Create a `.env` file inside `estimator-cag/`:

```env
# Provider: openai | anthropic
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...   # uncomment if using Anthropic

# Redis cache (optional)
CACHE_ENABLED=true
```

### 2. Run with Docker Compose

```bash
cd estimator-cag
docker compose up --build
```

This starts the FastAPI backend and a Redis container.

- **API + interactive docs**: http://localhost:8000/docs

### 3. Run the Streamlit UI locally

Streamlit runs outside Docker to avoid WebSocket issues with Docker Desktop on Windows.

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
cd estimator-cag
uv sync
uv run streamlit run streamlit_app.py        # UI at http://localhost:8501
```

### Local execution (without Docker)

```bash
cd estimator-cag
uv sync
uv run python main.py                        # API at http://localhost:8000
uv run streamlit run streamlit_app.py        # UI  at http://localhost:8501
```

## Tests

```bash
uv run pytest tests/ -v
```
