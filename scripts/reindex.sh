#!/bin/bash
# NURU — Wrapper de réindexation avec PYTHONPATH correct
# Résout : conflit Hermes 3.11 → Projet 3.13
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
SCRIPT="$PROJECT_ROOT/scripts/reindex_all.py"
PYTHON="$PROJECT_ROOT/.venv/bin/python3"

# PYTHONPATH nécessaire : les modules NURU (src.rag_engine, src.embedder, etc.)
# doivent se charger depuis le venv du projet, pas depuis Hermes (Python 3.11)
export PYTHONPATH="$PROJECT_ROOT/.venv/lib/python3.13/site-packages:$PROJECT_ROOT"
export PYTHONUNBUFFERED=1

echo "📂 Répertoire : $PROJECT_ROOT"
echo "🐍 Python      : $("$PYTHON" --version 2>&1)"
echo "📦 PYTHONPATH  : $PYTHONPATH"
echo ""

case "${1:-}" in
  --force|-f)
    echo "🔥 Mode FORCE : réindexation complète"
    echo ""
    exec "$PYTHON" "$SCRIPT" --force
    ;;
  --incremental|-i)
    echo "♻️  Mode incrémental"
    echo ""
    exec "$PYTHON" "$SCRIPT" --incremental
    ;;
  --help|-h)
    echo "Usage: $0 [--force | --incremental | --help]"
    echo ""
    echo "  (sans argument)   Réindexation complète, reprend depuis le checkpoint"
    echo "  --force, -f       Vide l'index et réindexe tout"
    echo "  --incremental, -i Ignore les fichiers déjà traités"
    echo "  --help, -h        Ce message"
    echo ""
    echo "Le checkpoint est sauvegardé dans : indexes/reindex_checkpoint.json"
    exit 0
    ;;
  *)
    exec "$PYTHON" "$SCRIPT"
    ;;
esac
