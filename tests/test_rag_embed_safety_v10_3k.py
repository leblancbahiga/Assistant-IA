"""Tests B-Embed — Audit Bug.

rag_engine._ms_vector_search fait `if not embed` sur un np.ndarray multi-éléments.
Cela lève ValueError 'truth value of array is ambiguous' et fait silencieusement
retomber _ms_vector_search à [], perdant TOUS les résultats vectoriels pour le
MultiSearchOrchestrator.

Logs user observés :
    WARNING:src.rag_engine:⚠️ _ms_vector_search(vector) a échoué:
    The truth value of an array with more than one element is ambiguous.
"""
import pytest
import numpy as np


class FakeEmbedder:
    """Mock Embedder.embed_sync qui retourne un np.ndarray 2D simulant MLX."""
    def __init__(self, dim=4):
        # Shape (1, dim) comme MLX retourne naturellement
        self._arr = np.ones((1, dim), dtype=np.float32)
        self.call_count = 0
    def embed_sync(self, text, is_query=True):
        self.call_count += 1
        return self._arr


def test_truthiness_check_works_on_ndarray_2d():
    """Démonstration du bug : `if not embed` lève sur np.ndarray 2D."""
    embedder = FakeEmbedder()
    embed = embedder.embed_sync("hello")

    try:
        if not embed:
            result = "empty"
        else:
            result = "ok"
        raised = None
    except ValueError as e:
        raised = e

    assert raised is not None, (
        "Si raised is None : le bug n'est PAS démontré. "
        "Sans fix, np.ndarray(1,4) lève ValueError sur `if not embed`."
    )
    assert "ambiguous" in str(raised)


def test_safe_embed_check():
    """Le fix doit utiliser .size au lieu de truthiness directe."""
    embedder = FakeEmbedder()
    embed = embedder.embed_sync("hello")

    def is_empty(arr):
        if arr is None:
            return True
        if hasattr(arr, 'size'):
            return arr.size == 0
        if isinstance(arr, (list, tuple)):
            return len(arr) == 0
        return False

    assert not is_empty(embed), "Un array (1,4) ne doit pas être considéré comme vide"
    assert is_empty(None)
    assert is_empty(np.array([]))
    assert is_empty([])


def test_ms_vector_search_returns_results_not_empty_on_2d_embed():
    """Test d'intégration : avec un embed 2D normal, _ms_vector_search doit retourner des rows.

    Avant le fix : ValueError → fallback silencieux → [] → le user voit un RAG cassé.
    Après le fix : retourne les rows trouvés (même si empty DB → []).
    L'important : JAMAIS de crash silencieux sur un embed normal.
    """
    from src.rag_engine import RAGEngine

    # Mock les composants internes pour éviter de charger MLX et sqlite
    eng = RAGEngine.__new__(RAGEngine)
    eng.embedder = FakeEmbedder(dim=4)
    # DB mockée qui retourne 2 rows (vecteurs bidons compatibles sqlite-vec)
    class _FakeConn:
        def execute(self, *a, **k): return self
        def fetchall(self):
            return [
                ("contenu chunk 1", "doc1.pdf", 0.85),
                ("contenu chunk 2", "doc2.pdf", 0.72),
            ]
        def close(self): pass
    eng._get_conn = lambda: _FakeConn()

    # Sans le fix : ça lève ValueError capturé en WARNING silencieux dans un try global
    # Avec le fix : retourne les rows
    try:
        result = eng._ms_vector_search("bonjour", search_type="vector")
    except ValueError as e:
        # Si on arrive ici, le fix n'est pas appliqué
        pytest.fail(
            f"_ms_vector_search devrait gérer ndarray 2D sans crash. Got: {e}"
        )

    assert isinstance(result, list), f"Attendu list, got {type(result).__name__}"
    assert len(result) == 2, f"Attendu 2 résultats depuis la mock DB, got {len(result)}"
    assert result[0] == ("contenu chunk 1", "doc1.pdf", 0.85)

