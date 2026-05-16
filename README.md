# lidr-Master-ai-Engineering

Repositorio del estudiante **Luis Vidaechea** — programa **Master AI Engineering** de [LIDR](https://lidr.es).

Contiene el proyecto principal **Estimator** — una plataforma completa de estimación de esfuerzo software basada en IA — y los ejercicios de sesiones del máster.

---

## Arquitectura del sistema

El proyecto principal está compuesto por cuatro servicios que se orquestan con Docker Compose:

```
┌─────────────────────────────────────────────────────────────────┐
│                        docker-compose.yml                        │
│                                                                  │
│  ┌──────────────┐   REST    ┌──────────────┐   HTTP             │
│  │   frontend   │ ────────► │   backend    │ ──────►  ai-engine │
│  │  Angular SPA │  :4200    │  FastAPI API │  :8001  FastAPI    │
│  │   :4200→80   │           │    :8000     │         (interno)  │
│  └──────────────┘           └──────────────┘                    │
│                                    │                  │          │
│                              ┌─────┴──────┐    ┌─────┴──────┐  │
│                              │ PostgreSQL │    │   Redis    │  │
│                              │   :5432    │    │   :6379    │  │
│                              └────────────┘    └────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

| Servicio | Directorio | Puerto | Responsabilidad |
|---|---|---|---|
| `frontend` | `frontend/` | 4200 | SPA Angular — interfaz de usuario |
| `backend` | `backend/` | 8000 | API de negocio — auth, proyectos, persistencia |
| `ai-engine` | `estimator-cag/` | 8001 | Motor LLM — generación de estimaciones |
| `ai-engine-worker` | `estimator-cag/` | — | Worker ARQ — estimaciones asíncronas |
| `postgres` | — | 5432 | Base de datos principal |
| `redis` | — | 6379 | Caché y cola de trabajos |

---

## Estructura del repositorio

```
lidr-Master-ai-engineering/
├── docker-compose.yml        # Orquestación completa de todos los servicios
├── .env                      # Variables de entorno (local, no versionado)
│
├── backend/                  # API de negocio (FastAPI + PostgreSQL)
│   ├── app/
│   │   ├── main.py           # Factory de la app, registro de routers
│   │   ├── config.py         # Settings (pydantic-settings)
│   │   ├── models/           # ORM SQLAlchemy (User, Project, Estimation)
│   │   ├── routers/          # auth, projects, estimations, internal
│   │   ├── schemas/          # Pydantic request/response
│   │   ├── services/         # Lógica de negocio + cliente HTTP al ai-engine
│   │   └── dependencies.py   # get_db, get_current_user (Depends)
│   ├── alembic/              # Migraciones de base de datos
│   └── tests/
│       ├── unit/             # test_auth_service, test_estimation_service
│       └── integration/      # test_auth, test_projects, test_estimations
│
├── estimator-cag/            # Motor de IA (FastAPI + LiteLLM + Redis)
│   ├── app/
│   │   ├── main.py           # Factory de la app
│   │   ├── routers/          # estimations, cache_metrics, internal
│   │   ├── services/         # estimation_service, litellm_service, cache_service
│   │   ├── prompts/          # Plantillas Jinja2 v1/v2 + ejemplos CAG
│   │   └── worker.py         # Worker ARQ para estimaciones asíncronas
│   ├── streamlit_app.py      # Chat UI de demostración
│   └── tests/
│       ├── unit/             # test_auth_service, test_cost_calculator, etc.
│       └── integration/      # test_estimations, test_litellm_estimations
│
├── frontend/                 # SPA Angular 21
│   └── src/app/
│       ├── features/         # auth/, projects/, estimations/
│       └── core/             # guards, interceptors, servicios compartidos
│
└── session01/                # Ejercicios Sesión 01 — clientes OpenAI y Anthropic
    ├── *.py                  # Scripts Python reutilizables
    └── *.ipynb               # Notebooks Jupyter
```

---

## Componentes en detalle

### `backend/` — API de negocio

API FastAPI que expone los recursos de la aplicación al frontend y actúa como gateway hacia el motor de IA. **No contiene lógica LLM**.

**Responsabilidades:**
- Autenticación JWT (registro, login, refresh) y OAuth2 (Google/Microsoft)
- CRUD de proyectos por usuario
- Creación y persistencia de estimaciones (estado: `pending → processing → completed/failed`)
- Proxy síncrono y asíncrono al `ai-engine`
- Endpoint de callback que recibe resultados del worker ARQ

**Endpoints principales:**

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/v1/auth/register` | Registro con email/contraseña |
| `POST` | `/v1/auth/login` | Login → access + refresh tokens |
| `POST` | `/v1/auth/refresh` | Renovar access token |
| `GET/POST` | `/v1/projects` | Listar / crear proyectos |
| `GET/PATCH/DELETE` | `/v1/projects/{id}` | Detalle, actualizar, eliminar |
| `GET/POST` | `/v1/estimations` | Listar / crear estimación (síncrona) |
| `POST` | `/v1/estimations/async` | Crear estimación asíncrona (→ job_id) |
| `GET` | `/v1/estimations/{id}/status` | Polling del estado de una estimación |
| `POST` | `/v1/internal/estimation-callback` | Callback del worker ARQ |

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 async · PostgreSQL · Alembic · python-jose · httpx · ARQ

---

### `estimator-cag/` — Motor de IA

Servicio interno que recibe una transcripción de reunión y devuelve una estimación de esfuerzo en markdown y/o formato estructurado. Implementa **Context-Augmented Generation (CAG)**: ejemplos de referencia curados se inyectan en el system prompt para guiar al modelo.

**Responsabilidades:**
- Pipeline CAG: construir system prompt con ejemplos + llamar al LLM + validar resultado
- Enrutamiento multi-modelo vía LiteLLM (OpenAI, Anthropic)
- Caché exacta con Redis (clave SHA-256 sobre transcripción + parámetros, TTL 24h)
- Cálculo de coste por llamada (MODEL_REGISTRY con precios por token)
- Worker ARQ para estimaciones asíncronas con callback al backend

**Modelos soportados:**

| Proveedor | Modelos |
|---|---|
| OpenAI | `gpt-4o-mini`, `gpt-5.4-mini`, `gpt-5.4`, `o3-mini`, `o4-mini` |
| Anthropic | `claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-7` |

**Endpoints internos:**

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v1/estimate` | Estimación síncrona |
| `POST` | `/api/v1/estimate/structured` | Estimación con salida estructurada |
| `POST` | `/api/v1/internal/estimate/async` | Encolar estimación asíncrona |
| `GET` | `/api/v1/examples` | Listar ejemplos CAG |
| `GET` | `/api/v1/cache/metrics` | Métricas de caché (hits, misses, coste evitado) |

**Stack:** Python 3.12 · FastAPI · LiteLLM · Redis · ARQ · Jinja2 · Streamlit (demo UI)

---

### `frontend/` — SPA Angular

Interfaz de usuario que consume la API del `backend`. Construida con Angular 21.

**Módulos de negocio (`src/app/features/`):**
- `auth/` — login, registro, gestión de tokens
- `projects/` — lista y detalle de proyectos
- `estimations/` — creación de estimaciones, visualización de resultados

**Stack:** Angular 21 · TypeScript · SCSS · nginx (producción)

---

### `session01/` — Ejercicios Sesión 01

Clientes Python mínimos y reutilizables para OpenAI y Anthropic, con tracking de costes y soporte para Google Colab y entorno local. Incluye notebooks Jupyter con ejemplos interactivos.

---

## Levantar el proyecto completo

### Requisitos
- Docker y Docker Compose
- Claves de API: `OPENAI_API_KEY` y/o `ANTHROPIC_API_KEY`

### Uso en Codespaces

Este repositorio incluye configuración de Dev Container en `.devcontainer/` para que GitHub Codespaces prepare el entorno automáticamente.

Al crear (o reconstruir) el Codespace se ejecuta `postCreate.sh`, que instala:
- Dependencias de sistema para ejecutar tests de Angular con Playwright/Chromium
- `uv` para gestión de entorno/dependencias Python
- Dependencias de `backend/` y `estimator-cag/` con `uv sync`
- Dependencias de `frontend/` con `npm ci` y binario de Chromium

Comandos recomendados para validar el entorno en un Codespace nuevo:

```bash
# Frontend (Angular + Vitest + Playwright)
cd frontend
npm test -- --watch=false --browsers=chromium

# Backend (FastAPI)
cd ../backend
uv run pytest tests/ -v

# AI Engine (FastAPI + LiteLLM)
cd ../estimator-cag
uv run pytest tests/ -v
```

#### Troubleshooting (Codespaces)

Si los tests del frontend fallan con errores de Playwright/Chromium (por ejemplo, `libatk-1.0.so.0: cannot open shared object file`):

```bash
cd frontend
npx playwright install-deps chromium
npx playwright install chromium
npm test -- --watch=false --browsers=chromium
```

Si aparece un error de bloqueo de `apt/dpkg` (`Could not get lock /var/lib/dpkg/lock-frontend`), espera al proceso activo y reintenta:

```bash
sudo apt-get -o DPkg::Lock::Timeout=600 update
sudo apt-get -o DPkg::Lock::Timeout=600 --fix-missing install
```

### Variables de entorno

Crea un archivo `.env` en la raíz del repositorio:

```env
# LLM
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Seguridad
SECRET_KEY=cambia_esto_en_produccion
INTERNAL_API_KEY=cambia_esto_tambien

# Base de datos (opcionales — los defaults funcionan con Docker)
POSTGRES_USER=estimator
POSTGRES_PASSWORD=estimator_dev
POSTGRES_DB=estimator
```

### Iniciar todos los servicios

```bash
# Construir imágenes y levantar todos los servicios
docker compose up --build

# En background (detached)
docker compose up --build -d
```

| URL | Servicio |
|---|---|
| http://localhost:4200 | Frontend Angular |
| http://localhost:8000/docs | Backend API — Swagger UI |
| http://localhost:8000/health | Backend healthcheck |

### Ejecutar las migraciones (primera vez)

```bash
a
```

### Otros comandos útiles

```bash
# Levantar solo infraestructura (postgres + redis)
docker compose up postgres redis

# Levantar solo el motor de IA con su worker
docker compose up --build ai-engine ai-engine-worker

# Ver logs en tiempo real (todos los servicios o uno concreto)
docker compose logs -f
docker compose logs -f ai-engine

# Parar los contenedores
docker compose down

# Parar y borrar volúmenes (elimina datos de postgres y redis)
docker compose down -v

# Reconstruir un servicio sin tocar los demás
docker compose up --build frontend
```

---

## Tests

### Backend

```bash
cd backend
uv run pytest tests/ -v
```

Los tests usan SQLite en memoria — no requieren PostgreSQL ni el `ai-engine` activo. Las llamadas HTTP al motor de IA se mockean.

### AI Engine

```bash
cd estimator-cag
uv run pytest tests/ -v
```

---

## Convenciones

- Secretos nunca versionados (`.env` en `.gitignore`)
- Sesiones del máster en directorios `session0X/`
- Un `APIRouter` por recurso de dominio
- Lógica de negocio exclusivamente en la capa de servicios, nunca en routers

---

## Autor

**Luis Vidaechea** — Master AI Engineering, LIDR

## Licencia

MIT

---

*Última actualización: 15 de Mayo de 2026*

