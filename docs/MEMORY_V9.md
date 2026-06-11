# Mémoire unifiée NURU V9

## Architecture

Le module `src/memory/` implémente une mémoire hiérarchique à 6 types,
inspirée de MemGPT/Letta, MIRIX, et Mem0.

```
┌────────────────────────────────────────────────────────────┐
│                    MEMORY MANAGER (façade)                   │
├────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  EPISODIC   │  │  SEMANTIC   │  │  USER       │       │
│  │  MEMORY     │  │  MEMORY     │  │  MEMORY     │       │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤       │
│  │ Événements  │  │ Faits       │  │ Profil      │       │
│  │ vécus       │  │ consolidés  │  │ utilisateur │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  ERROR      │  │  PROCEDURAL │  │  WORKING    │       │
│  │  MEMORY     │  │  (V10)      │  │  MEMORY     │       │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤       │
│  │ Erreurs +   │  │ Workflows   │  │ Session     │       │
│  │ corrections │  │ appris      │  │ (RAM)       │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
├────────────────────────────────────────────────────────────┤
│              CONSOLIDATION WORKER (daemon 6h)               │
└────────────────────────────────────────────────────────────┘
```

## Fichiers

| Fichier | Classe | Rôle | Statut |
|---|---|---|---|
| `schema.py` | `MemorySchema` | Création DB + tables + version | ✅ Stable |
| `episodic.py` | `EpisodicMemory` | Événements vécus avec embedding | ✅ Stable |
| `semantic.py` | `SemanticMemory` | Faits consolidés avec fusion | ✅ Stable |
| `user.py` | `UserMemory` | Profil utilisateur key-value | ✅ Stable |
| `errors.py` | `ErrorMemory` | Erreurs + détection proactive | ✅ Stable |
| `retriever.py` | `MemoryRetriever` | Recherche multi-mémoire unifiée | ✅ Stable |
| `manager.py` | `MemoryManager` | Façade pour le pipeline existant | ✅ Stable |
| `consolidation.py` | `ConsolidationWorker` | Consolidation périodique (6h) | ✅ Stable |

## Utilisation

```python
from src.memory import MemoryManager

# Créer le gestionnaire
mgr = MemoryManager()

# Enregistrer une conversation
mgr.record_conversation(
    query="Qui est Leblanc ?",
    response="Leblanc travaille pour YARID",
    importance=0.9,
)

# Ajouter un profil utilisateur
mgr.user.set(key="language", value="fr", category="preference")
mgr.user.set(key="name", value="Leblanc", category="identity")

# Rechercher dans toutes les mémoires
mgr.retriever.recall("Leblanc")

# Générer le contexte pour le prompt LLM
context = mgr.get_full_context("analyse du dossier Walikale")

# Vérifier les erreurs similaires avant une action
errors = mgr.check_errors("analyse de données météo")

# Statistiques
mgr.get_memory_stats()
```

## Tests

```bash
python tests/test_memory_v9.py
# Résultat : 178 tests, 0 échecs
```

## Schéma SQLite

Base de données : `~/.nuru/memory_v9.db` (ou chemin personnalisé)

Tables :
- `episodic_memory` : id, timestamp, event_type, summary, context (JSON), embedding (BLOB), importance, access_count, last_accessed, consolidated
- `semantic_memory` : id, fact, category, confidence, source_episodes (JSON), embedding (BLOB), created_at, updated_at, access_count
- `procedural_memory` : (réservé V10)
- `user_memory` : key, value, category, confidence, updated_at, source
- `error_memory` : id, timestamp, error_type, description, root_cause, correction, related_query, embedding (BLOB), resolved
- `working_memory` : key, value, ttl, created_at
- `memory_schema_version` : version, updated_at (V1 actuelle)

## Budget RAM estimé

- Module mémoire : ~210 Mo en usage, ~40 Mo en idle
- ConsolidationWorker : ~100 Mo (pic, toutes les 6h)

Compatible M1 8 Go avec les autres modules du pipeline.
