"""
Tests unitaires pour Sprint 9 — Dashboard V10 (StatsPage, ToolTester).

Ces tests NE lancent PAS PySide6 — ils testent uniquement les helpers
de formatage et la logique de calcul (pas le rendu Qt).

Exécution :
    pytest tests/test_sprint9_v10_dashboard.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ajouter le projet au path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ══════════════════════════════════════════════════════════════════════════
#  Helper functions à tester (copiées depuis stats_page.py)
# ══════════════════════════════════════════════════════════════════════════

def _pct_color(pct: float, good: float = 50, warn: float = 80) -> str:
    if pct < good:
        return "#39FF14"
    elif pct < warn:
        return "#FF8C00"
    return "#FF3333"


def _bool_color(val: float, ideal_high: bool = True) -> str:
    if ideal_high:
        if val >= 0.8:
            return "#39FF14"
        elif val >= 0.5:
            return "#FF8C00"
        return "#FF3333"
    else:
        if val <= 0.1:
            return "#39FF14"
        elif val <= 0.3:
            return "#FF8C00"
        return "#FF3333"


def _format_ms(ms: float) -> str:
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _format_pct(val: float) -> str:
    return f"{val * 100:.1f}%"


# ══════════════════════════════════════════════════════════════════════════
#  Helper functions à tester (copiées depuis tool_tester.py)
# ══════════════════════════════════════════════════════════════════════════

FORMAT_MAPPING = {
    "Word (.docx)": "word",
    "PDF (.pdf)": "pdf",
    "PowerPoint (.pptx)": "pptx",
    "Excel (.xlsx)": "xlsx",
    "Markdown (.md)": "markdown",
}

EXTENSION_MAPPING = {
    "word": ".docx",
    "pdf": ".pdf",
    "pptx": ".pptx",
    "xlsx": ".xlsx",
    "markdown": ".md",
}


def get_format_enum(display_name: str) -> str:
    return FORMAT_MAPPING.get(display_name, "word")


def get_extension(format_enum: str) -> str:
    return EXTENSION_MAPPING.get(format_enum, ".docx")


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : _pct_color
# ══════════════════════════════════════════════════════════════════════════


class TestPctColor:
    """Teste la couleur des pourcentages — vert/orange/rouge."""

    def test_green_below_good(self):
        assert _pct_color(30) == "#39FF14", "30% devrait être vert"

    def test_orange_between_good_and_warn(self):
        assert _pct_color(70) == "#FF8C00", "70% devrait être orange"

    def test_red_above_warn(self):
        assert _pct_color(90) == "#FF3333", "90% devrait être rouge"

    def test_exact_good(self):
        assert _pct_color(50) == "#FF8C00", "50% n'est pas < 50 donc orange"

    def test_exact_warn(self):
        assert _pct_color(80) == "#FF3333", "80% n'est pas < 80 donc rouge"

    def test_zero(self):
        assert _pct_color(0) == "#39FF14", "0% devrait être vert"

    def test_custom_thresholds(self):
        assert _pct_color(60, good=30, warn=70) == "#FF8C00", "60% avec good=30, warn=70"
        assert _pct_color(80, good=30, warn=70) == "#FF3333", "80% avec warn=70"


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : _bool_color
# ══════════════════════════════════════════════════════════════════════════


class TestBoolColor:
    """Teste la couleur des valeurs booléennes (0-1)."""

    def test_high_ideal_high(self):
        assert _bool_color(0.9) == "#39FF14", "0.9 avec ideal_high=True"
        assert _bool_color(0.95) == "#39FF14", "0.95"
        assert _bool_color(1.0) == "#39FF14", "1.0"

    def test_mid_ideal_high(self):
        assert _bool_color(0.6) == "#FF8C00", "0.6 avec ideal_high=True"
        assert _bool_color(0.5) == "#FF8C00", "0.5 (limite)"

    def test_low_ideal_high(self):
        assert _bool_color(0.2) == "#FF3333", "0.2 avec ideal_high=True"
        assert _bool_color(0.0) == "#FF3333", "0.0"

    def test_high_ideal_low(self):
        assert _bool_color(0.05, ideal_high=False) == "#39FF14", "0.05 avec ideal_high=False"
        assert _bool_color(0.0, ideal_high=False) == "#39FF14", "0.0 avec ideal_high=False"
        assert _bool_color(0.1, ideal_high=False) == "#39FF14", "0.1 (limite)"

    def test_mid_ideal_low(self):
        assert _bool_color(0.2, ideal_high=False) == "#FF8C00", "0.2 avec ideal_high=False"
        assert _bool_color(0.3, ideal_high=False) == "#FF8C00", "0.3 (limite)"

    def test_low_ideal_low(self):
        assert _bool_color(0.5, ideal_high=False) == "#FF3333", "0.5 avec ideal_high=False"
        assert _bool_color(1.0, ideal_high=False) == "#FF3333", "1.0 avec ideal_high=False"


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : _format_ms
# ══════════════════════════════════════════════════════════════════════════


class TestFormatMs:
    """Teste le formatage des millisecondes."""

    def test_under_1000(self):
        assert _format_ms(500) == "500ms"
        assert _format_ms(0) == "0ms"
        assert _format_ms(999) == "999ms"

    def test_over_1000(self):
        assert _format_ms(1500) == "1.5s"
        assert _format_ms(1000) == "1.0s"
        assert _format_ms(10000) == "10.0s"

    def test_edge_cases(self):
        assert _format_ms(1000) == "1.0s"
        assert _format_ms(1001) == "1.0s"


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : _format_pct
# ══════════════════════════════════════════════════════════════════════════


class TestFormatPct:
    """Teste le formatage des pourcentages."""

    def test_basic(self):
        assert _format_pct(0.857) == "85.7%"
        assert _format_pct(0.0) == "0.0%"
        assert _format_pct(1.0) == "100.0%"
        assert _format_pct(0.5) == "50.0%"

    def test_negative(self):
        result = _format_pct(-0.5)
        assert result == "-50.0%"

    def test_over_one(self):
        assert _format_pct(1.5) == "150.0%"


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : ToolTester format mapping
# ══════════════════════════════════════════════════════════════════════════


class TestToolTesterFormatMapping:
    """Teste le mapping des formats d'affichage vers enum."""

    def test_all_formats(self):
        assert get_format_enum("Word (.docx)") == "word"
        assert get_format_enum("PDF (.pdf)") == "pdf"
        assert get_format_enum("PowerPoint (.pptx)") == "pptx"
        assert get_format_enum("Excel (.xlsx)") == "xlsx"
        assert get_format_enum("Markdown (.md)") == "markdown"

    def test_unknown_fallback(self):
        assert get_format_enum("Unknown") == "word"

    def test_extension_mapping(self):
        assert get_extension("word") == ".docx"
        assert get_extension("pdf") == ".pdf"
        assert get_extension("pptx") == ".pptx"
        assert get_extension("xlsx") == ".xlsx"
        assert get_extension("markdown") == ".md"

    def test_unknown_extension_fallback(self):
        assert get_extension("unknown") == ".docx"


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : V10 Navigation integration
# ══════════════════════════════════════════════════════════════════════════


class TestV10Navigation:
    """Teste que la navigation V10 est bien configurée dans NAV_GROUPS."""

    def test_v10_group_present(self):
        """Vérifie que NURU V10 group existe."""
        from src.ui.dashboard import NAV_GROUPS
        groups = [g["label"] for g in NAV_GROUPS]
        assert "NURU V10" in groups, "Le groupe NURU V10 doit être dans NAV_GROUPS"

    def test_v10_items_present(self):
        """Vérifie que les slugs V10 sont dans le groupe."""
        from src.ui.dashboard import NAV_GROUPS
        v10_group = [g for g in NAV_GROUPS if g["label"] == "NURU V10"][0]
        slugs = [slug for _, slug in v10_group["items"]]
        assert "stats_v10" in slugs, "stats_v10 doit être dans les items"
        assert "tools_v10" in slugs, "tools_v10 doit être dans les items"

    def test_v10_placeholder_pages(self):
        """Vérifie que les pages V10 sont dans PLACEHOLDER_PAGES."""
        from src.ui.dashboard import PLACEHOLDER_PAGES
        assert "stats_v10" in PLACEHOLDER_PAGES
        assert "tools_v10" in PLACEHOLDER_PAGES


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : DocumentGenerator Spec (integration test)
# ══════════════════════════════════════════════════════════════════════════


class TestDocumentSpec:
    """Teste la validation des specs de DocumentGenerator."""

    def test_valid_spec(self):
        from src.tools.document import DocumentGenerator, DocumentSpec, DocSection, DocFormat
        gen = DocumentGenerator()
        spec = DocumentSpec(
            title="Test",
            format=DocFormat.MARKDOWN,
            sections=[DocSection(title="Section 1", content="Contenu")],
        )
        errors = gen.validate_spec(spec)
        assert errors == [], f"Aucune erreur attendue, obtenu: {errors}"

    def test_missing_title(self):
        from src.tools.document import DocumentGenerator, DocumentSpec, DocSection, DocFormat
        gen = DocumentGenerator()
        spec = DocumentSpec(
            title="",
            format=DocFormat.MARKDOWN,
            sections=[DocSection(title="Section 1", content="Contenu")],
        )
        errors = gen.validate_spec(spec)
        assert "Titre requis" in errors

    def test_missing_sections(self):
        from src.tools.document import DocumentGenerator, DocumentSpec, DocSection, DocFormat
        gen = DocumentGenerator()
        spec = DocumentSpec(
            title="Test",
            format=DocFormat.MARKDOWN,
            sections=[],
        )
        errors = gen.validate_spec(spec)
        assert "Au moins une section requise" in errors

    def test_invalid_format(self):
        from src.tools.document import DocumentGenerator, DocumentSpec, DocSection
        gen = DocumentGenerator()
        # Format invalide
        spec = DocumentSpec(
            title="Test",
            format="invalid",  # type: ignore
            sections=[DocSection(title="Section 1", content="Contenu")],
        )
        errors = gen.validate_spec(spec)
        assert any("Format non supporté" in e for e in errors)

    def test_generate_markdown_string(self):
        from src.tools.document import DocumentGenerator, DocumentSpec, DocSection, DocFormat
        gen = DocumentGenerator()
        spec = DocumentSpec(
            title="Rapport test",
            format=DocFormat.MARKDOWN,
            sections=[DocSection(title="Intro", content="Contenu de test")],
            metadata={"Auteur": "NURU"},
        )
        md = gen.generate_markdown_string(spec)
        assert "# Rapport test" in md
        assert "**Auteur** : NURU" in md
        assert "## Intro" in md
        assert "Contenu de test" in md

    def test_generate_json(self):
        from src.tools.document import DocumentGenerator, DocumentSpec, DocSection, DocFormat
        gen = DocumentGenerator()
        spec = DocumentSpec(
            title="Test JSON",
            format=DocFormat.WORD,
            sections=[DocSection(title="S1", content="C1")],
        )
        data = gen.generate_json(spec)
        assert data["title"] == "Test JSON"
        assert data["format"] == "word"
        assert len(data["sections"]) == 1
        assert data["sections"][0]["title"] == "S1"


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : WebResearcher helpers
# ══════════════════════════════════════════════════════════════════════════


class TestWebResearcherHelpers:
    """Teste les helpers de WebResearcher."""

    def test_score_relevance(self):
        from src.research.web import WebResearcher
        r = WebResearcher()
        score = r.score_relevance(
            "rapport agricole RDC",
            "Rapport agricole RDC 2024",
            "Analyse du secteur agricole en RDC",
        )
        assert score > 0, f"Score devrait être > 0, obtenu: {score}"

    def test_deduplicate(self):
        from src.research.web import WebResearcher, SearchResult
        r = WebResearcher()
        results = [
            SearchResult(url="https://a.com", title="A", snippet="", relevance_score=0.5),
            SearchResult(url="https://a.com", title="A dup", snippet="", relevance_score=0.4),
            SearchResult(url="https://b.com", title="B", snippet="", relevance_score=0.6),
        ]
        deduped = r.deduplicate(results)
        assert len(deduped) == 2, f"Devrait avoir 2 résultats, obtenu: {len(deduped)}"

    def test_filter_by_relevance(self):
        from src.research.web import WebResearcher, SearchResult
        r = WebResearcher()
        results = [
            SearchResult(url="https://a.com", title="A", snippet="", relevance_score=0.8),
            SearchResult(url="https://b.com", title="B", snippet="", relevance_score=0.3),
            SearchResult(url="https://c.com", title="C", snippet="", relevance_score=0.6),
        ]
        filtered = r.filter_by_relevance(results, 0.5)
        assert len(filtered) == 2, f"Devrait avoir 2 résultats, obtenu: {len(filtered)}"

    def test_rank_results(self):
        from src.research.web import WebResearcher, SearchResult
        r = WebResearcher()
        results = [
            SearchResult(url="https://a.com", title="A", snippet="", relevance_score=0.3),
            SearchResult(url="https://b.com", title="B", snippet="", relevance_score=0.9),
            SearchResult(url="https://c.com", title="C", snippet="", relevance_score=0.6),
        ]
        ranked = r.rank_results(results)
        assert ranked[0].relevance_score == 0.9, "Le premier doit être le plus pertinent"
        assert ranked[1].relevance_score == 0.6
        assert ranked[2].relevance_score == 0.3


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : ToolRegistry
# ══════════════════════════════════════════════════════════════════════════


class TestToolRegistry:
    """Teste les opérations du registre d'outils."""

    def test_register_list(self):
        from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter
        r = ToolRegistry()
        tool = ToolDefinition(
            name="test_tool",
            description="Un outil de test",
            category="document",
            parameters=[ToolParameter(name="param1", type="str", description="Un paramètre")],
        )
        r.register(tool)
        tools = r.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "test_tool"

    def test_list_by_category(self):
        from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter
        r = ToolRegistry()
        r.register(ToolDefinition(
            name="doc_gen", description="", category="document", parameters=[]))
        r.register(ToolDefinition(
            name="web_search", description="", category="web", parameters=[]))
        docs = r.list_by_category("document")
        assert len(docs) == 1
        assert docs[0].name == "doc_gen"

    def test_unregister(self):
        from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter
        r = ToolRegistry()
        r.register(ToolDefinition(name="temp", description="", category="test", parameters=[]))
        assert r.unregister("temp") is True
        assert r.unregister("nonexistent") is False

    def test_search(self):
        from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter
        r = ToolRegistry()
        r.register(ToolDefinition(name="document_generator", description="Génère des documents Word/PDF", category="document", parameters=[]))
        r.register(ToolDefinition(name="web_researcher", description="Recherche sur le web", category="web", parameters=[]))
        results = r.search("document")
        names = [t.name for t in results]
        assert "document_generator" in names


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : PerformanceTracker helpers
# ══════════════════════════════════════════════════════════════════════════


class TestPerformanceTrackerOperations:
    """Teste les opérations basiques du PerformanceTracker."""

    def test_record_and_count(self):
        import tempfile
        import os
        from src.learning.tracker import PerformanceTracker
        db_path = os.path.join(tempfile.gettempdir(), "test_perf_v10.db")
        # Nettoyer si existe
        if os.path.exists(db_path):
            os.remove(db_path)
        tracker = PerformanceTracker(db_path=db_path)
        tracker.record("rag_recall@5", 0.85, category="rag")
        tracker.record("response_time_ms", 3200.0, category="response")
        count = tracker.count()
        assert count >= 2, f"Au moins 2 métriques, obtenu: {count}"
        # Nettoyage
        os.remove(db_path)

    def test_record_and_averages(self):
        import tempfile
        import os
        from src.learning.tracker import PerformanceTracker
        db_path = os.path.join(tempfile.gettempdir(), "test_perf_v10_avg.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        tracker = PerformanceTracker(db_path=db_path)
        tracker.record("rag_recall@5", 0.80, category="rag")
        tracker.record("rag_recall@5", 0.90, category="rag")
        avgs = tracker.get_averages(category="rag", since_hours=24)
        assert "rag_recall@5" in avgs
        assert avgs["rag_recall@5"] == 0.85, f"Moyenne devrait être 0.85, obtenu: {avgs['rag_recall@5']}"
        os.remove(db_path)

    def test_summary(self):
        import tempfile
        import os
        from src.learning.tracker import PerformanceTracker
        db_path = os.path.join(tempfile.gettempdir(), "test_perf_summary.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        tracker = PerformanceTracker(db_path=db_path)
        tracker.record("rag_recall@5", 0.85, category="rag")
        tracker.record("rag_avg_score", 0.65, category="rag")
        summary = tracker.get_summary()
        assert "rag" in summary
        assert summary["rag"]["recall@5"] == 0.85
        assert summary["rag"]["avg_score"] == 0.65
        os.remove(db_path)

    def test_get_rag_metrics(self):
        import tempfile
        import os
        from src.learning.tracker import PerformanceTracker
        db_path = os.path.join(tempfile.gettempdir(), "test_rag_metrics.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        tracker = PerformanceTracker(db_path=db_path)
        tracker.record_rag_result("test query", 0.92, 0.75, False)
        metrics = tracker.get_rag_metrics()
        assert isinstance(metrics, dict)
        assert "recall@5" in metrics
        os.remove(db_path)

    def test_get_summary_structure(self):
        import tempfile
        import os
        from src.learning.tracker import PerformanceTracker
        db_path = os.path.join(tempfile.gettempdir(), "test_summary_struct.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        tracker = PerformanceTracker(db_path=db_path)
        summary = tracker.get_summary()
        # Vérifier la structure même avec des valeurs vides
        for key in ("rag", "response", "agent", "feedback"):
            assert key in summary, f"Clé {key} manquante dans le résumé"
            assert isinstance(summary[key], dict), f"{key} devrait être un dict"
        os.remove(db_path)
