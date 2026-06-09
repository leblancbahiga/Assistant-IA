"""
Tests unitaires — Sprint 3 (Recherche fichiers + Outils mémoire-safe).
"""
import sys; sys.path.insert(0, '.')
import os
import time
import json


# ═══════════════════════════════════════════
# Tests file_search
# ═══════════════════════════════════════════

def test_file_search_import():
    from src.rag.file_search import (
        grep_documents, SUPPORTED_EXTS, MAX_FILE_SIZE,
        _is_nuru_brain_path, _extract_pdf_text,
        _get_cached, _set_cache, GREP_CACHE_TTL,
    )
    assert '.pdf' in SUPPORTED_EXTS
    assert MAX_FILE_SIZE > 0
    assert GREP_CACHE_TTL == 60
    print("  \u2705 file_search_import")


def test_nuru_brain_exclusion():
    from src.rag.file_search import _is_nuru_brain_path
    nb_path = os.path.expanduser("~/Nuru_Brain/sources/cv.md")
    assert _is_nuru_brain_path(nb_path), "devrait detecter Nuru_Brain"
    docs_path = os.path.expanduser("~/Documents/cv.md")
    assert not _is_nuru_brain_path(docs_path), "ne devrait PAS detecter"
    print("  \u2705 nuru_brain_exclusion")


def test_grep_cache():
    from src.rag.file_search import _set_cache, _get_cached
    data = [{"path": "/tmp/test.pdf", "filename": "test.pdf", "score": 0.8}]

    # Cache miss
    assert _get_cached("inexistant") is None
    print("  \u2705 grep_cache_miss")

    # Cache set/get
    _set_cache("test query", data)
    cached = _get_cached("test query")
    assert cached == data, f"devrait retourner les donnees, got {cached}"
    print("  \u2705 grep_cache_set_get")


def test_pdf_extraction_invalid():
    from src.rag.file_search import _extract_pdf_text
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, mode="wb") as f:
        f.write(b"%PDF-1.4 fake content")
        path = f.name

    text = _extract_pdf_text(path)
    assert text == "", f"PDF invalide devrait retourner vide, got '{text[:20]}'"
    os.unlink(path)
    print("  \u2705 pdf_extraction_invalid")


def test_grep_empty_query():
    from src.rag.file_search import grep_documents
    results = grep_documents("")
    assert results == [], "requete vide = 0 resultats"
    results = grep_documents(" ")
    assert results == [], "requete espace = 0 resultats"
    print("  \u2705 grep_empty_query")


# ═══════════════════════════════════════════
# Tests read_tool
# ═══════════════════════════════════════════

def test_read_tool_sanitization():
    from src.rag.read_tool import find_and_read_file
    assert "[ERREUR" in find_and_read_file("../etc/passwd")
    assert "[ERREUR" in find_and_read_file("/etc/passwd")
    assert "[ERREUR" in find_and_read_file("")
    print("  \u2705 read_tool_sanitization")


def test_read_tool_not_found():
    from src.rag.read_tool import find_and_read_file, ALLOWED_DIRS, EXCLUDED_DIRS
    # Vérifier la structure sans déclencher os.walk
    assert len(ALLOWED_DIRS) >= 3
    assert any("Nuru_Brain" in d for d in EXCLUDED_DIRS)
    print("  \u2705 read_tool_not_found (structure)")


# ═══════════════════════════════════════════
# Tests integration Score Gate + Grep
# ═══════════════════════════════════════════

def test_score_gate_integration():
    import asyncio
    from src.rag_engine import RAGEngine

    async def _test():
        engine = RAGEngine()
        ctx, result = await engine.retrieve("rendement riz")

        # Le contexte doit TOUJOURS contenir l'en-tête de confiance
        assert "[CONFIANCE RAG:" in ctx
        
        # Le diagnostic doit être présent
        assert result.diagnostic is not None
        assert "vectorielle" in result.diagnostic["strategies_tried"]
        
        # Confidence label doit être défini
        assert result.confidence_label in ("HAUTE", "MOYENNE", "FAIBLE", "ABSENT")

    asyncio.run(_test())
    print("  \u2705 score_gate_integration")


# ═══════════════════════════════════════════
# Exécution
# ═══════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_file_search_import,
        test_nuru_brain_exclusion,
        test_grep_cache,
        test_pdf_extraction_invalid,
        test_grep_empty_query,
        test_read_tool_sanitization,
        test_read_tool_not_found,
        test_score_gate_integration,
    ]
    
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            import traceback
            print(f"  \u274c {test.__name__}: {e}")
            traceback.print_exc()
    
    total = len(tests)
    print(f"\n{'=' * 40}")
    print(f"Sprint 3 — {passed}/{total} tests OK"
          + ("" if passed == total else f", {total-passed} ECHEC"))
