#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python3 reindex_all.py
echo ""
echo "=== Appuyez sur Entrée pour fermer ==="
read
