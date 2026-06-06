#!/usr/bin/env python3
"""Nettoie la base NURU et réindexe tous les documents."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import pysqlite3 as sqlite3
import sqlite_vec

# 1. Vider la base
DB_PATH = "indexes/nuru.db"
conn = sqlite3.connect(DB_PATH, timeout=20)
sqlite_vec.load(conn)

tables = ["chunks", "chunks_fts", "indexed_files", "doc_structured", "cv_structured"]
for t in tables:
    try:
        conn.execute(f"DELETE FROM {t}")
    except Exception as e:
        print(f"  {t}: {e}")
conn.commit()
conn.close()

print("✅ Base videe")

# 2. Réindexer tous les fichiers dans les dossiers surveillés
from src.ingestion import IngestionEngine
from pathlib import Path
import asyncio
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

async def reindex():
    engine = IngestionEngine()
    
    # Dossiers à scanner (basés sur les chemins de indexed_files)
    dirs = [
        Path.home() / "Desktop" / "Dossier Leblanc Bahiga",
        Path.home() / "Desktop" / "Dossier Leblanc Bahiga" / "CV",
        Path.home() / "Desktop" / "Dossier Leblanc Bahiga" / "Lettre de motivation",
        Path.home() / "Desktop" / "VALUE CHAIN STUDY",
        Path.home() / "Desktop" / "Etude Kananga",
        Path.home() / "Desktop" / "Togogo",
        Path.home() / "Documents" / "Backup" / "CVS DES CONSULTANTS A LA MISSION" / "CVS DES CONSULTANTS A LA MISSION",
        Path.home() / "Documents" / "Backup" / "Construire un CV efficace de A a Z" / "5. Mise en pratique  Contenu et forme",
        Path.home() / "Documents" / "Documents - MacBook Pro de Leblanc" / "YARID",
        Path.home() / "Documents" / "Documents - MacBook Pro de Leblanc" / "YARID" / "CONCEPT NOTE",
        Path.home() / "Documents",
    ]
    
    total = 0
    for d in dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.suffix.lower() in [".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".xlsx"]:
                try:
                    await engine.index_file(str(f))
                    total += 1
                    print(f"  ✅ {f.name}")
                except Exception as e:
                    print(f"  ❌ {f.name}: {e}")
    
    print(f"\n✅ {total} fichiers indexes")

asyncio.run(reindex())
