# Stress Test Framework - Estructura

## 📂 Organización

```
evals/stress/
├── scenarios.py              Definiciones de escenarios (Growth, Pivot, Contradiction)
├── runner.py                 CLI para ejecutar escenarios
├── README.md                 Documentación general del framework
│
├── metrics/
│   ├── __init__.py
│   └── stress_metrics.py     Métricas DeepEval (MemoryDrift, Anchor, Contradiction)
│
├── tests/
│   ├── __init__.py
│   └── test_stress_scenarios.py   Suite pytest con markers @slow @llm_live
│
├── results/                  Salida de ejecuciones
│   ├── __init__.py
│   ├── growth.json           Resultado scenario growth
│   ├── pivot.json            Resultado scenario pivot
│   ├── contradiction.json    Resultado scenario contradiction
│   └── aggregated.json       Resultados combinados de todas las ejecuciones
│
└── docs/                     Documentación
    ├── STRUCTURE.md          Este archivo
    ├── GUIDE.md              Quick start y ejemplos
    ├── IMPLEMENTATION.md     Detalles técnicos
    └── SCENARIOS.md          Narrativas y turnos por escenario
```

## 🎯 Convenciones

### Nombres de Archivos

| Ubicación | Propósito | Ejemplo |
|-----------|-----------|---------|
| `results/` | Salida JSON única de ejecución | `growth.json` |
| `results/` | Salida JSON agregada | `aggregated.json` |
| `scenarios.py` | Lógica de generación de escenarios | N/A |
| `metrics/` | Implementación de métricas | `stress_metrics.py` |
| `tests/` | Suite de pruebas | `test_stress_scenarios.py` |

### Rutas en Código

```python
# Importar escenarios
from evals.stress.scenarios import ProjectGrowthScenario

# Importar métricas
from evals.stress.metrics.stress_metrics import MemoryDriftMetric

# Importar desde CLI
from evals.stress.runner import main
```

### Guardado de Resultados

**Automático (via CLI):**
```bash
uv run -m evals.stress.runner --scenario growth
# Guarda en: evals/stress/results/growth.json

uv run -m evals.stress.runner --scenario all --json results.json
# Guarda en: evals/stress/results/results.json
```

**Manual (en código):**
```python
import json
from pathlib import Path

result = await evaluator.run(scenario)
path = Path("evals/stress/results") / "custom.json"
path.parent.mkdir(parents=True, exist_ok=True)
with open(path, "w") as f:
    json.dump(result, f, indent=2)
```

## 📊 Flujo de Datos

```
┌─────────────────────────────────────────────────────┐
│        evals/stress/scenarios.py                    │
│  - ProjectGrowthScenario                           │
│  - ProjectPivotScenario                            │
│  - ProjectContradictionScenario                    │
│  - MultiTurnScenarioEvaluator                      │
└──────────────────┬──────────────────────────────────┘
                   │
                   ├──→ evals/stress/runner.py (CLI)
                   │         │
                   │         └──→ evals/stress/results/
                   │              - growth.json
                   │              - pivot.json
                   │              - contradiction.json
                   │              - aggregated.json
                   │
                   └──→ tests/test_stress_scenarios.py (pytest)
                        │
                        └──→ evals/stress/metrics/stress_metrics.py
                             - MemoryDriftMetric
                             - AnchorConsistencyMetric
                             - ContradictionDetectionMetric
```

## 🔄 Refactorización desde Versión Anterior

**Antes:**
```
ai-engine/
├── growth_results.json
├── pivot_results.json
├── contradiction_results.json
├── stress_results.json
├── tests/eval/test_stress_scenarios.py
├── tests/eval/metrics_stress.py
├── STRESS_TEST_REPORT.md
├── STRESS_TEST_GUIDE.md
└── evals/stress/
    └── README.md
```

**Después (Centralizado):**
```
ai-engine/
└── evals/stress/
    ├── scenarios.py
    ├── runner.py
    ├── README.md
    ├── metrics/
    │   └── stress_metrics.py
    ├── tests/
    │   └── test_stress_scenarios.py
    ├── results/
    │   ├── growth.json
    │   ├── pivot.json
    │   ├── contradiction.json
    │   └── aggregated.json
    └── docs/
        ├── STRUCTURE.md (este archivo)
        ├── GUIDE.md
        ├── IMPLEMENTATION.md
        └── SCENARIOS.md
```

## ✅ Ventajas de la Estructura Centralizada

| Aspecto | Antes | Después |
|---------|-------|---------|
| **Organización** | Archivos dispersos | Todo en `evals/stress/` |
| **Resultados** | 4 archivos en raíz | Centralizados en `results/` |
| **Tests** | Repartidos en `tests/eval/` | Coubicados en `stress/tests/` |
| **Métricas** | Separadas en `tests/eval/` | Agrupadas en `stress/metrics/` |
| **Documentación** | Mezcla en raíz y `evals/stress/` | Centralizadas en `stress/docs/` |
| **Discoverabilidad** | Difícil de ubicar | `evals/stress/` es punto único |

## 🚀 Próximos Pasos

1. **Usar la nueva estructura en CI/CD:**
   ```yaml
   - name: Run stress tests
     run: pytest evals/stress/tests/ -m slow
   ```

2. **Versionar resultados:**
   ```bash
   # Guardar por fecha
   uv run -m evals.stress.runner --scenario all \
     --json "results_$(date +%Y%m%d).json"
   # Guarda en: evals/stress/results/results_20260523.json
   ```

3. **Integrar con dashboard:**
   ```python
   from pathlib import Path
   import json
   
   results_dir = Path("evals/stress/results")
   latest_result = sorted(results_dir.glob("*.json"))[-1]
   with open(latest_result) as f:
       metrics = json.load(f)
       # Enviar a Datadog, CloudWatch, etc.
   ```

---

**Documentación:** Ver [GUIDE.md](GUIDE.md) para quick start  
**Implementación:** Ver [IMPLEMENTATION.md](IMPLEMENTATION.md) para detalles técnicos  
**Escenarios:** Ver [SCENARIOS.md](SCENARIOS.md) para narrativas
