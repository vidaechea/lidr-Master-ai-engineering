#!/bin/bash
# START HERE - Escenario de Adjuntos Grandes

cd "$(dirname "${BASH_SOURCE[0]}")"/ai-engine 2>/dev/null || cd ai-engine

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  🎯 ESCENARIO DE ADJUNTOS GRANDES - CÓMO COMENZAR             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "📝 ¿Qué mide este escenario?"
echo "  • Latencia vs tamaño de adjunto (0, 5, 20, 50, 100 KB)"
echo "  • Costo LLM vs tamaño de adjunto"
echo "  • Exactitud del sistema con archivos grandes"
echo ""

echo "🚀 OPCIÓN 1: Ejecutar TODO (escenario + análisis automático)"
echo "  $ bash tests/evals/stress/scripts/test_large_attachments.sh"
echo ""

echo "🚀 OPCIÓN 2: Ver opciones de ejecución"
echo "  $ bash tests/evals/stress/scripts/quickstart.sh"
echo ""

echo "🚀 OPCIÓN 3: Solo ejecutar el escenario"
echo "  $ uv run -m tests.evals.stress.runner large_attachment --json results.json"
echo ""

echo "📊 OPCIÓN 4: Ver ejemplo de interpretación de resultados"
echo "  $ python tests/stress/tools/interpret_stress_metrics.py"
echo ""

echo "📖 DOCUMENTACIÓN"
echo "  • Guía completa: tests/evals/stress/docs/LARGE_ATTACHMENTS.md"
echo "  • Índice: tests/evals/stress/docs/README.md"
echo ""

echo "➡️  RECOMENDACIÓN: Comienza con OPCIÓN 1"
echo "    bash tests/evals/stress/scripts/test_large_attachments.sh"
echo ""
