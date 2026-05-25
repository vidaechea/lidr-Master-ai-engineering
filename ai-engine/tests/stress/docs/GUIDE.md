# Quick Start Guide - Stress Tests

## ⚡ 5 Minutos para Empezar

### 1️⃣ Ejecutar un Escenario Individual

```bash
cd ai-engine

# Growth scenario (MVP → Auth → Multi-tenant → Audit → Export)
uv run -m evals.stress.runner --scenario growth

# Pivot scenario (React Native → Flutter)
uv run -m evals.stress.runner --scenario pivot

# Contradiction scenario (Budget conflict: €50k → €80k → €75k)
uv run -m evals.stress.runner --scenario contradiction
```

### 2️⃣ Ejecutar Todos los Escenarios

```bash
uv run -m evals.stress.runner --scenario all

# Con salida JSON
uv run -m evals.stress.runner --scenario all \
  --json aggregated.json

# Los resultados se guardan automáticamente en:
# tests/evals/stress/results/aggregated.json
```

### 3️⃣ Modo Verbose (Ver Detalles)

```bash
uv run -m evals.stress.runner --scenario growth --verbose

# Salida incluye:
# ✓ Turn 1: cost=$0.0, drift=50%
# ✓ Turn 3: cost=$0.0, drift=67%
# ... etc
```

### 4️⃣ Ejecutar con Pytest

```bash
# Un escenario específico
pytest tests/evals/stress/tests/test_stress_scenarios.py::test_project_growth_scenario -v

# Todos los escenarios
pytest tests/evals/stress/tests/ -m "slow and llm_live" -v

# Solo unidad (sin LLM live)
pytest tests/evals/stress/tests/ -m "not llm_live" -v
```

## 📊 Entender los Resultados

### Cálculo de Costos

**Antes (v0):** Los costos eran siempre $0.0 porque se intentaba extraer un atributo `_cost` que LiteLLM no incluía.

**Ahora (v1):** Los costos se calculan correctamente usando `MODEL_REGISTRY`:
```
Cost = (input_tokens × input_price + output_tokens × output_price) / 1,000,000
```

**Ejemplo:**
```
gpt-4o-mini:  $0.15 per 1M input tokens, $0.60 per 1M output tokens
→ 1,000 input + 500 output = (1,000 × 0.15 + 500 × 0.60) / 1,000,000 = $0.00045
```

### JSON Output

```json
{
  "aggregate": {
    "total_scenarios": 3,
    "successful": 3,
    "total_cost_usd": 0.02,
    "avg_memory_drift": 0.60
  },
  "scenarios": [
    {
      "scenario_id": "growth_01",
      "profile": "growth",
      "turns_executed": 5,
      "cost_curve": [0.0, 0.0, 0.0, 0.0, 0.0],
      "avg_memory_drift": 0.68,
      "summary": {
        "final_project_name": "TaskMaster",
        "final_technologies": ["expo", "go", "node.js", "postgresql", "react"],
        "cost_monotonic": true,
        "tech_accumulation": true
      }
    }
  ]
}
```

### Interpretación de Métricas

| Métrica | Rango | Interpretación |
|---------|-------|----------------|
| **memory_drift** | 0.0 - 1.0 | Qué % de hechos se olvidaron (0.6 = natural para 20 turnos) |
| **cost_curve** | Monotónico ↑ | El costo nunca debe bajar entre turnos |
| **tech_accumulation** | ✓/✗ | Las tecnologías se acumulan sin regresión |
| **name_preservation** | ✓/✗ | El nombre del proyecto se mantiene constante |

**Valores Esperados:**
- ✅ Memory drift: 0.50 - 0.75 (natural en conversaciones largas)
- ✅ Cost curve: [0.0, 0.0, 0.0, 0.0, 0.0] (test mode)
- ✅ Tech accumulation: True
- ✅ Name preservation: True

## 🎯 Escenarios Explicados

### 🌱 Growth Scenario
```
T1   → MVP (React, Node.js, PostgreSQL)
T3   → Agregar Auth (+ Auth provider)
T6   → Multi-tenant (+ Audit logging)
T10  → Agregar Go para servicios de larga duración
T20  → Agregar Expo para mobile
```
**Medida:** Costo monótonico + nombre preservado + tech acumula

### 🔄 Pivot Scenario
```
T1-4 → React Native baseline
T5   → PIVOT a Flutter + Dart
T6-20 → Verificar transición limpia
```
**Medida:** React Native desaparece, Flutter se mantiene

### ⚖️ Contradiction Scenario
```
T3  → Budget €50,000 (anclado)
T8  → Budget €80,000 (CONTRADICCIÓN DETECTADA)
T20 → Resolución en €75,000 (compromiso)
```
**Medida:** Detección de contradicción + resolución válida

## 💡 Casos de Uso

### Validar Cambios Recientes

```bash
# Después de actualizar EstimationService
uv run -m evals.stress.runner --scenario growth --json baseline.json

# Comparar con versión anterior
# Las métricas deberían ser similares (±5%)
```

### Monitoreo Contínuo

```bash
# Agregar a CI/CD (GitHub Actions)
# Ejecutar nightly y alertar si memory_drift > 0.8
pytest tests/evals/stress/tests/ -m slow --json stress_report.json
```

### Debugging de Issues

```bash
# Ver logs detallados
uv run -m evals.stress.runner --scenario growth --verbose 2>&1 | grep -A5 "Turn 10"

# Ejecutar solo 1 turno para debugging rápido
# (modificar turn_counts en scenarios.py temporalmente)
```

## 🔧 Troubleshooting

### Error: `ModuleNotFoundError: No module named 'evals'`
```bash
# ✗ Incorrecto
python3 -m evals.stress.runner --scenario growth

# ✓ Correcto
uv run -m evals.stress.runner --scenario growth
```

### Error: `Failed to read metadata`
```bash
# Limpiar cache y reinstalar
rm -rf ~/.cache/uv
uv sync
uv run -m evals.stress.runner --scenario growth
```

### Ejecución Lenta (> 60s por turno)
```bash
# Verificar que ANTHROPIC_API_KEY y OPENAI_API_KEY están configuradas
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY

# Ver logs de LiteLLM
uv run -m evals.stress.runner --scenario growth --verbose 2>&1 | tail -50
```

## 📂 Archivo de Resultados

Todos los resultados se guardan en `tests/evals/stress/results/`:

```bash
ls -la tests/evals/stress/results/

# growth.json
# pivot.json
# contradiction.json
# aggregated.json  (si ejecutas --scenario all)
```

## 🚀 Próximos Pasos

1. **Integrar con CI/CD**: Agregar a `.github/workflows/`
2. **Dashboard**: Exportar JSON a Datadog/CloudWatch
3. **Alertas**: Configurar thresholds (memory_drift > 0.75)
4. **Tendencia**: Archivar resultados semanales

---

**Ver también:**
- [STRUCTURE.md](STRUCTURE.md) - Organización del código
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - Detalles técnicos
- [SCENARIOS.md](SCENARIOS.md) - Narrativas de escenarios
- [../README.md](../README.md) - Documentación general
