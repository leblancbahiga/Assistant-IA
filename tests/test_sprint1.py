"""
Tests unitaires — Sprint 1 (Observabilité).
"""
import sys; sys.path.insert(0, '.')
import json
import time


# ═══════════════════════════════════════════
# Tests RAGDiagnostic
# ═══════════════════════════════════════════

def test_diagnostic_creation():
    from src.rag.diagnostics import RAGDiagnostic
    diag = RAGDiagnostic(query="test query")
    assert diag.query == "test query"
    assert diag.strategies_tried == []
    assert diag.verdict == ""
    print("  \u2705 diagnostic_creation")


def test_diagnostic_cycle_complet():
    from src.rag.diagnostics import RAGDiagnostic
    diag = RAGDiagnostic(query="rendement riz")
    diag.start()
    diag.log_strategy("vectorielle", 3, 0.65, True, 45.2)
    diag.log_strategy("fts", 0, 0.0, False, 12.1)
    diag.set_verdict("HAUTE")
    time.sleep(0.001)
    diag.stop()

    assert len(diag.strategies_tried) == 2
    assert diag.verdict == "HAUTE"
    assert diag.timing_ms > 0, f"timing_ms should be > 0, got {diag.timing_ms}"
    assert diag.strategies_results["vectorielle"]["found"] == 3
    assert diag.strategies_results["fts"]["hit"] is False
    print("  \u2705 diagnostic_cycle_complet")


def test_diagnostic_serialisation():
    from src.rag.diagnostics import RAGDiagnostic
    diag = RAGDiagnostic(query="test")
    diag.start()
    time.sleep(0.002)
    diag.log_strategy("vectorielle", 1, 0.5, True, 10.0)
    diag.set_verdict("MOYENNE")
    diag.stop()

    d = diag.to_dict()
    assert d["query"] == "test", f"query mismatch: {d['query']}"
    assert d["verdict"] == "MOYENNE"
    assert d["timing_ms"] > 0

    j = diag.to_json()
    parsed = json.loads(j)
    assert parsed["verdict"] == "MOYENNE"

    s = diag.summary()
    assert "1" in s
    assert "MOYENNE" in s
    print("  \u2705 diagnostic_serialisation")


def test_diagnostic_index_stats():
    from src.rag.diagnostics import RAGDiagnostic
    diag = RAGDiagnostic()
    diag.set_index_stats({"total_docs": 446})
    d = diag.to_dict()
    assert d["index_stats"]["total_docs"] == 446
    print("  \u2705 diagnostic_index_stats")


def test_diagnostic_start_stop():
    from src.rag.diagnostics import RAGDiagnostic
    diag = RAGDiagnostic()
    diag.start()
    time.sleep(0.002)
    diag.stop()
    assert diag.timing_ms > 0, f"timing_ms={diag.timing_ms}"
    print("  \u2705 diagnostic_start_stop")


# ═══════════════════════════════════════════
# Tests IndexHealthReport
# ═══════════════════════════════════════════

def test_index_health_structure():
    from src.rag.index_health import IndexHealthReport
    r = IndexHealthReport()
    assert hasattr(r, "total_in_index")
    assert hasattr(r, "summary")
    print("  \u2705 index_health_structure")


def test_index_health_summary():
    from src.rag.index_health import IndexHealthReport
    r = IndexHealthReport()
    s = r.summary()
    assert "0" in s
    print("  \u2705 index_health_summary")


def test_index_health_to_dict():
    from src.rag.index_health import IndexHealthReport
    r = IndexHealthReport()
    r.total_in_index = 100
    r.files_on_disk = 50
    r.matched = 45
    d = r.to_dict()
    assert d["total_in_index"] == 100
    assert "status" in d
    assert d["match_pct"] == 90.0
    print("  \u2705 index_health_to_dict")


# ═══════════════════════════════════════════
# Tests TraceCollector
# ═══════════════════════════════════════════

def test_trace_collector():
    import asyncio
    import sqlite3
    from src.learning.trace_collector import TraceCollector

    async def _run():
        tc = TraceCollector()
        await tc.start()
        diag_data = json.dumps({"verdict": "HAUTE", "strategies_tried": ["vec"]})
        await tc.record(query="q", response="r", mode="RAG", rag_diagnostic=diag_data)
        await asyncio.sleep(0.5)
        conn = sqlite3.connect(tc.db_path)
        row = conn.execute(
            "SELECT rag_diagnostic FROM traces ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        await tc.stop()
        assert row is not None
        d = json.loads(row[0])
        assert d["verdict"] == "HAUTE"

    asyncio.run(_run())
    print("  \u2705 trace_collector")


# ═══════════════════════════════════════════
# Exécution
# ═══════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_diagnostic_creation,
        test_diagnostic_cycle_complet,
        test_diagnostic_serialisation,
        test_diagnostic_index_stats,
        test_diagnostic_start_stop,
        test_index_health_structure,
        test_index_health_summary,
        test_index_health_to_dict,
        test_trace_collector,
    ]
    
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  \u274c {test.__name__}: {e}")
    
    total = len(tests)
    print(f"\n{'=' * 40}")
    print(f"Sprint 1 \u2014 {passed}/{total} tests OK \u2705" if passed == total else
          f"Sprint 1 \u2014 {passed}/{total} tests, {total-passed} ECHEC \u274c")
