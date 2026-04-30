# lidr-Master-ai-Engineering

Repositorio de prácticas del estudiante **Luis Vidaechea** del programa **Master AI Engineering** de **LIDR** (Laboratorio de Ingeniería de Datos y IA).

## Acerca de este repositorio

Este repositorio contiene las prácticas y proyectos desarrollados durante el Master AI Engineering. Cada sesión o práctica se organiza en directorios independientes con la nomenclatura `session0X`, permitiendo una estructura clara y modular para el aprendizaje progresivo.

## Estructura del repositorio

```
lidr-Master-ai-engineering/
├── README.md                 # Este archivo
├── .env                      # Variables de entorno (local, no versionado)
├── .gitignore               # Archivos ignorados por git
├── requirements.txt         # Dependencias del proyecto
└── session0X/               # Carpetas de prácticas
    ├── README.md           # Documentación específica de la sesión
    ├── *.py                # Scripts Python
    ├── *.ipynb             # Notebooks de Jupyter
    └── assets/             # Recursos adicionales (si aplica)
```

## Sesiones disponibles

### [Session 01: API Clients for OpenAI and Anthropic](session01/)

Desarrollo de clientes Python reutilizables para las APIs de OpenAI y Anthropic con:
- ✅ Clientes minimalistas y limpios
- ✅ Soporte para múltiples modelos
- ✅ Tracking de costos
- ✅ Soporte para Google Colab y desarrollo local

**Documentación completa**: Ver [session01/README.md](session01/README.md)

## Requisitos generales

- Python 3.8+
- Gestor de paquetes (`pip`, `uv`, etc.)
- Virtual environment
- Claves API según la sesión (OpenAI, Anthropic, etc.)

## Setup inicial

### 1. Clonar el repositorio

```bash
git clone <repository-url>
cd lidr-Master-ai-engineering
```

### 2. Crear virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

O con `uv`:
```bash
uv sync
```

### 4. Configurar variables de entorno

Crear archivo `.env` en la raíz del proyecto:
```env
# Agregar según la sesión requerida
OPENAI_API_KEY=sk-proj-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
```

## Navegación por sesiones

Cada sesión es independiente y tiene su propia documentación. Para acceder a una sesión:

```bash
cd sessionXX/
cat README.md  # Leer documentación específica
```

## Convenciones del proyecto

- 📁 **Nombres de carpetas**: `session0X` (ej: `session01`, `session02`, etc.)
- 📄 **Archivos Python**: `session_0X_descripcion.py`
- 📓 **Notebooks**: `session_0X_descripcion.ipynb`
- 📚 **Documentación**: `README.md` en cada sesión
- 🔐 **Secretos**: Nunca versionados (`.env` en `.gitignore`)

## Recursos útiles

- [Master AI Engineering - LIDR](https://lidr.es)
- [Python Documentation](https://docs.python.org/3/)
- [Git Documentation](https://git-scm.com/doc)

## Autor

**Luis Vidaechea**  
Master AI Engineering - LIDR

## Licencia

MIT

---

**Última actualización**: 20 de Abril de 2026

