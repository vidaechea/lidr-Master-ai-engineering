# Estimator CAG

A REST API service that generates software effort estimates from meeting transcriptions using OpenAI language models. It follows a **Context-Augmented Generation (CAG)** approach: static reference examples are injected into the system prompt at startup to guide the model's output format and level of detail.

---

## Features

- **CAG pipeline** — curated estimation examples are embedded in the system prompt so the model always produces structured, consistent estimates.
- **Pre-call token forecasting** — estimates input tokens before calling the API; returns HTTP 413 if the context window would be exceeded.
- **Cost accounting** — tracks input/output token counts and computes per-turn and cumulative USD cost.
- **Multi-provider support** — OpenAI (Responses API) and Anthropic (Messages API); the routing layer handles each provider's differences automatically.
- **Multi-turn sessions** — optional conversation continuation. OpenAI uses server-side `previous_response_id`; Anthropic replays the full history on every call (stateless).
- **Provider-specific multi-turn** — Anthropic history is stored client-side and grows turn-by-turn; `reset()` starts a new thread.

---

## Project structure

```
estimator-cag/
├── app/
│   ├── main.py               # FastAPI application factory
│   ├── config.py             # Settings loaded from .env
│   ├── context/
│   │   └── examples.py       # CAG static examples injected into the system prompt
│   ├── routers/
│   │   └── estimations.py    # POST /estimations/ and GET /estimations/examples
│   └── services/
│       ├── base_llm_service.py        # Abstract base with shared estimation pipeline
│       ├── openai_llm_service.py      # OpenAI implementation (Responses API)
│       └── anthropic_llm_service.py   # Anthropic implementation (Messages API, stateless multi-turn)
├── tests/
│   ├── integration/          # HTTP-level tests via FastAPI TestClient
│   └── unit/                 # Unit tests for the LLM service and examples module
├── main.py                   # Uvicorn entry point
├── pyproject.toml
└── requirements.txt
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/estimations/examples` | Returns the CAG reference examples |
| `POST` | `/estimations/` | Generates an effort estimate from a meeting transcription |

### `POST /estimations/`

**Request body**
```json
{
  "description": "<meeting transcription or project description>"
}
```

**Response body**
```json
{
  "estimation": "## Estimate: ...",
  "model": "gpt-4o-mini",
  "input_tokens": 620,
  "output_tokens": 310,
  "reasoning_tokens": null,
  "turn_cost_usd": 0.000279,
  "total_cost_usd": 0.000279,
  "response_id": "resp_abc123",
  "estimated_input_tokens": 615,
  "estimated_precall_cost_usd": 0.0000923
}
```

**Error responses**

| Status | Condition |
|--------|-----------|
| `413` | Estimated input tokens exceed the model's context window |
| `422` | `description` field missing from request body |
| `500` | OpenAI API returned a non-completed response status |

---

## Supported models

| Model | Input ($/1M tokens) | Output ($/1M tokens) | Context window | Reasoning |
|-------|--------------------|--------------------|----------------|-----------|
| `gpt-3.5-turbo` | $0.50 | $1.50 | 16 385 | No |
| `gpt-4-turbo` | $10.00 | $30.00 | 128 000 | No |
| `gpt-4o-mini` | $0.15 | $0.60 | 128 000 | No |
| `gpt-5.4-mini` | $0.75 | $4.50 | 128 000 | No |
| `gpt-5.4` | $2.50 | $15.00 | 128 000 | No |
| `o3-mini` | $1.10 | $4.40 | 200 000 | Yes |
| `o3` | $10.00 | $40.00 | 200 000 | Yes |
| `o4-mini` | $1.10 | $4.40 | 200 000 | Yes |
| `o4-mini-2025-04-16` | $1.10 | $4.40 | 200 000 | Yes |

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- An OpenAI or Anthropic API key (depending on which provider you use)

### Install dependencies

```bash
uv sync
```

### Environment variables

Create a `.env` file in the `estimator-cag/` directory:

**OpenAI (default)**

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini   # optional, this is the default
APP_ENV=development
LOG_LEVEL=DEBUG
```

**Anthropic**

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-6   # optional, this is the Anthropic default
APP_ENV=development
LOG_LEVEL=DEBUG
```

Set `LLM_PROVIDER` to `openai` or `anthropic` to switch between providers. When using OpenAI, `OPENAI_API_KEY` is required; when using Anthropic, `ANTHROPIC_API_KEY` is required.

### Run the server

```bash
uv run python main.py
```

The API will be available at `http://127.0.0.1:8000`. Interactive docs at `http://127.0.0.1:8000/docs`.

Environment overrides for the server:

```env
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8080
UVICORN_RELOAD=true
```

---

## Running tests

```bash
uv run pytest tests/ -v
```

The test suite covers 115 cases across unit and integration layers. All external API calls are mocked.
