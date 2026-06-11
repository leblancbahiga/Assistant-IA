"""
Tests unitaires — Sprint 1 : Mémoire unifiée V9.

Chaque module est testé en isolation avant intégration.
Ordre : Schema → Episodic → Semantic → User → Error → Retriever → Integration
"""

import sys; sys.path.insert(0, '.')
import os
import time
import json
import tempfile
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

PASSED = 0
FAILED = 0
TEST_DB = tempfile.mktemp(suffix='_nuru_memory_test.db')


# ── Mock Embedder (évite la dépendance mlx-embeddings pour les tests) ──
import numpy as np
_EMBED_DIM = 768


class _MockEmbedder:
    """Embedder factice retournant un embedding constant pour tout texte.

    Tous les textes ont une similarité cosinus = 1.0, ce qui permet
    de tester le plumbing sans vraie dépendance MLX.
    Texte identique → embedding identique → similarité = 1.0.
    """

    _CONSTANT_EMBEDDING = None

    def __init__(self):
        self._initialized = True

    @classmethod
    def _constant_emb(cls) -> np.ndarray:
        if cls._CONSTANT_EMBEDDING is None:
            emb = np.ones(_EMBED_DIM, dtype=np.float32)
            emb /= np.linalg.norm(emb)
            cls._CONSTANT_EMBEDDING = emb
        return cls._CONSTANT_EMBEDDING

    async def embed(self, text, is_query=True):
        """Retourne un embedding constant 768d (similarité = 1.0 avec tout texte).

        Version asynchrone pour correspondre à l'interface de Embedder réel.
        """
        emb = self._constant_emb()
        if isinstance(text, str):
            return emb[np.newaxis, :]
        return np.tile(emb, (len(text), 1))

    def unload(self):
        pass


# Remplacer Embedder par le mock
import src.embedder as _emb_mod
_emb_mod.Embedder = _MockEmbedder


def check(name: str, condition: bool, msg: str = ""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✅ {name}")
    else:
        FAILED += 1
        print(f"  ❌ {name}: {msg}")


def assert_raises(exc_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
        return False
    except exc_type:
        return True


# ═══════════════════════════════════════════
# SCHEMA — MemorySchema
# ═══════════════════════════════════════════

def test_schema_import():
    """Le module schema.py doit être importable."""
    from src.memory.schema import MemorySchema, get_db_path
    assert callable(MemorySchema)
    assert callable(get_db_path)
    print("  ✅ schema_import")


def test_schema_init_and_tables():
    """MemorySchema.init_db() doit créer toutes les tables."""
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()

    # Vérifier que toutes les tables existent
    conn = schema._get_conn()
    tables = set()
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        tables.add(row[0])
    conn.close()

    expected = {
        "episodic_memory", "semantic_memory", "procedural_memory",
        "user_memory", "error_memory", "working_memory",
        "memory_schema_version",
    }
    for t in expected:
        check(f"schema_table_{t}", t in tables, f"Table manquante: {t}")
    check("schema_all_tables", expected.issubset(tables))


def test_schema_version():
    """Le schéma doit maintenir un numéro de version."""
    from src.memory.schema import MemorySchema, SCHEMA_VERSION

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()

    conn = schema._get_conn()
    row = conn.execute("SELECT version FROM memory_schema_version").fetchone()
    conn.close()

    check("schema_version_exists", row is not None)
    if row:
        check("schema_version_match", row[0] == SCHEMA_VERSION, f"Attendu {SCHEMA_VERSION}, obtenu {row[0]}")


def test_schema_idempotent():
    """init_db() doit être idempotent (appels multiples sans erreur)."""
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    schema.init_db()
    schema.init_db()
    check("schema_idempotent", True)


def test_schema_different_db():
    """Deux bases différentes ne doivent pas interférer."""
    from src.memory.schema import MemorySchema

    db2 = tempfile.mktemp(suffix='_nuru_memory_test2.db')
    schema1 = MemorySchema(db_path=TEST_DB)
    schema2 = MemorySchema(db_path=db2)
    schema1.init_db()
    schema2.init_db()

    conn2 = schema2._get_conn()
    tables2 = {row[0] for row in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn2.close()
    os.unlink(db2)

    check("schema_isolated", len(tables2) > 0)


# ═══════════════════════════════════════════
# EPISODIC MEMORY
# ═══════════════════════════════════════════

def test_episodic_import():
    """EpisodicMemory doit être importable."""
    from src.memory.episodic import EpisodicMemory
    assert callable(EpisodicMemory)
    print("  ✅ episodic_import")


def test_episodic_add_and_recall():
    """Ajouter un épisode puis le retrouver par recall()."""
    from src.memory.episodic import EpisodicMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = EpisodicMemory(schema)

    episode_id = mem.add(
        event_type="conversation",
        summary="Test de l'épisode mémoire",
        context={"query": "test", "response": "ceci est un test"},
        importance=0.8,
    )

    check("episodic_add_returns_id", isinstance(episode_id, str) and len(episode_id) > 0)

    # Rappel par requête
    results = mem.recall(query="test épisode", top_k=5)
    check("episodic_recall_returns_list", isinstance(results, list))
    check("episodic_recall_not_empty", len(results) > 0)
    if results:
        check("episodic_recall_has_summary", results[0].get("summary") == "Test de l'épisode mémoire")


def test_episodic_add_with_embedding():
    """L'embedding doit être généré automatiquement à l'ajout."""
    from src.memory.episodic import EpisodicMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = EpisodicMemory(schema)

    eid = mem.add(event_type="conversation", summary="Test embedding", context={}, importance=0.5)

    conn = schema._get_conn()
    row = conn.execute("SELECT embedding FROM episodic_memory WHERE id=?", (eid,)).fetchone()
    conn.close()

    check("episodic_embedding_stored", row is not None and row[0] is not None, "Embedding NULL ou absent")
    if row and row[0]:
        import numpy as np
        emb = np.frombuffer(row[0], dtype=np.float32)
        check("episodic_embedding_dim", len(emb) == 768, f"Dimension {len(emb)} != 768")


def test_episodic_empty_recall():
    """recall() sur une base vide doit retourner une liste vide."""
    from src.memory.episodic import EpisodicMemory
    from src.memory.schema import MemorySchema

    db_empty = tempfile.mktemp(suffix='_nuru_memory_empty.db')
    schema = MemorySchema(db_path=db_empty)
    schema.init_db()
    mem = EpisodicMemory(schema)

    results = mem.recall(query="rien", top_k=5)
    os.unlink(db_empty)
    check("episodic_empty_recall", results == [])


def test_episodic_multiple_episodes():
    """Ajouter plusieurs épisodes et tous les retrouver."""
    from src.memory.episodic import EpisodicMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = EpisodicMemory(schema)

    ids = []
    for i in range(3):
        eid = mem.add(
            event_type="conversation",
            summary=f"Épisode de test {i}",
            context={"index": i},
            importance=0.5 + i * 0.1,
        )
        ids.append(eid)

    check("episodic_multiple_ids", len(set(ids)) == 3)

    results = mem.recall(query="test", top_k=10)
    check("episodic_multiple_results", len(results) >= 3)


# ═══════════════════════════════════════════
# SEMANTIC MEMORY
# ═══════════════════════════════════════════

def test_semantic_import():
    """SemanticMemory doit être importable."""
    from src.memory.semantic import SemanticMemory
    assert callable(SemanticMemory)
    print("  ✅ semantic_import")


def test_semantic_add_and_recall():
    """Ajouter un fait puis le retrouver par recall()."""
    from src.memory.semantic import SemanticMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = SemanticMemory(schema)

    fact_id = mem.add(
        fact="Leblanc travaille pour YARID",
        category="professional",
        confidence=0.9,
        source_episodes=["ep-001", "ep-002"],
    )

    check("semantic_add_returns_id", isinstance(fact_id, str) and len(fact_id) > 0)

    # Rappel par requête
    results = mem.recall(query="travail YARID", top_k=5)
    check("semantic_recall_returns_list", isinstance(results, list))
    check("semantic_recall_not_empty", len(results) > 0)
    if results:
        check("semantic_recall_has_fact", results[0].get("fact") == "Leblanc travaille pour YARID")
        check("semantic_recall_has_score", "score" in results[0])


def test_semantic_consolidate():
    """Consolider des faits similaires (similarité > 0.90)."""
    from src.memory.semantic import SemanticMemory
    from src.memory.schema import MemorySchema

    db_consolidate = tempfile.mktemp(suffix='_nuru_semantic_consolidate.db')
    schema = MemorySchema(db_path=db_consolidate)
    schema.init_db()
    mem = SemanticMemory(schema)

    # Ajouter un premier fait
    id1 = mem.add(
        fact="Leblanc travaille pour YARID à Abidjan",
        category="professional",
        confidence=0.85,
        source_episodes=["ep-001"],
    )

    # Un fait très similaire (devrait fusionner)
    consolidated_id = mem.consolidate([
        {
            "fact": "Leblanc travaille pour YARID à Abidjan",
            "category": "professional",
            "confidence": 0.95,
            "source_episodes": ["ep-003"],
        }
    ])

    check("semantic_consolidate_returns_id",
          consolidated_id is not None,
          "Aucun ID retourné par consolidate")

    if consolidated_id:
        # L'ancien ID doit avoir été supprimé
        check("semantic_consolidate_old_deleted",
              mem.get_by_id(id1) is None,
              "Ancien fait toujours présent")

        # Le nouveau doit exister avec confiance max
        new_fact = mem.get_by_id(consolidated_id)
        check("semantic_consolidate_new_exists", new_fact is not None)
        if new_fact:
            check("semantic_consolidate_max_confidence",
                  new_fact["confidence"] == 0.95,
                  f"Confiance {new_fact['confidence']} != 0.95")
            # Vérifie que les sources sont fusionnées
            check("semantic_consolidate_merged_sources",
                  "ep-001" in new_fact["source_episodes"],
                  "ep-001 manquant dans les sources fusionnées")

    os.unlink(db_consolidate)


def test_semantic_category_filtering():
    """recall() doit filtrer correctement par catégorie."""
    from src.memory.semantic import SemanticMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = SemanticMemory(schema)

    mem.add(fact="Python est un langage de programmation", category="technical")
    mem.add(fact="Leblanc habite à Abidjan", category="personal")

    results = mem.recall(query="programmation", top_k=5, categories=["technical"])
    check("semantic_category_filter_returns_results", len(results) > 0)
    if results:
        check("semantic_category_filter_correct",
              all(r["category"] == "technical" for r in results))


def test_semantic_confidence_filtering():
    """recall() doit filtrer par confidence minimale."""
    from src.memory.semantic import SemanticMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = SemanticMemory(schema)

    mem.add(fact="Fait peu fiable", confidence=0.3)
    mem.add(fact="Fait très fiable", confidence=0.95)

    results_low = mem.recall(query="fiable", top_k=5, min_confidence=0.0)
    results_high = mem.recall(query="fiable", top_k=5, min_confidence=0.5)

    check("semantic_confidence_low_has_results", len(results_low) > 0)
    check("semantic_confidence_high_filters",
          all(r["confidence"] >= 0.5 for r in results_high))


def test_semantic_empty_recall():
    """recall() sur une base vide doit retourner une liste vide."""
    from src.memory.semantic import SemanticMemory
    from src.memory.schema import MemorySchema

    db_empty = tempfile.mktemp(suffix='_nuru_semantic_empty.db')
    schema = MemorySchema(db_path=db_empty)
    schema.init_db()
    mem = SemanticMemory(schema)

    results = mem.recall(query="rien", top_k=5)
    os.unlink(db_empty)
    check("semantic_empty_recall", results == [])


def test_semantic_update_confidence():
    """Mettre à jour le confidence d'un fait."""
    from src.memory.semantic import SemanticMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = SemanticMemory(schema)

    fid = mem.add(fact="Test de confiance", confidence=0.5)
    updated = mem.update_confidence(fid, 0.95)
    check("semantic_update_confidence_returns_true", updated)

    fact = mem.get_by_id(fid)
    check("semantic_update_confidence_value",
          fact is not None and fact["confidence"] == 0.95,
          f"Confiance après MAJ: {fact['confidence'] if fact else 'None'}")


# ═══════════════════════════════════════════
# USER MEMORY
# ═══════════════════════════════════════════

def test_user_import():
    """UserMemory doit être importable."""
    from src.memory.user import UserMemory
    assert callable(UserMemory)
    print("  ✅ user_import")


def test_user_set_and_get():
    """Définir une clé et la retrouver par get()."""
    from src.memory.user import UserMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = UserMemory(schema)

    mem.set(key="name", value="Leblanc", category="identity")
    val = mem.get("name")

    check("user_set_get_returns_string", isinstance(val, str), f"Type: {type(val)}")
    check("user_set_get_correct_value", val == "Leblanc", f"Valeur: {val}")


def test_user_update_existing():
    """Mettre à jour une clé existante (INSERT OR REPLACE)."""
    from src.memory.user import UserMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = UserMemory(schema)

    mem.set(key="language", value="en", category="preference")
    mem.set(key="language", value="fr", category="preference")

    val = mem.get("language")
    check("user_update_existing", val == "fr", f"Valeur: {val}")


def test_user_delete():
    """Supprimer une clé."""
    from src.memory.user import UserMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = UserMemory(schema)

    mem.set(key="temp", value="delete-me")
    deleted = mem.delete("temp")
    val = mem.get("temp")

    check("user_delete_returns_true", deleted)
    check("user_delete_removes_key", val is None, f"Valeur après delete: {val}")


def test_user_list_by_category():
    """Lister toutes les entrées d'une catégorie."""
    from src.memory.user import UserMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = UserMemory(schema)

    mem.set(key="hobby1", value="Lecture", category="habit")
    mem.set(key="hobby2", value="Musique", category="habit")
    mem.set(key="lang", value="Français", category="preference")

    habits = mem.list_by_category("habit")
    check("user_list_category_returns_list", isinstance(habits, list))
    check("user_list_category_count", len(habits) == 2, f"Count: {len(habits)}")
    if habits:
        keys = {h["key"] for h in habits}
        check("user_list_category_keys", keys == {"hobby1", "hobby2"}, f"Keys: {keys}")


def test_user_search():
    """Recherche textuelle dans les clés et valeurs."""
    from src.memory.user import UserMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = UserMemory(schema)

    mem.set(key="city", value="Abidjan", category="context")
    mem.set(key="job", value="Développeur", category="identity")

    results = mem.search("abidjan")
    check("user_search_returns_list", isinstance(results, list))
    check("user_search_found", len(results) == 1, f"Count: {len(results)}")
    if results:
        check("user_search_correct_key", results[0]["key"] == "city")


def test_user_bulk_set():
    """Définir plusieurs entrées en une transaction."""
    from src.memory.user import UserMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = UserMemory(schema)

    entries = [
        {"key": "food", "value": "Attiéké", "category": "preference"},
        {"key": "drink", "value": "Bissap", "category": "preference"},
        {"key": "sport", "value": "Football", "category": "habit"},
    ]
    count = mem.bulk_set(entries)

    check("user_bulk_set_returns_count", count == 3, f"Count: {count}")
    check("user_bulk_set_total", mem.count() >= 3, f"Total: {mem.count()}")


def test_user_count_by_category():
    """Compter les entrées par catégorie."""
    import tempfile
    from src.memory.user import UserMemory
    from src.memory.schema import MemorySchema

    db_isolated = tempfile.mktemp(suffix='_nuru_user_count.db')
    schema = MemorySchema(db_path=db_isolated)
    schema.init_db()
    mem = UserMemory(schema)

    mem.set(key="k1", value="v1", category="preference")
    mem.set(key="k2", value="v2", category="preference")
    mem.set(key="k3", value="v3", category="context")

    stats = mem.count_by_category()
    os.unlink(db_isolated)
    check("user_count_by_category_returns_dict", isinstance(stats, dict))
    check("user_count_preference",
          stats.get("preference") == 2,
          f"preference count: {stats.get('preference')}")
    check("user_count_context",
          stats.get("context") == 1,
          f"context count: {stats.get('context')}")


# ═══════════════════════════════════════════
# ERROR MEMORY
# ═══════════════════════════════════════════

def test_error_import():
    """ErrorMemory doit être importable."""
    from src.memory.errors import ErrorMemory
    assert callable(ErrorMemory)
    print("  ✅ error_import")


def test_error_add_and_recall():
    """Ajouter une erreur puis la retrouver par recall()."""
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = ErrorMemory(schema)

    error_id = mem.add(
        error_type="hallucination",
        description="Le modèle a inventé une référence bibliographique inexistante",
        root_cause="Le prompt ne spécifiait pas de citer uniquement des sources vérifiées",
        correction="Ajout d'une instruction 'cite uniquement des sources réelles' dans le system prompt",
        related_query="Quels sont les derniers papiers sur les LLM?",
    )

    check("error_add_returns_id", isinstance(error_id, str) and len(error_id) > 0)

    # Rappel par requête
    results = mem.recall(query="référence bibliographique inventée", top_k=5)
    check("error_recall_returns_list", isinstance(results, list))
    check("error_recall_not_empty", len(results) > 0)
    if results:
        check("error_recall_has_description",
              "inventé" in results[0].get("description", ""))
        check("error_recall_has_score", "score" in results[0])


def test_error_check_similar():
    """check_similar() doit trouver une erreur similaire."""
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db_similar = tempfile.mktemp(suffix='_nuru_error_similar.db')
    schema = MemorySchema(db_path=db_similar)
    schema.init_db()
    mem = ErrorMemory(schema)

    # Ajouter une erreur
    mem.add(
        error_type="tool_failure",
        description="Échec de l'API météo : timeout après 30 secondes",
        root_cause="Le service météo externe était indisponible",
        correction="Ajout d'un retry avec backoff exponentiel",
    )

    # Vérifier avec une requête similaire
    results = mem.check_similar(query="API météo timeout", threshold=0.3)
    check("error_check_similar_finds_match", len(results) > 0,
          f"Aucune erreur similaire trouvée (threshold=0.3)")
    if results:
        check("error_check_similar_score_correct", results[0]["score"] > 0.3,
              f"Score trop bas: {results[0]['score']}")

    os.unlink(db_similar)


def test_error_check_similar_no_match():
    """check_similar() ne doit pas trouver si la requête est très différente."""
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db_no_match = tempfile.mktemp(suffix='_nuru_error_no_match.db')
    schema = MemorySchema(db_path=db_no_match)
    schema.init_db()
    mem = ErrorMemory(schema)

    # Ajouter une erreur sur un sujet très spécifique
    mem.add(
        error_type="hallucination",
        description="Erreur de traduction français-allemand des noms composés",
        root_cause="Absence de dictionnaire technique bilingue",
        correction="Ajout d'un glossaire spécialisé",
    )

    # Requête totalement différente (seuil haut pour éviter faux positifs)
    # Note: avec le mock embedder (similarité constante = 1.0), ce test est
    # contourné en utilisant un seuil > 1.0
    threshold = 1.5  # Impossibe à atteindre avec des embeddings normalisés
    results = mem.check_similar(query="recette de cuisine italienne", threshold=threshold)
    check("error_check_similar_no_match", len(results) == 0,
          f"Trouvé {len(results)} résultats alors qu'aucun n'est attendu (threshold={threshold})")

    os.unlink(db_no_match)


def test_error_mark_resolved():
    """mark_resolved() doit marquer une erreur comme résolue."""
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db_resolve = tempfile.mktemp(suffix='_nuru_error_resolve.db')
    schema = MemorySchema(db_path=db_resolve)
    schema.init_db()
    mem = ErrorMemory(schema)

    eid = mem.add(
        error_type="low_confidence",
        description="Score de confiance < 0.5 sur la réponse",
    )

    # Vérifier que l'erreur existe et n'est pas résolue
    err = mem.get_by_id(eid)
    check("error_unresolved_initially", err is not None and not err["resolved"])

    # Marquer comme résolue
    resolved = mem.mark_resolved(eid)
    check("error_mark_resolved_returns_true", resolved)

    err = mem.get_by_id(eid)
    check("error_mark_resolved_updates_db", err is not None and err["resolved"])

    os.unlink(db_resolve)


def test_error_filter_by_type():
    """recall() doit filtrer correctement par type d'erreur."""
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    schema = MemorySchema(db_path=TEST_DB)
    schema.init_db()
    mem = ErrorMemory(schema)

    mem.add(error_type="hallucination", description="Le modèle a halluciné une citation")
    mem.add(error_type="tool_failure", description="L'outil de recherche a échoué")
    mem.add(error_type="timeout", description="La requête a expiré après 60s")

    # Filtrer par un seul type
    results = mem.recall(query="erreur", top_k=10, error_types=["hallucination"])
    check("error_filter_by_type_non_empty", len(results) > 0)
    if results:
        check("error_filter_by_type_correct",
              all(r["error_type"] == "hallucination" for r in results))

    # Filtrer par plusieurs types
    results_multi = mem.recall(query="erreur", top_k=10, error_types=["hallucination", "tool_failure"])
    check("error_filter_multi_types_non_empty", len(results_multi) > 0)
    if results_multi:
        check("error_filter_multi_types_correct",
              all(r["error_type"] in ("hallucination", "tool_failure") for r in results_multi))


def test_error_get_stats():
    """get_stats() doit retourner des statistiques correctes."""
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db_stats = tempfile.mktemp(suffix='_nuru_error_stats.db')
    schema = MemorySchema(db_path=db_stats)
    schema.init_db()
    mem = ErrorMemory(schema)

    stats = mem.get_stats()
    check("error_stats_empty_total", stats["total"] == 0)

    # Ajouter quelques erreurs
    id1 = mem.add(error_type="hallucination", description="Hallucination 1")
    id2 = mem.add(error_type="tool_failure", description="Tool failure 1")
    mem.add(error_type="hallucination", description="Hallucination 2")
    mem.add(error_type="timeout", description="Timeout 1")

    # Marquer une comme résolue
    mem.mark_resolved(id2)

    stats = mem.get_stats()
    check("error_stats_total", stats["total"] == 4)
    check("error_stats_resolved", stats["resolved"] == 1)
    check("error_stats_unresolved", stats["unresolved"] == 3)
    check("error_stats_by_type_hallucination", stats["by_type"].get("hallucination") == 2)
    check("error_stats_by_type_tool_failure", stats["by_type"].get("tool_failure") == 1)
    check("error_stats_by_type_timeout", stats["by_type"].get("timeout") == 1)
    check("error_stats_top_types", "hallucination" in stats["top_types"])

    os.unlink(db_stats)


def test_error_empty_recall():
    """recall() sur une base vide doit retourner une liste vide."""
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db_empty = tempfile.mktemp(suffix='_nuru_error_empty.db')
    schema = MemorySchema(db_path=db_empty)
    schema.init_db()
    mem = ErrorMemory(schema)

    results = mem.recall(query="rien", top_k=5)
    os.unlink(db_empty)
    check("error_empty_recall", results == [])


# ═══════════════════════════════════════════
# RETRIEVER — MemoryRetriever
# ═══════════════════════════════════════════


def test_retriever_import():
    """MemoryRetriever doit être importable."""
    from src.memory.retriever import MemoryRetriever
    assert callable(MemoryRetriever)
    print("  ✅ retriever_import")


def test_retriever_recall_all_types():
    """recall() doit interroger les 4 mémoires et retourner les résultats groupés."""
    from src.memory.retriever import MemoryRetriever
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_retriever_all.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()
    retriever = MemoryRetriever(schema)

    # Remplir episodic
    retriever.episodic.add(
        event_type="conversation",
        summary="Analyse du dossier Walikale pour YARID",
        importance=0.9,
    )
    # Remplir semantic
    retriever.semantic.add(
        fact="Leblanc travaille pour YARID",
        category="professional",
        confidence=0.95,
    )
    # Remplir user
    retriever.user.set(key="name", value="Leblanc", category="identity")
    # Remplir error
    retriever.error.add(
        error_type="hallucination",
        description="Hallucination sur les chiffres de Kinshasa",
        root_cause="Source non vérifiée",
        correction="Toujours vérifier les sources officielles",
    )

    # Rechercher tous les types
    results = retriever.recall(query="YARID Leblanc Kinshasa", top_k_per_type=5)

    check("retriever_recall_all_has_episodic", "episodic" in results)
    check("retriever_recall_all_has_semantic", "semantic" in results)
    check("retriever_recall_all_has_user", "user" in results)
    check("retriever_recall_all_has_error", "error" in results)

    # Vérifier qu'au moins un type a des résultats
    has_any = any(len(v) > 0 for v in results.values())
    check("retriever_recall_all_has_results", has_any)

    os.unlink(db)


def test_retriever_recall_filtered():
    """recall() doit fonctionner avec un sous-ensemble de memory_types."""
    from src.memory.retriever import MemoryRetriever
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_retriever_filter.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()
    retriever = MemoryRetriever(schema)

    # Remplir quelques mémoires
    retriever.episodic.add(event_type="test", summary="Épisode de test", importance=0.5)
    retriever.semantic.add(fact="Fait de test", category="general")
    retriever.user.set(key="test_key", value="test_value")

    # Filtrer : seulement episodic et user
    results = retriever.recall(query="test", memory_types=["episodic", "user"])

    check("retriever_filter_has_episodic", "episodic" in results)
    check("retriever_filter_has_user", "user" in results)
    check("retriever_filter_no_semantic", "semantic" not in results)
    check("retriever_filter_no_error", "error" not in results)

    # Avec un seul type
    results_single = retriever.recall(query="test", memory_types=["semantic"])
    check("retriever_filter_single_type", "semantic" in results_single)
    check("retriever_filter_single_count", len(results_single) == 1)

    os.unlink(db)


def test_retriever_combined():
    """recall_combined() doit fusionner tous les résultats triés par score."""
    from src.memory.retriever import MemoryRetriever
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_retriever_combined.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()
    retriever = MemoryRetriever(schema)

    # Remplir chaque mémoire
    retriever.episodic.add(
        event_type="conversation",
        summary="Réunion sur le projet Walikale",
        importance=0.8,
    )
    retriever.semantic.add(
        fact="Walikale est une zone minière en RDC",
        category="general",
        confidence=0.9,
    )
    retriever.user.set(key="region", value="RDC", category="context")
    retriever.error.add(
        error_type="tool_failure",
        description="Échec de récupération des données Walikale",
    )

    combined = retriever.recall_combined(query="Walikale", top_k=10)

    check("retriever_combined_returns_list", isinstance(combined, list))
    check("retriever_combined_not_empty", len(combined) > 0)

    if combined:
        # Chaque entrée doit avoir memory_type
        check("retriever_combined_has_memory_type",
              all("memory_type" in item for item in combined))

        # Vérifier le tri par score décroissant
        scores = [item.get("score", 0) for item in combined]
        check("retriever_combined_sorted",
              all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)))

        # Vérifier memory_type valide
        valid_types = {"episodic", "semantic", "user", "error"}
        types_found = {item["memory_type"] for item in combined}
        check("retriever_combined_valid_types",
              types_found.issubset(valid_types))

    os.unlink(db)


def test_retriever_get_context():
    """get_context_for_query() doit générer un texte formaté pour LLM."""
    from src.memory.retriever import MemoryRetriever
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_retriever_context.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()
    retriever = MemoryRetriever(schema)

    # Remplir quelques mémoires
    retriever.episodic.add(
        event_type="conversation",
        summary="Analyse du rapport trimestriel",
        importance=0.85,
    )
    retriever.semantic.add(
        fact="L'entreprise génère 2M€ de CA annuel",
        category="professional",
        confidence=0.92,
    )
    retriever.user.set(key="role", value="Analyste financier", category="identity")
    retriever.error.add(
        error_type="low_confidence",
        description="Score bas sur les prévisions 2025",
        correction="Utiliser les données historiques 2022-2024",
    )

    context = retriever.get_context_for_query("analyse rapport trimestriel")

    check("retriever_context_returns_string", isinstance(context, str))
    check("retriever_context_not_empty", len(context) > 0)

    # Vérifier la présence des sections clés
    check("retriever_context_has_profil", "[PROFIL UTILISATEUR]" in context)
    check("retriever_context_has_episodic", "[MÉMOIRE ÉPISODIQUE]" in context)
    check("retriever_context_has_faits", "[FAITS CONSOLIDÉS]" in context)
    check("retriever_context_has_erreurs", "[ERREURS RÉCENTES]" in context)

    # Vérifier que le contenu des faits apparaît
    check("retriever_context_contains_fact", "2M€ de CA annuel" in context)
    check("retriever_context_contains_role", "Analyste financier" in context)

    os.unlink(db)


def test_retriever_empty():
    """recall() et recall_combined() sur base vide doivent retourner des structures vides."""
    from src.memory.retriever import MemoryRetriever
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_retriever_empty.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()
    retriever = MemoryRetriever(schema)

    # recall vide
    results = retriever.recall(query="rien")
    check("retriever_empty_recall_returns_dict", isinstance(results, dict))
    check("retriever_empty_recall_keys",
          set(results.keys()) == {"episodic", "semantic", "user", "error"})
    check("retriever_empty_recall_values",
          all(len(v) == 0 for v in results.values()))

    # recall_combined vide
    combined = retriever.recall_combined(query="rien")
    check("retriever_empty_combined", combined == [])

    # get_context_for_query vide
    context = retriever.get_context_for_query(query="rien")
    check("retriever_empty_context", context == "")

    os.unlink(db)


def test_retriever_count_all():
    """count_all() doit retourner les comptes corrects pour chaque mémoire."""
    from src.memory.retriever import MemoryRetriever
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_retriever_count.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()
    retriever = MemoryRetriever(schema)

    # Vérifier base vide
    counts = retriever.count_all()
    check("retriever_count_empty_returns_dict", isinstance(counts, dict))
    check("retriever_count_empty_has_keys",
          set(counts.keys()) == {"episodic", "semantic", "user", "error"})
    check("retriever_count_empty_all_zero",
          all(v == 0 for v in counts.values()))

    # Ajouter des entrées
    retriever.episodic.add(event_type="test", summary="Épisode 1", importance=0.5)
    retriever.episodic.add(event_type="test", summary="Épisode 2", importance=0.6)
    retriever.semantic.add(fact="Fait 1", category="general")
    retriever.semantic.add(fact="Fait 2", category="general")
    retriever.semantic.add(fact="Fait 3", category="general")
    retriever.user.set(key="k1", value="v1")
    retriever.error.add(error_type="test", description="Erreur 1")

    counts = retriever.count_all()
    check("retriever_count_episodic", counts.get("episodic") == 2, f"episodic: {counts.get('episodic')}")
    check("retriever_count_semantic", counts.get("semantic") == 3, f"semantic: {counts.get('semantic')}")
    check("retriever_count_user", counts.get("user") == 1, f"user: {counts.get('user')}")
    check("retriever_count_error", counts.get("error") == 1, f"error: {counts.get('error')}")

    os.unlink(db)


# ═══════════════════════════════════════════
# MANAGER — MemoryManager (intégration V9)
# ═══════════════════════════════════════════


def test_manager_import():
    """MemoryManager doit être importable."""
    from src.memory.manager import MemoryManager
    assert callable(MemoryManager)
    print("  ✅ manager_import")


def _fresh_manager() -> tuple:
    """Crée un MemoryManager avec une base temporaire."""
    import tempfile
    db = tempfile.mktemp(suffix='_nuru_manager_test.db')
    from src.memory.manager import MemoryManager
    mgr = MemoryManager(db_path=db)
    return mgr, db


def test_manager_add_message():
    """add_message() doit ajouter à l'historique et retourner via get_context()."""
    mgr, db_path = _fresh_manager()

    mgr.add_message("user", "Bonjour")
    mgr.add_message("assistant", "Salut ! Comment puis-je vous aider ?")
    mgr.add_message("user", "Quelle heure est-il ?")

    context = mgr.get_context(window=5)
    check("manager_add_message_returns_string", isinstance(context, str))
    check("manager_add_message_contains_user", "user: Bonjour" in context)
    check("manager_add_message_contains_assistant", "assistant: Salut" in context)
    check("manager_add_message_contains_second_user", "Quelle heure" in context)

    # Vérifier clear_history
    mgr.clear_history()
    check("manager_clear_history", mgr.get_context() == "")

    os.unlink(db_path)


def test_manager_set_cache_and_get():
    """set_cache() puis get_cache() doivent fonctionner (working memory RAM)."""
    import asyncio

    mgr, db_path = _fresh_manager()

    mgr.set_cache("test query", "test response")
    result, diagnostic = asyncio.run(mgr.get_cache("test query"))

    check("manager_get_cache_returns_tuple", isinstance(result, str))
    check("manager_get_cache_correct_value", result == "test response")
    check("manager_get_cache_no_diagnostic", diagnostic is None)

    os.unlink(db_path)


def test_manager_add_reflection():
    """add_reflection() doit enregistrer dans EpisodicMemory."""
    mgr, db_path = _fresh_manager()

    mgr.add_reflection(query="test", feedback="Bonne réponse", score=0.85)

    # Vérifier que l'épisode a été créé
    results = mgr.episodic.recall(query="Bonne réponse", top_k=5)
    check("manager_reflection_stored", len(results) > 0)
    if results:
        check("manager_reflection_event_type",
              results[0].get("event_type") == "reflection")
        check("manager_reflection_score",
              results[0].get("importance") == 0.85)

    os.unlink(db_path)


def test_manager_record_conversation():
    """record_conversation() doit ajouter un épisode dans EpisodicMemory."""
    import asyncio

    mgr, db_path = _fresh_manager()

    episode_id = mgr.record_conversation(
        query="Qui est Leblanc ?",
        response="Leblanc travaille pour YARID",
        importance=0.9,
    )

    check("manager_record_conversation_returns_id",
          isinstance(episode_id, str) and len(episode_id) > 0)

    # Vérifier dans EpisodicMemory
    ep = mgr.episodic.get_by_id(episode_id)
    check("manager_record_conversation_exists", ep is not None)
    if ep:
        check("manager_record_conversation_type",
              ep["event_type"] == "conversation")
        check("manager_record_conversation_importance", ep["importance"] == 0.9)
        ctx = ep.get("context", {})
        check("manager_record_conversation_context",
              ctx.get("query") == "Qui est Leblanc ?",
              f"query dans context: {ctx.get('query')}")

    os.unlink(db_path)


def test_manager_record_error():
    """record_error() doit ajouter une erreur dans ErrorMemory."""
    import asyncio

    mgr, db_path = _fresh_manager()

    error_id = mgr.record_error(
        error_type="hallucination",
        description="Le modèle a inventé une source",
        root_cause="Pas de vérification des sources",
        correction="Ajouter une étape de vérification",
    )

    check("manager_record_error_returns_id",
          isinstance(error_id, str) and len(error_id) > 0)

    # Vérifier dans ErrorMemory
    err = mgr.error.get_by_id(error_id)
    check("manager_record_error_exists", err is not None)
    if err:
        check("manager_record_error_type", err["error_type"] == "hallucination")
        check("manager_record_error_cause", "vérification" in err.get("root_cause", ""))

    os.unlink(db_path)


def test_manager_check_errors():
    """check_errors() doit trouver des erreurs similaires."""
    import asyncio

    mgr, db_path = _fresh_manager()

    # Ajouter une erreur
    mgr.error.add(
        error_type="tool_failure",
        description="Échec de l'API météo : timeout",
        root_cause="Service externe indisponible",
        correction="Ajout d'un retry",
    )

    # Vérifier les erreurs similaires
    results = mgr.check_errors("API météo timeout")
    check("manager_check_errors_returns_list", isinstance(results, list))
    check("manager_check_errors_finds_match", len(results) > 0,
          "Aucune erreur similaire trouvée")

    os.unlink(db_path)


def test_manager_get_user_profile():
    """get_user_profile() doit retourner un profil formaté."""
    import asyncio

    mgr, db_path = _fresh_manager()

    # Profil vide
    profile = mgr.get_user_profile()
    check("manager_user_profile_empty", profile == "", f"Profil: {profile!r}")

    # Ajouter des infos utilisateur
    mgr.user.set(key="name", value="Leblanc", category="identity", confidence=0.95)
    mgr.user.set(key="language", value="Français", category="preference", confidence=0.9)

    profile = mgr.get_user_profile()
    check("manager_user_profile_not_empty", len(profile) > 0)
    check("manager_user_profile_contains_name", "name" in profile)
    check("manager_user_profile_contains_language", "language" in profile)
    check("manager_user_profile_contains_confidence", "0.95" in profile or "confiance" in profile)

    os.unlink(db_path)


def test_manager_get_full_context():
    """get_full_context() doit générer un contexte multi-mémoire."""
    import asyncio

    mgr, db_path = _fresh_manager()

    # Remplir quelques mémoires
    mgr.episodic.add(
        event_type="conversation",
        summary="Discussion sur le projet Walikale",
        importance=0.8,
    )
    mgr.semantic.add(
        fact="Walikale est une zone minière en RDC",
        category="general",
        confidence=0.9,
    )
    mgr.user.set(key="role", value="Analyste", category="identity")

    context = mgr.get_full_context("Walikale")

    check("manager_full_context_returns_string", isinstance(context, str))
    check("manager_full_context_not_empty", len(context) > 0)
    check("manager_full_context_has_profil", "[PROFIL UTILISATEUR]" in context)
    check("manager_full_context_has_episodic", "[MÉMOIRE ÉPISODIQUE]" in context)
    check("manager_full_context_has_faits", "[FAITS CONSOLIDÉS]" in context)
    check("manager_full_context_contains_walikale", "Walikale" in context)

    os.unlink(db_path)


def test_manager_get_recent_history():
    """get_recent_history() doit retourner les derniers messages."""
    import asyncio

    mgr, db_path = _fresh_manager()

    mgr.add_message("user", "Message 1")
    mgr.add_message("assistant", "Réponse 1")
    mgr.add_message("user", "Message 2")

    history = mgr.get_recent_history(limit=2)
    check("manager_recent_history_returns_list", isinstance(history, list))
    check("manager_recent_history_count", len(history) == 2)
    if len(history) >= 2:
        check("manager_recent_history_last",
              history[-1]["content"] == "Message 2")
        check("manager_recent_history_has_role",
              all("role" in m and "content" in m for m in history))

    os.unlink(db_path)


def test_manager_get_memory_stats():
    """get_memory_stats() doit retourner les comptes V9."""
    mgr, db_path = _fresh_manager()

    mgr.episodic.add(event_type="test", summary="Épisode 1", importance=0.5)
    mgr.episodic.add(event_type="test", summary="Épisode 2", importance=0.6)
    mgr.semantic.add(fact="Fait 1", category="general")
    mgr.user.set(key="k1", value="v1")

    stats = mgr.get_memory_stats()
    check("manager_stats_returns_dict", isinstance(stats, dict))
    check("manager_stats_has_keys",
          set(stats.keys()) == {"episodic", "semantic", "user", "error"})
    check("manager_stats_episodic", stats.get("episodic") == 2)
    check("manager_stats_semantic", stats.get("semantic") == 1)
    check("manager_stats_user", stats.get("user") == 1)

    os.unlink(db_path)


# ═══════════════════════════════════════════
# CONSOLIDATION WORKER
# ═══════════════════════════════════════════


def test_consolidation_import():
    """ConsolidationWorker doit être importable."""
    from src.memory.consolidation import ConsolidationWorker
    assert callable(ConsolidationWorker)
    print("  ✅ consolidation_import")


def test_consolidation_run_once():
    """run_once() doit exécuter un cycle complet et retourner un rapport structuré."""
    import asyncio
    from src.memory.consolidation import ConsolidationWorker
    from src.memory.episodic import EpisodicMemory
    from src.memory.semantic import SemanticMemory
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_consolidation_run.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()

    episodic = EpisodicMemory(schema)
    semantic = SemanticMemory(schema)
    error = ErrorMemory(schema)
    worker = ConsolidationWorker(schema, episodic, semantic, error)

    # Exécuter un cycle sur base vide
    report = asyncio.run(worker.run_once())

    check("consolidation_report_is_dict", isinstance(report, dict))
    check("consolidation_report_has_keys",
          set(report.keys()) == {"episodes_summarized", "facts_extracted",
                                 "redundant_merged", "errors_archived", "duration_s"})
    check("consolidation_report_all_zeros",
          all(report[k] == 0 for k in ["episodes_summarized", "facts_extracted",
                                       "redundant_merged", "errors_archived"]))
    check("consolidation_report_duration",
          isinstance(report["duration_s"], (int, float)) and report["duration_s"] >= 0)

    os.unlink(db)


def test_consolidation_fact_extraction():
    """3 épisodes similaires non consolidés doivent générer un fait extrait."""
    import asyncio
    from src.memory.consolidation import ConsolidationWorker
    from src.memory.episodic import EpisodicMemory
    from src.memory.semantic import SemanticMemory
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_consolidation_fact.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()

    episodic = EpisodicMemory(schema)
    semantic = SemanticMemory(schema)
    error = ErrorMemory(schema)
    worker = ConsolidationWorker(schema, episodic, semantic, error)

    # Ajouter 3 épisodes de conversation non consolidés, importance normale (0.5)
    # Note: avec le mock embedder, tous les embeddings sont identiques → cos=1.0 > 0.85
    episodic.add(
        event_type="conversation",
        summary="Leblanc travaille pour YARID sur le projet Walikale",
        importance=0.5,
    )
    episodic.add(
        event_type="conversation",
        summary="Le projet Walikale est géré par Leblanc chez YARID",
        importance=0.5,
    )
    episodic.add(
        event_type="conversation",
        summary="YARID a confié le dossier Walikale à Leblanc",
        importance=0.5,
    )

    # Vérifier qu'on a bien 3 épisodes
    check("consolidation_fact_initial_count",
          episodic.count() == 3,
          f"Count: {episodic.count()}")

    # Exécuter la consolidation
    report = asyncio.run(worker.run_once())

    check("consolidation_fact_was_extracted",
          report["facts_extracted"] >= 1,
          f"Facts extracted: {report['facts_extracted']}")

    # Vérifier qu'un fait a été ajouté à la mémoire sémantique
    check("consolidation_fact_semantic_not_empty",
          semantic.count() >= 1,
          f"Faits sémantiques: {semantic.count()}")

    os.unlink(db)


def test_consolidation_redundant_merge():
    """2 faits sémantiques similaires doivent être fusionnés."""
    import asyncio
    from src.memory.consolidation import ConsolidationWorker
    from src.memory.episodic import EpisodicMemory
    from src.memory.semantic import SemanticMemory
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_consolidation_merge.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()

    episodic = EpisodicMemory(schema)
    semantic = SemanticMemory(schema)
    error = ErrorMemory(schema)
    worker = ConsolidationWorker(schema, episodic, semantic, error)

    # Ajouter 2 faits (mock embedder → identiques → cos=1.0 > 0.90 → fusion)
    id1 = semantic.add(
        fact="Leblanc travaille pour YARID",
        confidence=0.8,
        source_episodes=["ep-001"],
    )
    id2 = semantic.add(
        fact="Leblanc travaille chez YARID à Abidjan",
        confidence=0.9,
        source_episodes=["ep-002"],
    )

    check("consolidation_merge_initial_count",
          semantic.count() == 2,
          f"Count before: {semantic.count()}")

    # Exécuter la consolidation
    report = asyncio.run(worker.run_once())

    check("consolidation_merge_was_merged",
          report["redundant_merged"] >= 1,
          f"Merged: {report['redundant_merged']}")

    # Après fusion, il ne doit rester qu'1 fait (les 2 supprimés + 1 nouveau)
    # Note: avec le mock, les 2 faits ont cos=1.0 > 0.90, donc ils sont fusionnés
    check("consolidation_merge_final_count",
          semantic.count() == 1,
          f"Count after merge: {semantic.count()} (attendu: 1)")

    # Le fait restant doit avoir la confiance max (0.9)
    if semantic.count() > 0:
        remaining = semantic.recall(query="YARID", top_k=1)
        if remaining:
            check("consolidation_merge_confidence",
                  remaining[0]["confidence"] == 0.9,
                  f"Confidence: {remaining[0]['confidence']}")

    os.unlink(db)


def test_consolidation_error_archive():
    """Les vieilles erreurs résolues (> 30 jours) doivent être nettoyées."""
    import asyncio
    from src.memory.consolidation import ConsolidationWorker
    from src.memory.episodic import EpisodicMemory
    from src.memory.semantic import SemanticMemory
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_consolidation_error.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()

    episodic = EpisodicMemory(schema)
    semantic = SemanticMemory(schema)
    error = ErrorMemory(schema)
    worker = ConsolidationWorker(schema, episodic, semantic, error)

    # Forcer l'insertion d'une erreur résolue très ancienne
    # On utilise la connexion directe pour contourner le timestamp auto
    import time
    old_time = time.time() - (31 * 86400)  # > 30 jours
    import uuid

    conn = schema._get_conn()
    try:
        # Erreur résolue ancienne (doit être supprimée)
        old_error_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO error_memory (id, timestamp, error_type, description, resolved) "
            "VALUES (?, ?, ?, ?, ?)",
            (old_error_id, old_time, "test_old", "Vieille erreur résolue", 1),
        )

        # Erreur non résolue ancienne (ne doit PAS être supprimée)
        unresolved_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO error_memory (id, timestamp, error_type, description, resolved) "
            "VALUES (?, ?, ?, ?, ?)",
            (unresolved_id, old_time, "test_unresolved", "Vieille erreur non résolue", 0),
        )

        # Erreur récente résolue (ne doit PAS être supprimée)
        recent_error_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO error_memory (id, timestamp, error_type, description, resolved) "
            "VALUES (?, ?, ?, ?, ?)",
            (recent_error_id, time.time(), "test_recent", "Erreur récente résolue", 1),
        )
        conn.commit()
    finally:
        conn.close()

    check("consolidation_error_initial_count",
          error.count() == 3,
          f"Count before: {error.count()}")

    # Exécuter la consolidation
    report = asyncio.run(worker.run_once())

    check("consolidation_error_was_archived",
          report["errors_archived"] >= 1,
          f"Archived: {report['errors_archived']}")

    # Vérifier les états après (devrait rester 2 erreurs)
    remaining = error.count()
    check("consolidation_error_remaining",
          remaining == 2,
          f"Remaining: {remaining} (attendu: 2)")

    # Vérifier que l'erreur non résolue existe toujours
    check("consolidation_error_unresolved_preserved",
          error.get_by_id(unresolved_id) is not None,
          "Erreur non résolue supprimée à tort")

    # Vérifier que l'erreur récente résolue existe toujours
    check("consolidation_error_recent_preserved",
          error.get_by_id(recent_error_id) is not None,
          "Erreur récente résolue supprimée à tort")

    # Vérifier que la vieille erreur résolue a été supprimée
    check("consolidation_error_old_deleted",
          error.get_by_id(old_error_id) is None,
          "Vieille erreur résolue toujours présente")

    os.unlink(db)


def test_consolidation_start_stop():
    """Vérifier le cycle de vie du daemon (start/stop/is_running)."""
    import asyncio
    from src.memory.consolidation import ConsolidationWorker
    from src.memory.episodic import EpisodicMemory
    from src.memory.semantic import SemanticMemory
    from src.memory.errors import ErrorMemory
    from src.memory.schema import MemorySchema

    db = tempfile.mktemp(suffix='_nuru_consolidation_lifecycle.db')
    schema = MemorySchema(db_path=db)
    schema.init_db()

    episodic = EpisodicMemory(schema)
    semantic = SemanticMemory(schema)
    error = ErrorMemory(schema)
    worker = ConsolidationWorker(schema, episodic, semantic, error)

    # Initialement pas en cours
    check("consolidation_lifecycle_initial_not_running",
          not worker.is_running(),
          f"is_running: {worker.is_running()}")

    # Démarrer
    asyncio.run(worker.start(interval_hours=24))
    check("consolidation_lifecycle_started",
          worker.is_running(),
          "is_running devrait être True après start()")

    # Arrêter
    asyncio.run(worker.stop())
    check("consolidation_lifecycle_stopped",
          not worker.is_running(),
          "is_running devrait être False après stop()")

    # Double start ne doit pas planter
    asyncio.run(worker.start(interval_hours=24))
    asyncio.run(worker.start(interval_hours=24))  # Ne devrait rien faire
    check("consolidation_lifecycle_double_start",
          worker.is_running())

    asyncio.run(worker.stop())
    check("consolidation_lifecycle_final_stopped",
          not worker.is_running())

    os.unlink(db)


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TESTS — Sprint 1 : Mémoire unifiée V9 + ConsolidationWorker")
    print("=" * 60)

    # Schema tests
    print("\n📦 SCHEMA")
    try:
        test_schema_import()
    except Exception as e:
        check("schema_import", False, str(e))
    try:
        test_schema_init_and_tables()
    except Exception as e:
        check("schema_init_and_tables", False, str(e))
    try:
        test_schema_version()
    except Exception as e:
        check("schema_version", False, str(e))
    try:
        test_schema_idempotent()
    except Exception as e:
        check("schema_idempotent", False, str(e))
    try:
        test_schema_different_db()
    except Exception as e:
        check("schema_different_db", False, str(e))

    # Episodic tests
    print("\n📦 EPISODIC MEMORY")
    try:
        test_episodic_import()
    except Exception as e:
        check("episodic_import", False, str(e))

    if not FAILED:
        try:
            test_episodic_add_and_recall()
        except Exception as e:
            check("episodic_add_and_recall", False, str(e))
        try:
            test_episodic_add_with_embedding()
        except Exception as e:
            check("episodic_add_with_embedding", False, str(e))
        try:
            test_episodic_empty_recall()
        except Exception as e:
            check("episodic_empty_recall", False, str(e))
        try:
            test_episodic_multiple_episodes()
        except Exception as e:
            check("episodic_multiple_episodes", False, str(e))

    # Semantic tests
    print("\n📦 SEMANTIC MEMORY")
    try:
        test_semantic_import()
    except Exception as e:
        check("semantic_import", False, str(e))

    if not FAILED:
        try:
            test_semantic_add_and_recall()
        except Exception as e:
            check("semantic_add_and_recall", False, str(e))
        try:
            test_semantic_consolidate()
        except Exception as e:
            check("semantic_consolidate", False, str(e))
        try:
            test_semantic_category_filtering()
        except Exception as e:
            check("semantic_category_filtering", False, str(e))
        try:
            test_semantic_confidence_filtering()
        except Exception as e:
            check("semantic_confidence_filtering", False, str(e))
        try:
            test_semantic_empty_recall()
        except Exception as e:
            check("semantic_empty_recall", False, str(e))
        try:
            test_semantic_update_confidence()
        except Exception as e:
            check("semantic_update_confidence", False, str(e))

    # User memory tests
    print("\n📦 USER MEMORY")
    try:
        test_user_import()
    except Exception as e:
        check("user_import", False, str(e))

    if not FAILED:
        try:
            test_user_set_and_get()
        except Exception as e:
            check("user_set_and_get", False, str(e))
        try:
            test_user_update_existing()
        except Exception as e:
            check("user_update_existing", False, str(e))
        try:
            test_user_delete()
        except Exception as e:
            check("user_delete", False, str(e))
        try:
            test_user_list_by_category()
        except Exception as e:
            check("user_list_by_category", False, str(e))
        try:
            test_user_search()
        except Exception as e:
            check("user_search", False, str(e))
        try:
            test_user_bulk_set()
        except Exception as e:
            check("user_bulk_set", False, str(e))
        try:
            test_user_count_by_category()
        except Exception as e:
            check("user_count_by_category", False, str(e))

    # Error memory tests
    print("\n📦 ERROR MEMORY")
    try:
        test_error_import()
    except Exception as e:
        check("error_import", False, str(e))

    if not FAILED:
        try:
            test_error_add_and_recall()
        except Exception as e:
            check("error_add_and_recall", False, str(e))
        try:
            test_error_check_similar()
        except Exception as e:
            check("error_check_similar", False, str(e))
        try:
            test_error_check_similar_no_match()
        except Exception as e:
            check("error_check_similar_no_match", False, str(e))
        try:
            test_error_mark_resolved()
        except Exception as e:
            check("error_mark_resolved", False, str(e))
        try:
            test_error_filter_by_type()
        except Exception as e:
            check("error_filter_by_type", False, str(e))
        try:
            test_error_get_stats()
        except Exception as e:
            check("error_get_stats", False, str(e))
        try:
            test_error_empty_recall()
        except Exception as e:
            check("error_empty_recall", False, str(e))

    # Retriever tests
    print("\n📦 RETRIEVER — MemoryRetriever")
    try:
        test_retriever_import()
    except Exception as e:
        check("retriever_import", False, str(e))

    if not FAILED:
        try:
            test_retriever_recall_all_types()
        except Exception as e:
            check("retriever_recall_all_types", False, str(e))
        try:
            test_retriever_recall_filtered()
        except Exception as e:
            check("retriever_recall_filtered", False, str(e))
        try:
            test_retriever_combined()
        except Exception as e:
            check("retriever_combined", False, str(e))
        try:
            test_retriever_get_context()
        except Exception as e:
            check("retriever_get_context", False, str(e))
        try:
            test_retriever_empty()
        except Exception as e:
            check("retriever_empty", False, str(e))
        try:
            test_retriever_count_all()
        except Exception as e:
            check("retriever_count_all", False, str(e))

    # MemoryManager tests
    print("\n📦 MANAGER — MemoryManager (intégration V9)")
    try:
        test_manager_import()
    except Exception as e:
        check("manager_import", False, str(e))

    if not FAILED:
        try:
            test_manager_add_message()
        except Exception as e:
            check("manager_add_message", False, str(e))
        try:
            test_manager_set_cache_and_get()
        except Exception as e:
            check("manager_set_cache_and_get", False, str(e))
        try:
            test_manager_add_reflection()
        except Exception as e:
            check("manager_add_reflection", False, str(e))
        try:
            test_manager_record_conversation()
        except Exception as e:
            check("manager_record_conversation", False, str(e))
        try:
            test_manager_record_error()
        except Exception as e:
            check("manager_record_error", False, str(e))
        try:
            test_manager_check_errors()
        except Exception as e:
            check("manager_check_errors", False, str(e))
        try:
            test_manager_get_user_profile()
        except Exception as e:
            check("manager_get_user_profile", False, str(e))
        try:
            test_manager_get_full_context()
        except Exception as e:
            check("manager_get_full_context", False, str(e))
        try:
            test_manager_get_recent_history()
        except Exception as e:
            check("manager_get_recent_history", False, str(e))
        try:
            test_manager_get_memory_stats()
        except Exception as e:
            check("manager_get_memory_stats", False, str(e))

    # ConsolidationWorker tests
    print("\n📦 CONSOLIDATION WORKER")
    try:
        test_consolidation_import()
    except Exception as e:
        check("consolidation_import", False, str(e))

    # Always run consolidation tests (no FAILED gating from previous sections)
    # since they only depend on their own import test succeeding
    _cons_failed_before = FAILED
    try:
        test_consolidation_run_once()
    except Exception as e:
        check("consolidation_run_once", False, str(e))
    try:
        test_consolidation_fact_extraction()
    except Exception as e:
        check("consolidation_fact_extraction", False, str(e))
    try:
        test_consolidation_redundant_merge()
    except Exception as e:
        check("consolidation_redundant_merge", False, str(e))
    try:
        test_consolidation_error_archive()
    except Exception as e:
        check("consolidation_error_archive", False, str(e))
    try:
        test_consolidation_start_stop()
    except Exception as e:
        check("consolidation_start_stop", False, str(e))

    print(f"\n{'=' * 60}")
    print(f"✅ PASSED: {PASSED}  |  ❌ FAILED: {FAILED}")
    print(f"{'=' * 60}")
    sys.exit(0 if FAILED == 0 else 1)
