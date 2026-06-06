# OpenAIEmbedder

Generador de embeddings usando el modelo `text-embedding-3-small` de OpenAI.

## Características

- **Modelo**: `text-embedding-3-small` (1536 dimensiones)
- **Batching**: Procesa chunks en lotes de máximo 100 para optimizar API calls
- **Reintento automático**: Maneja `RateLimitError` con reintentos exponenciales (1s, 2s, 4s)
- **Logging**: Registra cada batch procesado con token counts y latencias
- **Cálculo de costos**: Estima costo en USD ($0.02 por millón de tokens de entrada)

## Uso

### Embedear un texto individual

```python
from app.embedding_pipeline.embedder import OpenAIEmbedder

embedder = OpenAIEmbedder()
vector = embedder.embed_one("Your text here")
# vector es una lista de 1536 floats
```

### Embedear múltiples chunks

```python
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import Chunk

embedder = OpenAIEmbedder()

chunks = [
    Chunk(
        chunk_id="chunk_001",
        text="First chunk content",
        metadata={"budget_id": "BUD-001"},
        token_count=150,
    ),
    Chunk(
        chunk_id="chunk_002",
        text="Second chunk content",
        metadata={"budget_id": "BUD-001"},
        token_count=200,
    ),
]

embedded_chunks = embedder.embed_many(chunks)
# embedded_chunks es una lista de EmbeddedChunk con el vector de embedding incluido
```

## Detalles técnicos

### Batching

El método `embed_many()` automáticamente divide los chunks en lotes de máximo 100:

```
[Chunk1, Chunk2, ..., Chunk100] → Batch 1 → API call
[Chunk101, Chunk102, ..., Chunk200] → Batch 2 → API call
[Chunk201, ...] → Batch 3 → API call
```

### Reintento automático en Rate Limits

Si OpenAI retorna `RateLimitError`:

```
Intento 1 → Error → Espera 1s
Intento 2 → Error → Espera 2s
Intento 3 → Error → Espera 4s
Intento 4 → Falla → Excepción
```

### Logging

Cada batch procesa genera un log:

```
embedding_batch_processed
  batch_num=1
  batch_size=100
  batch_tokens=15234
  latency_seconds=0.532
```

### Cálculo de costos

Fórmula: `(tokens_entrada * $0.02) / 1_000_000`

Ejemplo:
- 1,000,000 tokens → $0.02
- 500,000 tokens → $0.01
- 10,000 tokens → $0.0002

## Errores

### ValueError

- `"OPENAI_API_KEY is required"`: Falta configurar la API key en `.env`
- `"Text must be non-empty"`: El texto pasado a `embed_one()` está vacío
- `"Chunks list must not be empty"`: La lista de chunks en `embed_many()` está vacía

### RateLimitError

Se reintenta automáticamente 3 veces. Si persiste después de los reintentos, se propaga la excepción.

## Configuración

Constantes de módulo en `embedder.py`:

```python
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # segundos
EMBEDDING_COST_PER_MILLION_TOKENS_USD = 0.02
```

## Requisitos

- Variables de entorno: `OPENAI_API_KEY`
- Dependencias: `openai`, `structlog`, `pydantic`

## Integraciones

- **Router**: [embedding_pipeline/router.py](router.py)
- **Schemas**: [embedding_pipeline/schemas.py](schemas.py) (`Chunk`, `EmbeddedChunk`)
