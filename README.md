# lidr-Master-ai-Engineering

**Estimator** — AI-powered software effort estimation platform.

Repository by **Luis Vidaechea** — **Master AI Engineering** program at [LIDR](https://lidr.es).

---

## What is Estimator?

Estimator is a web application that generates software development effort estimates by analyzing meeting transcriptions using AI. It uses **Context-Augmented Generation (CAG)** to inject curated reference examples into prompts, ensuring consistent and well-structured estimates.

### Key Features

- 🎯 **Automatic estimation** from meeting transcriptions
- 🧠 **Multi-model LLM**: OpenAI, Anthropic (via LiteLLM)
- ⚡ **Smart caching** with Redis (TTL 24h)
- 💰 **Cost tracking** per call and session
- 🔐 **JWT authentication** and PostgreSQL persistence
- 📊 **Complete REST API** with Swagger/OpenAPI
- 🎨 **Modern Angular UI** with responsive design
- 🤖 **Async processing** with ARQ worker
- 🎯 **Tier-based adaptive prompts**: Developer / PM / Executive audiences receive distinct, role-specific system prompts selected automatically from the JWT claim

---

## 🚀 Quick Start

### Requirements
- Docker and Docker Compose
- API Keys: `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`

### Starting the Application

1. **Clone and configure environment variables**
   ```bash
   git clone https://github.com/vidaechea/lidr-Master-ai-engineering.git
   cd lidr-Master-ai-engineering
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Start all services**
   ```bash
   docker compose up --build
   ```

3. **Run database migrations** (first time, in another terminal)
   ```bash
   docker compose exec backend alembic upgrade head
   ```

4. **Access the application**
   - 🖥️ Frontend: http://localhost:4200
   - 📡 Backend API: http://localhost:8000/docs (Swagger)
   - 🧠 AI Engine: http://localhost:8001/docs (Swagger)

---

## 📚 Component Documentation

| Component | Description | Documentation |
|---|---|---|
| **Frontend** | Angular SPA for user interface | [→ frontend/README.md](frontend/README.md) |
| **Backend** | Business API, authentication, persistence | [→ backend/README.md](backend/README.md) |
| **AI Engine** | LLM engine, estimations, caching | [→ ai-engine/README.md](ai-engine/README.md) |
| **Notebooks** | OpenAI/Anthropic API clients, interactive examples | [→ notebooks/README.md](notebooks/README.md) |

---

## 🏗️ System Architecture

The main project consists of four services orchestrated with Docker Compose:

```
┌─────────────────────────────────────────────────────────────────┐
│                        docker-compose.yml                        │
│                                                                  │
│  ┌──────────────┐   REST    ┌──────────────┐   HTTP             │
│  │   frontend   │ ────────► │   backend    │ ──────►  ai-engine │
│  │  Angular SPA │  :4200    │  FastAPI API │  :8001  FastAPI    │
│  │   :4200→80   │           │    :8000     │         (internal)  │
│  └──────────────┘           └──────────────┘                    │
│                                    │                  │          │
│                              ┌─────┴──────┐    ┌─────┴──────┐  │
│                              │ PostgreSQL │    │   Redis    │  │
│                              │   :5432    │    │   :6379    │  │
│                              └────────────┘    └────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

| Service | Directory | Port | Responsibility |
|---|---|---|---|
| `frontend` | `frontend/` | 4200 | Angular SPA — user interface |
| `backend` | `backend/` | 8000 | Business API — auth, projects, persistence |
| `ai-engine` | `ai-engine/` | 8001 | LLM engine — estimation generation |
| `ai-engine-worker` | `ai-engine/` | — | ARQ worker — async estimations |
| `postgres` | — | 5432 | Main database |
| `redis` | — | 6379 | Cache and job queue |

---

## Repository Structure

```
lidr-Master-ai-engineering/
├── docker-compose.yml        # Complete services orchestration
├── .env                      # Environment variables (local, not versioned)
│
├── backend/                  # Business API (FastAPI + PostgreSQL)
│   ├── app/
│   │   ├── main.py           # App factory, router registration
│   │   ├── config.py         # Settings (pydantic-settings)
│   │   ├── models/           # SQLAlchemy ORM (User, Project, Estimation)
│   │   ├── routers/          # auth, projects, estimations, internal
│   │   ├── schemas/          # Pydantic request/response
│   │   ├── services/         # Business logic + HTTP client to ai-engine
│   │   └── dependencies.py   # get_db, get_current_user (Depends)
│   ├── alembic/              # Database migrations
│   └── tests/
│       ├── unit/             # test_auth_service, test_estimation_service
│       └── integration/      # test_auth, test_projects, test_estimations
│
├── ai-engine/               # AI Engine (FastAPI + LiteLLM + Redis)
│   ├── app/
│   │   ├── main.py           # App factory
│   │   ├── routers/          # estimations, cache_metrics, internal
│   │   ├── services/         # estimation_service, litellm_service, cache_service
│   │   ├── prompts/          # Jinja2 templates v1/v2 + CAG examples
│   │   └── worker.py         # ARQ worker for async estimations
│   ├── streamlit_app.py      # Demo chat UI
│   └── tests/
│       ├── unit/             # test_auth_service, test_cost_calculator, etc.
│       └── integration/      # test_estimations, test_litellm_estimations
│
├── frontend/                 # Angular 21 SPA
│   └── src/app/
│       ├── features/         # auth/, projects/, estimations/
│       └── core/             # guards, interceptors, shared services
│
└── notebooks/                # Session 01 — OpenAI and Anthropic clients
    ├── *.py                  # Reusable Python scripts
    └── *.ipynb               # Jupyter notebooks
```

---

## Components in Detail

### `backend/` — Business API

FastAPI application that exposes application resources to the frontend and acts as a gateway to the AI engine. **Does not contain LLM logic**.

**Responsibilities:**
- JWT authentication (signup, login, refresh) and OAuth2 (Google/Microsoft)
- Per-user project CRUD
- Estimation creation and persistence (state: `pending → processing → completed/failed`)
- Synchronous and asynchronous proxy to `ai-engine`
- Callback endpoint that receives ARQ worker results

**Main Endpoints:**

| Method | Route | Description |
|---|---|---|
| `POST` | `/v1/auth/register` | Register with email/password |
| `POST` | `/v1/auth/login` | Login → access + refresh tokens |
| `POST` | `/v1/auth/refresh` | Refresh access token |
| `GET/POST` | `/v1/projects` | List / create projects |
| `GET/PATCH/DELETE` | `/v1/projects/{id}` | Detail, update, delete |
| `GET/POST` | `/v1/estimations` | List / create estimation (sync) |
| `POST` | `/v1/estimations/async` | Create async estimation (→ job_id) |
| `GET` | `/v1/estimations/{id}/status` | Poll estimation status |
| `POST` | `/v1/internal/estimation-callback` | ARQ worker callback |

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 async · PostgreSQL · Alembic · python-jose · httpx · ARQ

---

### `ai-engine/` — AI Engine

Internal service that receives a meeting transcription and returns effort estimation in markdown and/or structured format. Implements **Context-Augmented Generation (CAG)**: curated reference examples are injected into the system prompt to guide the model.

**Responsibilities:**
- CAG pipeline: build system prompt with examples + call LLM + validate result
- **Tier-based adaptive prompts**: resolves `estimation/{tier}/{version}/system.j2` based on the `tier` JWT claim — `developer`, `pm`, or `executive`
- Multi-model routing via LiteLLM (OpenAI, Anthropic)
- Exact caching with Redis (SHA-256 key on transcription + params, TTL 24h)
- Cost calculation per call (MODEL_REGISTRY with per-token pricing)
- ARQ worker for async estimations with callback to backend

**Supported Models:**

| Provider | Models |
|---|---|
| OpenAI | `gpt-4o-mini`, `gpt-5.4-mini`, `gpt-5.4`, `o3-mini`, `o4-mini` |
| Anthropic | `claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-7` |

**Internal Endpoints:**

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/v1/estimate` | Sync estimation |
| `POST` | `/api/v1/estimate/structured` | Estimation with structured output |
| `POST` | `/api/v1/internal/estimate/async` | Enqueue async estimation |
| `GET` | `/api/v1/examples` | List CAG examples |
| `GET` | `/api/v1/cache/metrics` | Cache metrics (hits, misses, cost saved) |

**Stack:** Python 3.12 · FastAPI · LiteLLM · Redis · ARQ · Jinja2 · Streamlit (demo UI)

---

### `frontend/` — Angular SPA

User interface that consumes the `backend` API. Built with Angular 21.

**Business Modules (`src/app/features/`):**
- `auth/` — login, signup, token management
- `projects/` — projects list and detail
- `estimations/` — estimation creation, results visualization

**Stack:** Angular 21 · TypeScript · SCSS · nginx (production)

---

### `notebooks/` — Session 01

Minimal, reusable Python clients for OpenAI and Anthropic with cost tracking and support for Google Colab and local environment. Includes interactive Jupyter notebooks with examples.

---

## 🛠️ Full Project Setup

### Requirements
- Docker and Docker Compose
- API Keys: `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`

### Using with Codespaces

This repository includes Dev Container configuration in `.devcontainer/` for GitHub Codespaces to automatically prepare the environment.

Detailed documentation: [`.devcontainer/README.md`](.devcontainer/README.md).

When creating (or rebuilding) the Codespace, `postCreate.sh` is executed, which installs:
- System dependencies for running Angular tests with Playwright/Chromium
- `uv` for Python environment/dependency management
- `backend/` and `ai-engine/` dependencies with `uv sync`
- `frontend/` dependencies with `npm ci` and Chromium binary

Recommended commands to validate the environment in a new Codespace:

```bash
# Frontend (Angular + Vitest + Playwright)
cd application-web/frontend
npm test -- --watch=false --browsers=chromium

# Backend (FastAPI)
cd ../../application-web/backend
uv run pytest tests/ -v

# AI Engine (FastAPI + LiteLLM)
cd ../ai-engine
uv run pytest tests/ -v
```

#### Troubleshooting (Codespaces)

If frontend tests fail with Playwright/Chromium errors (e.g., `libatk-1.0.so.0: cannot open shared object file`):

```bash
cd application-web/frontend
npx playwright install-deps chromium
npx playwright install chromium
npm test -- --watch=false --browsers=chromium
```

If you encounter `apt/dpkg` lock errors (`Could not get lock /var/lib/dpkg/lock-frontend`), wait for the active process and retry:

```bash
sudo apt-get -o DPkg::Lock::Timeout=600 update
sudo apt-get -o DPkg::Lock::Timeout=600 --fix-missing install
```

### Environment Variables

Create a `.env` file in the repository root:

```env
# LLM
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Security
SECRET_KEY=change_this_in_production
INTERNAL_API_KEY=change_this_too

# Database (optional — defaults work with Docker)
POSTGRES_USER=estimator
POSTGRES_PASSWORD=estimator_dev
POSTGRES_DB=estimator
```

### Starting All Services

```bash
# Build images and start all services
docker compose up --build

# In the background (detached)
docker compose up --build -d
```

If you change `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB` after the first startup, the Postgres container won't reapply those values to an already-initialized volume. In that case, the backend may continue trying to connect with the new credentials while Postgres keeps the old ones.

For a local environment without data to preserve, restart the database from scratch:

```bash
docker compose down -v
docker compose up --build
```

If you need to preserve data, change the Postgres user password inside Postgres to match your current `.env` instead of deleting the volume.

| URL | Service |
|---|---|
| http://localhost:4200 | Angular Frontend |
| http://localhost:8000/docs | Backend API — Swagger UI |
| http://localhost:8000/health | Backend healthcheck |

### Running Migrations (first time)

```bash
# Option 1: with Docker Compose (recommended if you started the stack with Docker)
docker compose exec backend alembic upgrade head

# Option 2: locally (outside Docker)
cd application-web/backend
uv run alembic upgrade head
```

### Creating a New Migration

```bash
# Option 1: with Docker Compose
docker compose exec backend alembic revision --autogenerate -m "description_of_change"

# Option 2: locally (outside Docker)
cd application-web/backend
uv run alembic revision --autogenerate -m "description_of_change"
```

### Other Useful Commands

```bash
# Start only infrastructure (postgres + redis)
docker compose up postgres redis

# Start only the AI engine with its worker
docker compose up --build ai-engine ai-engine-worker

# View logs in real time (all services or specific one)
docker compose logs -f
docker compose logs -f ai-engine

# Stop containers
docker compose down

# Stop and delete volumes (removes postgres and redis data)
docker compose down -v

# Rebuild a service without touching others
docker compose up --build frontend
```

---

## 🧪 Testing

### Backend

```bash
cd application-web/backend
uv run pytest tests/ -v
```

Tests use in-memory SQLite — no PostgreSQL or active `ai-engine` required. HTTP calls to the AI engine are mocked.

### AI Engine

```bash
cd ai-engine

# Family 1 — Hard determinism (fast, no API keys needed)
uv run pytest tests/unit/ tests/integration/ -v

# Exclude slow tests explicitly
uv run pytest tests/ -m "not slow" -v

# Family 2 — Soft determinism (requires API keys, ~9 LLM calls)
uv run pytest tests/evals/test_soft_determinism.py -m "slow and llm_live" -v

# Family 3 — LLM-as-judge via DeepEval (~12 LLM calls)
uv run pytest tests/evals/test_llm_judge.py -m "slow and llm_live" -v

# Full eval suite (pre-merge)
uv run pytest tests/ -m "slow and llm_live" -v
```

---

## 📋 Conventions

- Secrets never versioned (`.env` in `.gitignore`)
- Master program sessions in `session0X/` directories
- One `APIRouter` per domain resource
- Business logic exclusively in the services layer, never in routers

---

## 👤 Author

**Luis Vidaechea** — Master AI Engineering, LIDR

## 📄 License

MIT

---

*Last update: May 17, 2026*

