# Backend — Business API

FastAPI application that exposes business resources to the frontend and acts as a gateway to the AI engine. Handles authentication, project management, and estimation persistence.

---

## Overview

The backend is the core business logic layer of Estimator. It provides:

- 🔐 **Authentication & Authorization** — JWT-based access control
- 📦 **Resource Management** — CRUD operations for projects and estimations
- 🔄 **State Management** — Tracks estimation lifecycle (pending → processing → completed/failed)
- 🧠 **AI Gateway** — Proxies requests to the AI engine, both sync and async
- 💾 **Persistence** — PostgreSQL with SQLAlchemy ORM and Alembic migrations
- 📊 **REST API** — Complete OpenAPI/Swagger documentation

---

## Architecture

### Folder Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # App factory, CORS, router registration
│   ├── config.py               # Settings with pydantic-settings
│   ├── database.py             # SQLAlchemy engine, session factory
│   ├── dependencies.py         # FastAPI dependency injection
│   ├── logging.py              # Structured logging setup
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py             # User model
│   │   ├── project.py          # Project model
│   │   └── estimation.py       # Estimation model
│   ├── routers/                # API route handlers
│   │   ├── __init__.py
│   │   ├── auth.py             # POST /v1/auth/*
│   │   ├── projects.py         # /v1/projects/*
│   │   ├── estimations.py      # /v1/estimations/*
│   │   └── internal.py         # /v1/internal/* (callbacks, health)
│   ├── schemas/                # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── project.py
│   │   └── estimation.py
│   └── services/               # Business logic layer
│       ├── __init__.py
│       ├── auth_service.py     # JWT, OAuth2, user signup/login
│       ├── project_service.py  # Project CRUD + filtering
│       ├── estimation_service.py # Estimation lifecycle + AI engine client
│       └── helpers/            # Utility functions
├── alembic/                    # Database migrations
│   ├── env.py                  # Migration environment setup
│   ├── script.py.mako          # Migration template
│   └── versions/               # Migration files
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Shared fixtures
│   ├── unit/
│   │   ├── test_auth_service.py
│   │   ├── test_project_service.py
│   │   └── test_estimation_service.py
│   └── integration/
│       ├── test_auth.py        # API endpoint tests
│       ├── test_projects.py
│       └── test_estimations.py
├── pyproject.toml              # Dependencies + project metadata
├── Dockerfile                  # Production image
└── alembic.ini                 # Migration config
```

---

## Key Components

### Models (`models/`)

**User** — Registered application users
- Fields: `id`, `email` (unique), `password_hash`, `created_at`, `updated_at`
- Relations: One-to-many with `Project`

**Project** — Collections of estimations per user
- Fields: `id`, `user_id` (FK), `name`, `description`, `created_at`, `updated_at`
- Relations: Many-to-one to `User`, One-to-many to `Estimation`

**Estimation** — Individual effort estimates
- Fields: `id`, `project_id` (FK), `status`, `estimation_text`, `cost_usd`, `created_at`, `completed_at`
- Status flow: `pending` → `processing` → `completed` / `failed`

### Routers (`routers/`)

| Router | Endpoints | Purpose |
|---|---|---|
| **auth.py** | `POST /v1/auth/register`, `POST /v1/auth/login`, `POST /v1/auth/refresh` | JWT authentication |
| **projects.py** | `GET /v1/projects`, `POST /v1/projects`, `GET /v1/projects/{id}`, `PATCH /v1/projects/{id}`, `DELETE /v1/projects/{id}` | Project CRUD |
| **estimations.py** | `GET /v1/estimations`, `POST /v1/estimations`, `GET /v1/estimations/{id}`, `POST /v1/estimations/async`, `GET /v1/estimations/{id}/status` | Estimation lifecycle |
| **internal.py** | `GET /health`, `POST /v1/internal/estimation-callback` | Health checks, ARQ callbacks |

### Services (`services/`)

**AuthService**
- JWT token generation and validation
- Password hashing with bcrypt
- OAuth2 integration (extensible)
- User registration and login logic

**ProjectService**
- CRUD operations with ownership validation
- Per-user filtering
- Soft delete support (if implemented)

**EstimationService**
- Calls the AI engine via httpx (sync/async)
- Manages estimation status lifecycle
- Handles ARQ worker callbacks
- Computes cost tracking

### Schemas (`schemas/`)

Request/Response Pydantic models for API endpoints:
- `UserRegister`, `UserLogin`, `TokenResponse`
- `ProjectCreate`, `ProjectUpdate`, `ProjectResponse`
- `EstimationCreate`, `EstimationResponse`, `EstimationStatusResponse`

---

## Development

### Setup

1. **Install Python 3.12+ and uv**
   ```bash
   # macOS with Homebrew
   brew install uv
   
   # Or via pip
   pip install uv
   ```

2. **Install dependencies**
   ```bash
   cd backend
   uv sync
   ```

3. **Create `.env`** (or copy from root `.env`)
   ```bash
   cp ../.env.example .env
   ```

4. **Setup database** (first time)
   ```bash
   uv run alembic upgrade head
   ```

### Running Locally

**Start the API server**
```bash
uv run fastapi run app/main.py --reload
```

The API will be available at:
- 🌐 http://localhost:8000
- 📖 Swagger UI: http://localhost:8000/docs
- 📖 ReDoc: http://localhost:8000/redoc

### Running Tests

```bash
# All tests
uv run pytest tests/ -v

# Only unit tests
uv run pytest tests/unit/ -v

# Only integration tests
uv run pytest tests/integration/ -v

# Specific test
uv run pytest tests/unit/test_auth_service.py -v

# With coverage
uv run pytest tests/ --cov=app --cov-report=html
```

**Note:** Tests use in-memory SQLite. No PostgreSQL or AI engine required. HTTP calls are mocked.

### Database Migrations

**Create a new migration**
```bash
uv run alembic revision --autogenerate -m "add_user_email_index"
```

**Apply pending migrations**
```bash
uv run alembic upgrade head
```

**Downgrade one migration**
```bash
uv run alembic downgrade -1
```

**View migration history**
```bash
uv run alembic history
```

---

## Stack

| Component | Version | Purpose |
|---|---|---|
| Python | 3.12 | Language |
| FastAPI | 0.104+ | Web framework |
| Uvicorn | 0.24+ | ASGI server |
| SQLAlchemy | 2.0+ | ORM |
| PostgreSQL | 15+ | Database |
| Alembic | 1.12+ | Migrations |
| Pydantic | 2.0+ | Data validation |
| python-jose | 3.3+ | JWT tokens |
| passlib | 1.7+ | Password hashing |
| httpx | 0.25+ | HTTP client (async) |
| pytest | 7.4+ | Testing |

---

## Dependencies

See `pyproject.toml` for the complete list. Key dependencies:

- `fastapi` — Web framework
- `sqlalchemy` — ORM
- `psycopg` — PostgreSQL adapter
- `pydantic-settings` — Configuration management
- `python-multipart` — Form data parsing
- `pytest`, `pytest-asyncio` — Testing

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | No | `postgresql://estimator:estimator_dev@localhost:5432/estimator` | PostgreSQL connection string |
| `SECRET_KEY` | Yes | — | JWT signing key (change in production!) |
| `INTERNAL_API_KEY` | Yes | — | Internal API authentication key |
| `AI_ENGINE_URL` | No | `http://localhost:8001` | AI engine base URL |
| `LOG_LEVEL` | No | `INFO` | Logging level |

---

## API Endpoints

### Authentication

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/auth/register` | Register new user |
| `POST` | `/v1/auth/login` | Login, get access + refresh tokens |
| `POST` | `/v1/auth/refresh` | Refresh access token |

**Example: Login**
```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"securepass"}'
```

### Projects

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/projects` | List user's projects |
| `POST` | `/v1/projects` | Create new project |
| `GET` | `/v1/projects/{id}` | Get project detail |
| `PATCH` | `/v1/projects/{id}` | Update project |
| `DELETE` | `/v1/projects/{id}` | Delete project |

### Estimations

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/estimations` | List estimations (all or filtered) |
| `POST` | `/v1/estimations` | Create estimation (sync) |
| `GET` | `/v1/estimations/{id}` | Get estimation detail |
| `POST` | `/v1/estimations/async` | Create estimation (async, returns job_id) |
| `GET` | `/v1/estimations/{id}/status` | Poll async estimation status |

### Health & Internal

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/v1/internal/estimation-callback` | ARQ worker callback (internal) |

---

## Conventions

- ✅ **Services handle all business logic** — routers are thin, just HTTP wrappers
- ✅ **Dependency injection for database sessions** — via `Depends(get_db)`
- ✅ **Async/await throughout** — non-blocking operations
- ✅ **Type hints on all functions** — for IDE support and clarity
- ✅ **Pydantic schemas for validation** — no unvalidated input to services
- ✅ **Structured logging** — not plain `print()`

---

## Related Documentation

- [Main README](../README.md) — Project overview
- [AI Engine README](../ai-engine/README.md) — LLM estimation engine
- [Frontend README](../frontend/README.md) — Angular UI
- [FastAPI docs](https://fastapi.tiangolo.com) — Framework reference
- [SQLAlchemy docs](https://docs.sqlalchemy.org) — ORM reference

---

## License

MIT
