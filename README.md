# lidr-Master-ai-Engineering

Prácticas y proyectos del estudiante **Luis Vidaechea** — programa **Master AI Engineering** de [LIDR](https://lidr.es).

## Estructura del repositorio

```
lidr-Master-ai-engineering/
├── README.md                 # Este archivo
├── .env                      # Variables de entorno (local, no versionado)
├── .gitignore
├── estimator-cag/            # Proyecto: API REST de estimación con CAG
│   ├── README.md             # Setup completo del proyecto
│   ├── app/                  # Código FastAPI
│   ├── tests/
│   ├── streamlit_app.py      # Chat UI
│   ├── docker-compose.yml    # App + Redis
│   └── pyproject.toml
└── session01/                # Sesión 01: Clientes API OpenAI y Anthropic
    ├── README.md             # Documentación y uso detallado
    ├── *.py                  # Scripts Python
    └── *.ipynb               # Notebooks Jupyter
```

## Proyectos

### [estimator-cag](estimator-cag/) — API REST de estimación de esfuerzo

API FastAPI que genera estimaciones de esfuerzo de software a partir de transcripciones de reuniones, usando un enfoque **Context-Augmented Generation (CAG)**.

**Funcionalidades principales:**
- Pipeline CAG con ejemplos de referencia inyectados en el system prompt
- Soporte multi-proveedor: OpenAI y Anthropic
- Caché exacta con Redis (SHA-256, TTL configurable)
- Previsión de tokens y coste antes de cada llamada
- Sesiones multi-turn con historial
- Chat UI con Streamlit

**Levantar el proyecto → ver [estimator-cag/README.md](estimator-cag/README.md)**

---

### [session01](session01/) — Clientes API OpenAI y Anthropic

Clientes Python reutilizables con tracking de costos y soporte para Google Colab y desarrollo local.

**Levantar el proyecto → ver [session01/README.md](session01/README.md)**

---

## Convenciones

- 📁 Sesiones: `session0X/`
- 📄 Scripts: `session_0X_descripcion.py`
- 📓 Notebooks: `session_0X_descripcion.ipynb`
- 🔐 Secretos: nunca versionados (`.env` en `.gitignore`)

## Autor

**Luis Vidaechea** — Master AI Engineering, LIDR

## Licencia

MIT

---

**Última actualización**: 10 de Mayo de 2026

