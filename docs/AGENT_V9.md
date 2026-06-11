# Agent Loop NURU V9

## Architecture

Le module `src/agent/` implémente la boucle agentique ReAct (Reasoning + Acting)
avec planification, exécution, vérification, et gestion d'erreurs.

```
OBJECTIF UTILISATEUR
        │
        ▼
[AgentOrchestrator.run(goal)]
        │
        ├── 1. TaskPlanner.plan(goal) → TaskPlan
        │       └── Décomposition en ≤ 5 étapes ordonnées
        │
        ├── 2. Pour chaque étape (séquentiel) :
        │       ├── TaskExecutor.execute(step) → StepResult
        │       ├── TaskVerifier.verify(step, result) → (ok, score, reason)
        │       └── En cas d'échec :
        │               ├── ErrorRecovery.decide() → RETRY (max 3x)
        │               └── ErrorRecovery.decide() → ESCALATE (abandon)
        │
        ├── 3. Synthèse → réponse finale
        │
        ├── 4. ResumeManager.save_state() → SQLite
        │
        └── 5. MemoryManager (EpisodicMemory) → trace persistante
```

## Fichiers

| Fichier | Classe | Rôle | Tests |
|---|---|---|---|
| `types.py` | — | Dataclasses + enums partagés | — |
| `planner.py` | `TaskPlanner` | Décompose un goal en étapes (règles) | 12 |
| `executor.py` | `TaskExecutor` | Exécute une étape (mock ou custom tools) | 10 |
| `verifier.py` | `TaskVerifier` | Vérifie le résultat d'une étape | 11 |
| `recovery.py` | `ErrorRecovery` | Stratégies de recovery par type d'erreur | 13 |
| `resume.py` | `ResumeManager` | Sauvegarde/restaure l'état SQLite | 8 |
| `orchestrator.py` | `AgentOrchestrator` | Boucle agentique principale | 30 |

## Contrôles de sécurité

```python
AGENT_LIMITS = {
    "max_steps": 5,              # Pas de boucles infinies
    "max_retries_per_step": 3,    # Abandon après 3 échecs
    "max_wall_time_seconds": 300, # Timeout global 5 min
    "max_tool_calls_per_step": 3, # Pas plus de 3 outils par étape
}
```

## Utilisation

```python
from src.agent import AgentOrchestrator

orc = AgentOrchestrator()

# Tâche simple
result = await orc.run("fais une recherche sur le climat en RDC")
# → planifie: [search, generate, verify]
# → exécute 3 étapes
# → retourne résultat structuré

# Tâche complexe
result = await orc.run(
    "analyse le dossier Walikale et rédige un rapport"
)
# → planifie: [search, analyze, report]
# → chaque étape vérifiée individuellement
# → retry automatique si échec
```

## Tests

```bash
pytest tests/test_agent_v9.py tests/test_agent_v9_modules.py \
       tests/test_agent_v9_orchestrator.py -v
# 88 tests, 0 échecs
```

## Erreurs gérées

| Type | Stratégies |
|---|---|
| `TOOL_FAILURE` | retry → alternative → simplify → ask_user |
| `TIMEOUT` | retry → partial_result |
| `HALLUCINATION_DETECTED` | regenerate_strict → fallback_to_rag |
| `LOW_CONFIDENCE` | search_more → ask_user |
| `RAM_EXCEEDED` | reduce_batch → unload_models |
| `NETWORK_ERROR` | retry_backoff → offline_fallback |
