---
description: "Use when writing, reviewing, or refactoring Python code, FastAPI routers, services, Pydantic schemas, dependency injection, LLM provider integrations, or abstract service patterns."
name: "Python FastAPI LLM Architecture"
applyTo: "**/*.py"
---

# Python, FastAPI & LLM Architecture Standards

## Python

- Use type annotations on all function signatures and class attributes (PEP 484)
- Prefer `str | None` union syntax (Python 3.10+) over `Optional[str]`
- Name classes `PascalCase`, functions and variables `snake_case`, constants `UPPER_SNAKE_CASE`
- Keep functions small and single-purpose (SRP). If a function does more than one thing, split it
- Prefer composition over inheritance; use ABC only when a genuine contract is needed
- Never use mutable default arguments (`def f(items=[])` is a bug)
- Use `dataclasses` or Pydantic models for data containers; avoid plain dicts as public interfaces
- Raise specific exceptions, never bare `except:` or `except Exception:` without re-raising or logging
- Use `logging` module, never `print()` in production code

## FastAPI

- Routers handle only HTTP concerns: parse request, call service, return response
- Business logic lives exclusively in the service layer, never in routers or schemas
- Define one `APIRouter` per domain resource; mount routers in the app factory
- Use Pydantic `BaseModel` for all request bodies and response models — never raw dicts
- Separate request schemas from response schemas even if they look similar
- Use `Depends()` for all shared resources: DB sessions, config, auth, service instances
- Mark I/O-bound endpoint handlers as `async def`; CPU-bound work goes in a thread pool via `run_in_executor`
- Return `HTTPException` with explicit `status_code` and a human-readable `detail`
- Use `response_model=` on every route so the contract is explicit and docs are accurate
- Version the API in the router prefix (`/v1/...`), not in function names

## LLM Service Layer

- Define an abstract base class (`ABC`) that declares the provider contract; concrete classes implement it
- The factory/selector that resolves the provider must be the only place that knows which provider is active
- System prompts are part of the service layer, never constructed in routers or controllers
- Standardize the return type across all providers into a single internal schema (model, content, token counts, cost)
- Token counting and cost estimation belong inside the service, not the caller
- Handle provider-specific errors (rate limits, context length, auth) in the concrete class and re-raise as domain exceptions
- Never log raw API responses that may contain sensitive user data
- Store provider credentials only in environment variables; never hardcode or default to real keys

## Project Layout

- `app/main.py` — App factory, router registration, lifespan
- `app/config.py` — Settings via pydantic-settings BaseSettings
- `app/routers/` — One file per domain resource
- `app/services/` — Business logic and external integrations
- `app/schemas/` — Pydantic request/response models if complex enough to separate
- `app/context/` — Prompt templates, CAG examples, static context
- `tests/unit/` — Pure logic, no I/O, fast
- `tests/integration/` — Real HTTP via TestClient or httpx.AsyncClient

## Testing

- Unit tests must not call external APIs or the filesystem
- Use `pytest` fixtures for reusable setup; avoid `setUp/tearDown` class methods
- Mock at the boundary of the system under test, not deep inside implementation
- Each test covers one behavior; test name describes the scenario: `test_<unit>_<scenario>_<expected>`