# 📚 Documentación de Stress Tests

## 🎯 Inicio Rápido

**¿Quieres ejecutar los tests en 2 minutos?**  
→ Ir a [GUIDE.md](GUIDE.md)

```bash
uv run -m evals.stress.runner --scenario growth
```

## 📖 Índice Completo

| Documento | Propósito | Audiencia |
|-----------|-----------|-----------|
| [GUIDE.md](GUIDE.md) | **Quick start** - Cómo ejecutar y entender resultados | Todos |
| [STRUCTURE.md](STRUCTURE.md) | **Organización del código** - Dónde está cada cosa | Developers |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | **Detalles técnicos** - Cómo funciona internamente | Architects |
| [SCENARIOS.md](SCENARIOS.md) | **Narrativas de tests** - Qué prueba cada escenario | QA/PMs |

## 🗂️ Ubicación de Archivos

### Código
```
evals/stress/
├── scenarios.py              ← Definiciones de escenarios
├── runner.py                 ← CLI para ejecutar
├── metrics/stress_metrics.py ← Métricas personalizadas
└── tests/test_scenarios.py   ← Suite pytest
```

### Resultados
```
evals/stress/results/
├── growth.json               ← Resultado scenario growth
├── pivot.json                ← Resultado scenario pivot
├── contradiction.json        ← Resultado scenario contradiction
└── aggregated.json           ← Resultados combinados
```

### Documentación
```
evals/stress/docs/
├── GUIDE.md                  ← Este documento
├── STRUCTURE.md              ← Estructura del proyecto
├── IMPLEMENTATION.md         ← Detalles técnicos
└── SCENARIOS.md              ← Narrativas de tests
```

## 🚀 Comandos Comunes

```bash
# Ejecutar un escenario
uv run -m evals.stress.runner --scenario growth

# Ejecutar todos los escenarios
uv run -m evals.stress.runner --scenario all

# Guardar resultados
uv run -m evals.stress.runner --scenario all --json results.json
# Se guarda en: evals/stress/results/results.json

# Ejecutar con pytest
pytest evals/stress/tests/ -m slow -v

# Ver detalles
uv run -m evals.stress.runner --scenario growth --verbose
```

## 📊 Métricas Principales

- **Memory Drift** (0-1): Olvido natural de contexto (0.60 = normal)
- **Cost Curve**: Debe ser monotónico (no bajar)
- **Tech Accumulation**: Tecnologías se agregan, no se quitan
- **Name Preservation**: Nombre del proyecto se mantiene

## 🎯 Tres Escenarios

1. **Growth** 🌱  
   MVP → Auth → Multi-tenant → Audit → Export  
   Mide: Acumulación coherente de features

2. **Pivot** 🔄  
   React Native → Flutter (en turno 5)  
   Mide: Reemplazo limpio sin acumulación

3. **Contradiction** ⚖️  
   €50k → €80k (contradicción) → €75k (resolución)  
   Mide: Detección y resolución de conflictos

## 📈 Integración CI/CD

```yaml
# .github/workflows/stress-tests.yml
- name: Run stress tests
  run: |
    cd ai-engine
    uv run -m evals.stress.runner --scenario all --json stress_report.json
    
- name: Upload results
  uses: actions/upload-artifact@v3
  with:
    name: stress-test-results
    path: ai-engine/evals/stress/results/
```

## ✅ Validación Rápida

¿Todo funciona?

```bash
# Ejecutar growth scenario (5 turnos, ~60 segundos)
time uv run -m evals.stress.runner --scenario growth --verbose

# Debe completarse sin errores y generar un JSON
cat evals/stress/results/growth.json | head -20
```

## 🔍 Troubleshooting

| Error | Solución |
|-------|----------|
| `ModuleNotFoundError: No module named 'evals'` | Usar `uv run -m` en lugar de `python -m` |
| Ejecución lenta | Verificar `ANTHROPIC_API_KEY` y `OPENAI_API_KEY` |
| JSON no generado | Ver logs con `--verbose` |

Ver [GUIDE.md](GUIDE.md) para más detalles.

## 📞 Contacto

- **Documentación técnica:** [IMPLEMENTATION.md](IMPLEMENTATION.md)
- **Cómo ejecutar:** [GUIDE.md](GUIDE.md)
- **Narrativas de tests:** [SCENARIOS.md](SCENARIOS.md)

---

**Última actualización:** 2026-05-23  
**Status:** ✅ Production Ready  
**Coverage:** 100% (3 scenarios × 5 turns)
