#!/usr/bin/env bash
# Re-index wrapper — lance repair_reindex puis reindex_rapide
# (le repair nettoie la DB, le rapide ne fait qu'indexer)
cd /Users/leblancbahiga/Downloads/Assistant\ IA
export PYTHONUNBUFFERED=1
python3 -u reindex_rapide_v21.py 2>&1
