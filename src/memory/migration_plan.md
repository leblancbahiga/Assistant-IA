# Plan de Migration Mémoire — V5 → V15 (Item 32, P2 #68)

## Contexte

NURU a accumulé **4 modules mémoire** qui font la même chose de façons
différentes :

| Module | Type | Statut |
|--------|------|--------|
| `memory_store.py` | V5 legacy | SQLite + sqlite-vec + Embedder |
| `memory_bridge.py` | V10.1 pont | Wrapper V9 → V5 |
| `long_term_memory.py` | V10.1 adaptateur | Wrapper orchestrateur |
| `memory/manager.py` | **V15 cible** | 6 couches unifiées |

## Architecture Cible

```
MemoryManager (src/memory/manager.py)
├── 1. WorkingMemory    — RAM-TTL (src/memory/working.py)
├── 2. EpisodicMemory   — SQLite (src/memory/episodic.py)
├── 3. SemanticMemory   — SQLite (src/memory/semantic.py)
├── 4. UserMemory       — SQLite (src/memory/user.py)
├── 5. ProceduralMemory — SQLite (src/memory/procedural.py)
├── 6. ErrorMemory      — SQLite (src/memory/errors.py)
├── SleepCycleManager   — src/memory/sleep_cycle.py
└── ConsolidationWorker — src/memory/consolidation.py
```

## Mapping Tables V5 → V15

| V5 (memory_store) | V15 cible | Migration |
|-------------------|-----------|-----------|
| `facts`           | `semantic_memory` | `INSERT INTO semantic_memory(id,fact,category,confidence,created_at,updated_at) SELECT ...` |
| `user_facts`      | `user_memory` | `INSERT INTO user_memory(key,value,category,confidence,updated_at) SELECT ...` |
| `history`         | `episodic_memory` | `INSERT INTO episodic_memory(id,timestamp,event_type,summary) VALUES('conv_'+ROWID, timestamp, 'conversation', content)` |
| `knowledge_cards` | `semantic_memory` | Fusion avec ses propres catégories |
| `feedback`        | `episodic_memory` | `event_type='feedback'` |
| `procedures`      | `procedural_memory` | Direct (même schéma) |
| `errors`          | `error_memory` | Direct (même schéma) |

## Script de Migration

```python
"""scripts/migrate_v5_to_v15.py — Migration V5 → V15 MemoryManager.

Usage:
    .venv/bin/python3 scripts/migrate_v5_to_v15.py [--dry-run]

Phase 1 : Analyse (dry-run)
Phase 2 : Export V5
Phase 3 : Import V15
Phase 4 : Validation
"""

import logging
import sqlite3
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

V5_DB_PATH = Path.home() / ".nuru" / "memory.db"
V15_DB_PATH = Path.home() / ".nuru" / "memory_v9.db"


def get_v5_conn():
    conn = sqlite3.connect(str(V5_DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def get_v15_conn():
    conn = sqlite3.connect(str(V15_DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_facts(v5, v15, dry_run=True):
    """Migre V5 facts → V15 semantic_memory."""
    cursor = v5.execute("SELECT id, content, category, timestamp FROM facts")
    rows = cursor.fetchall()
    if dry_run:
        logger.info("facts → semantic_memory : %d lignes", len(rows))
        return len(rows)

    now = time.time()
    count = 0
    for row in rows:
        v15.execute(
            """INSERT OR IGNORE INTO semantic_memory
               (id, fact, category, confidence, source_episodes,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), row["content"],
             row["category"] or "general", 0.8, "migration_v5",
             now, now),
        )
        count += 1
    v15.commit()
    logger.info("Migrated facts: %d", count)
    return count


def migrate_user_facts(v5, v15, dry_run=True):
    """Migre V5 user_facts → V15 user_memory."""
    cursor = v5.execute(
        "SELECT fact_type, content, source, confidence FROM user_facts WHERE is_active=1"
    )
    rows = cursor.fetchall()
    if dry_run:
        logger.info("user_facts → user_memory : %d lignes", len(rows))
        return len(rows)

    now = time.time()
    count = 0
    for row in rows:
        v15.execute(
            """INSERT OR IGNORE INTO user_memory
               (key, value, category, confidence, updated_at, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (row["fact_type"], row["content"], "migrated",
             row["confidence"], now, row["source"] or "migration_v5"),
        )
        count += 1
    v15.commit()
    logger.info("Migrated user_facts: %d", count)
    return count


def migrate_history(v5, v15, dry_run=True):
    """Migre V5 history → V15 episodic_memory."""
    cursor = v5.execute(
        "SELECT id, role, content, timestamp FROM history ORDER BY id"
    )
    rows = cursor.fetchall()
    if dry_run:
        logger.info("history → episodic_memory : %d lignes", len(rows))
        return len(rows)

    count = 0
    for row in rows:
        ts = row["timestamp"]
        if isinstance(ts, str):
            # Convert string timestamp to float
            from datetime import datetime
            ts = datetime.fromisoformat(ts).timestamp()
        v15.execute(
            """INSERT OR IGNORE INTO episodic_memory
               (id, timestamp, event_type, summary)
               VALUES (?, ?, ?, ?)""",
            (f"conv_{row['id']}", ts,
             "conversation", f"[{row['role']}] {row['content'][:200]}"),
        )
        count += 1
    v15.commit()
    logger.info("Migrated history: %d", count)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("=== DRY RUN — aucune donnée modifiée ===")

    v5 = get_v5_conn()
    v15 = get_v15_conn()
    
    total = 0
    total += migrate_facts(v5, v15, dry_run)
    total += migrate_user_facts(v5, v15, dry_run)
    total += migrate_history(v5, v15, dry_run)
    
    v5.close()
    v15.close()
    
    logger.info("Total lignes migrées : %d%s", total, " (dry-run)" if dry_run else "")
```

## Timeline

| Étape | Durée | Dépendances |
|-------|-------|------------|
| 1. Analyse V5 → tables cibles | 1j | - |
| 2. Écrire script migration | 1j | Étape 1 |
| 3. Dry-run & validation | 1j | Étape 2 |
| 4. Migration production | 1j* | Étape 3 |
| 5. Désactiver anciens modules | 1j | Étape 4 |
| 6. Tests post-migration | 2j | Étape 4 |

*La migration elle-même prend ~5-15 min sur M1.

## Risques

- **Perte de données** : faire backup complet de `memory.db` avant
- **Régressions** : `memory_store.py` est utilisé par l'orchestrateur
- **Temps d'arrêt** : migration en une session, NURU indisponible ~10 min

## Validation

Après migration :
```python
from src.memory import MemoryManager
mm = MemoryManager()
s = mm.stats()
assert s["episodic"] > 0
assert s["semantic"] > 0
assert s["user"] > 0
```
