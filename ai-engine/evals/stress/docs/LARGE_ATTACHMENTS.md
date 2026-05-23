# Escenario de Adjuntos Grandes

## Propósito

El escenario `ProjectLargeAttachmentScenario` prueba cómo el sistema maneja archivos adjuntos de diferentes tamaños y mide:

- **Latencia**: Cómo cambia el tiempo de respuesta con el tamaño del adjunto
- **Costo**: Cómo cambia el costo de LLM con adjuntos más grandes (más tokens)
- **Recall**: Si el resumen de la respuesta menciona contenido del adjunto

## Configuración del Escenario

El escenario ejecuta 5 turnos con el **mismo transcript fijo** pero con adjuntos de tamaños crecientes:

| Turno | Tamaño Adjunto | Descripción |
|-------|---|---|
| 1 | 0 KB | Baseline (sin adjunto) |
| 2 | 5 KB | ≈ 2 páginas de texto plano |
| 3 | 20 KB | ≈ 8 páginas |
| 4 | 50 KB | ≈ 20 páginas |
| 5 | 100 KB | ≈ 40 páginas (cerca del límite `MAX_ATTACHMENT_CHARS`) |

El **transcript es idéntico para todos los turnos**:
```
"We're building a mobile app called PhotoShare. 
It's a photo sharing and collaboration platform. 
Users can upload photos, add comments, and collaborate with teams. 
Stack: React Native, Node.js backend, MongoDB. 
We need to estimate the initial MVP."
```

**Esto asegura que el stress esté únicamente en el tamaño del adjunto**, no en el contenido del transcript.

## Métricas Recolectadas

Para cada turno, el evaluador registra:

- `latency_ms`: Tiempo total de la estimación (ms)
- `cost_usd`: Costo del LLM para ese turno
- `input_tokens`: Tokens consumidos (transcript + adjunto)
- `output_tokens`: Tokens generados (respuesta)
- `response`: Texto completo del resumen de estimación

Además, se miden hechos (facts) para verificar que el sistema recuerde correctamente el proyecto "PhotoShare" y su stack tecnológico incluso con adjuntos grandes.

## Cómo Ejecutar

### Ejecutar solo el escenario de adjuntos grandes:

```bash
cd ai-engine
uv run -m evals.stress.runner large_attachment --json results.json
```

### Ejecutar todos los escenarios (incluyendo adjuntos grandes):

```bash
cd ai-engine
uv run -m evals.stress.runner all --json all_results.json
```

### Usar el script de prueba:

```bash
cd ai-engine
bash evals/stress/scripts/test_large_attachments.sh
```

## Análisis de Resultados

### Opción 1: Análisis automático

```bash
python evals/stress/tools/analyze.py results.json
```

Este script proporciona:

- **Tabla de métricas**: Latencia, costo, tokens para cada tamaño de adjunto
- **Análisis de latencia**: Cómo crece con el tamaño del adjunto
- **Análisis de costo**: Correlación entre tamaño y costo
- **Previsualizaciones de respuesta**: Fragmentos de las respuestas generadas

Ejemplo de salida:

```
================================================================================
📊 LARGE ATTACHMENT SCENARIO ANALYSIS
================================================================================

📈 METRICS BY ATTACHMENT SIZE

Turn   Size       Latency (ms)    Cost (USD)      In Tokens    Out Tokens
------ ---------- --------------- --------------- ------------ --------
1      0 KB          2134.5        $0.000450      1240         320
2      5 KB          2287.3        $0.000512      1450         335
3      20 KB         2456.1        $0.000675      1890         345
4      50 KB         2834.5        $0.001120      2890         360
5      100 KB        3456.7        $0.001850      4560         375

🔍 LATENCY ANALYSIS
  Baseline (no attachment): 2134.5 ms
  Maximum latency: 3456.7 ms (at 100 KB)
  Increase: +62.0% from baseline

💰 COST ANALYSIS
  Baseline (no attachment): $0.000450
  Maximum cost: $0.001850 (at 100 KB)
  Increase: +311.1% from baseline
```

### Opción 2: Análisis manual

Abre el archivo JSON resultante y busca la sección `scenarios` → `large_attachment_01` → `turns`.

## Interpretación de Resultados

### Curva de Latencia

- **Esperado**: Latencia creciente con tamaño del adjunto
- **Señal de alerta**: Saltos inexplicables de latencia (posible problema con el sistema)
- **Baseline útil**: El turno 1 (sin adjunto) sirve como referencia

### Curva de Costo

- **Esperado**: Costo proporcional al aumento de tokens (más contenido = más tokens)
- **Correlación**: Debería correlacionar con `input_tokens` en el turno
- **Truncamiento**: Si el turno 5 (100 KB) tiene tokens limitados, el sistema puede estar truncando

### Recall del Contenido

El análisis busca:
- ¿Menciona "PhotoShare" la respuesta?
- ¿Se mencionan "React Native", "Node.js", "MongoDB"?
- ¿El adjunto afecta la extracción de metadatos?

## Posibles Problemas

### 1. PDFs No Se Generan

Si ve errores al generar PDFs, asegúrese de tener reportlab instalado:

```bash
pip install reportlab
```

O el sistema usará una alternativa de texto simple.

### 2. Adjuntos No Se Envían

Si ve que `attachments_total_chars` es 0 en los resultados, verificar:
- TestClient está correctamente inicializado
- El endpoint `/api/v1/sessions/{id}/estimate` acepta archivos
- Ver logs del servidor

### 3. Costo Permanece en Cero

Esto indica que `MODEL_REGISTRY` no tiene la configuración de precios para el modelo usado. Ver [cost-calculation-fix.md](/memories/repo/cost-calculation-fix.md).

## Extensiones Futuras

- Agregar adjuntos múltiples (2-3 archivos simultáneamente)
- Probar diferentes formatos: DOCX, TXT, imágenes
- Medir impacto en cache hits/misses
- Evaluar compresión automática de adjuntos grandes
