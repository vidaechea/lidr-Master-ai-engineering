# Estimator AI

A REST API service that generates software effort estimates from meeting transcriptions using OpenAI language models. It follows a **Context-Augmented Generation (CAG)** approach: static reference examples are injected into the system prompt at startup to guide the model's output format and level of detail.

---

## Features

- **CAG pipeline** — curated estimation examples are embedded in the system prompt so the model always produces structured, consistent estimates.
- **Pre-call token forecasting** — estimates input tokens before calling the API; returns HTTP 413 if the context window would be exceeded.
- **Cost accounting** — tracks input/output token counts and computes per-turn and cumulative USD cost.
- **Multi-provider support** — OpenAI (Responses API) and Anthropic (Messages API); the routing layer handles each provider's differences automatically.
- **Multi-turn sessions** — optional conversation continuation. OpenAI uses server-side `previous_response_id`; Anthropic replays the full history on every call (stateless).
- **Provider-specific multi-turn** — Anthropic history is stored client-side and grows turn-by-turn; `reset()` starts a new thread.
- **Pre-call requirements extraction** — optional first LLM call that distills the raw transcript into structured requirements before the main estimation call.
- **Exact-match Redis cache** — optional caching layer that returns stored results for identical requests without calling the LLM. Cache key is a SHA-256 hash of the full input + all relevant parameters; a TTL of 24 h is applied by default. Every response includes a `cache_hit` field.
- **Streamlit chat UI** — interactive chat interface to paste transcripts and receive estimates directly in the browser, with full token/cost metadata per response.

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
│   │   └── estimations.py    # POST /api/v1/estimate and GET /api/v1/examples
│   └── services/
│       ├── base_llm_service.py        # Abstract base with shared estimation pipeline
│       ├── openai_llm_service.py      # OpenAI implementation (Responses API)
│       ├── anthropic_llm_service.py   # Anthropic implementation (Messages API, stateless multi-turn)
│       ├── cache_service.py           # CachedLLMService decorator (Redis exact-match cache)
│       └── factory.py                 # Provider factory; wraps service with cache when enabled
├── tests/
│   ├── integration/          # HTTP-level tests via FastAPI TestClient
│   └── unit/                 # Unit tests for the LLM service and examples module
├── main.py                   # Uvicorn entry point
├── streamlit_app.py          # Streamlit chat UI entry point
├── docker-compose.yml        # App + Redis services
├── pyproject.toml
└── requirements.txt
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/examples` | Returns the CAG reference examples |
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
  "reasoning_tokens": null,
  "turn_cost_usd": 0.000279,
  "total_cost_usd": 0.000279,
  "response_id": "resp_abc123",
  "estimated_input_tokens": 615,
  "estimated_precall_cost_usd": 0.0000923,
  "cache_hit": false
}
```

**Error responses**

| Status | Condition |
|--------|-----------|
| `413` | Estimated input tokens exceed the model's context window |
| `422` | `transcription` field missing from request body |
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
- Redis 7+ (only required when `CACHE_ENABLED=true`; included in `docker-compose.yml`)

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

**Cache (optional)**

```env
CACHE_ENABLED=true
REDIS_URL=redis://localhost:6379
CACHE_TTL=86400   # seconds; default 24 h
```

When `CACHE_ENABLED=true` every `POST /api/v1/estimate` call checks Redis before hitting the LLM. Identical requests (same transcription + same parameters) return immediately with `cache_hit: true` and cost $0.

### Run with Docker Compose

The provided `docker-compose.yml` starts both the API and a Redis instance:

```bash
docker compose up --build
```

Add `CACHE_ENABLED=true` to your `.env` file to activate the cache when running via Docker.

### Run the server (local)

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

### Run the Streamlit UI

```bash
uv run streamlit run streamlit_app.py
```

The chat interface will be available at `http://localhost:8501`.

#### LLM Options panel

The sidebar expander exposes all call parameters without writing code:

| Section | Control | Description |
|---------|---------|-------------|
| **Model** | Provider selector | Switch between `openai` and `anthropic`. Changing the provider recreates the service and clears the conversation. |
| | Model selector | Lists all models registered for the active provider. Reasoning models (`o3`, `o4-mini`, `claude-opus-4-7`, …) are supported. |
| **Sampling** | Sampling parameter | Choose `temperature`, `top_p`, `top_k` (Anthropic only), or `none` (model default). Only one can be active at a time. |
| | Slider / input | Sets the selected sampling parameter value. |
| **Generation** | Output format | `markdown` (table-based), `json` (structured), or `narrative` (prose). Controls the few-shot examples injected into the system prompt. |
| | Number of examples | 0–5 few-shot examples in the system prompt. 0 = zero-shot. |
| | Max output tokens | Hard cap on generated tokens (256–32 768). |
| | Verbosity | `low`, `medium`, or `high`. Passed to providers that support it; silently ignored by others. |
| | Reasoning effort | `low`, `medium`, or `high`. Only active for reasoning models. |
| **Session** | Multi-turn toggle | Continues the conversation across messages. OpenAI uses `previous_response_id`; Anthropic replays the full history. |
| | Pre-call toggle | Runs a cheap requirements-extraction step before the main estimation call. Improves quality on long or noisy transcripts. |
| | Clear conversation | Resets session state and conversation history. |

#### Details expander (per response)

Each assistant response includes a collapsible **Details** panel with:

- **Tokens** — input, output, estimated input; reasoning and cache tokens appear only when present
- **Costs (USD)** — turn cost, total cumulative cost; pre-call costs only when pre-call is enabled
- **Run info** — model used, finish reason, truncated flag, response ID (shown when available)
- **Validation** — structural checks (title, breakdown table, totals, team, duration, finish reason) with a score percentage and numeric consistency check (declared hours/cost vs. row sums)
- **Extracted requirements** — shown when pre-call is enabled

---

## Running tests

```bash
uv run pytest tests/ -v
```

The test suite covers unit and integration layers. All external API calls are mocked.

To run only the cache tests:

```bash
uv run pytest tests/unit/test_cache_service.py -v
```
