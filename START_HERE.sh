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
echo "  $ bash evals/stress/scripts/test_large_attachments.sh"
echo ""

echo "🚀 OPCIÓN 2: Ver opciones de ejecución"
echo "  $ bash evals/stress/scripts/quickstart.sh"
echo ""

echo "🚀 OPCIÓN 3: Solo ejecutar el escenario"
echo "  $ uv run -m evals.stress.runner large_attachment --json results.json"
echo ""

echo "📊 OPCIÓN 4: Ver ejemplo de interpretación de resultados"
echo "  $ python evals/stress/tools/interpret.py"
echo ""

echo "📖 DOCUMENTACIÓN"
echo "  • Guía completa: evals/stress/docs/LARGE_ATTACHMENTS.md"
echo "  • Índice: evals/stress/docs/README.md"
echo ""

echo "➡️  RECOMENDACIÓN: Comienza con OPCIÓN 1"
echo "    bash evals/stress/scripts/test_large_attachments.sh"
echo ""
