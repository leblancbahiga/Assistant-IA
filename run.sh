cd#!/bin/bash
# NURU — Lanceur automatique depuis le .venv
# Évite les conflits pydantic-core entre Python système (3.13) et .venv.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -f .venv/bin/python ]; then
    echo "❌ .venv introuvable. Crée-le avec :"
    echo "   python3.13 -m venv .venv && source .venv/bin/activate && pip install -e \".[dev]\""
    exit 1
fi

echo "🚀 NURU — activation .venv..."
source .venv/bin/activate

# PYTHONPATH peut polluer avec les libs Hermes (Python 3.11) → le nettoyer
unset PYTHONPATH

exec python run.py "$@"
