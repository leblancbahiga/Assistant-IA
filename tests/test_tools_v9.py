"""Tests unitaires pour ToolRegistry + DocumentGenerator — Sprint 6"""
import json
import tempfile
from pathlib import Path

from src.tools.registry import ToolRegistry, ToolDefinition, ToolParameter
from src.tools.document import DocumentGenerator, DocumentSpec, DocFormat, DocSection


# ──────────────────────────────────────────────────
# Fixtures helpers
# ──────────────────────────────────────────────────

def _make_tool(name="tool_a", category="document", desc="A tool"):
    return ToolDefinition(
        name=name,
        description=desc,
        category=category,
        parameters=[ToolParameter(name="input", type="str", description="Input param")],
    )


def _make_doc(title="Rapport", sections=None, fmt=DocFormat.MARKDOWN, metadata=None):
    if sections is None:
        sections = [DocSection(title="Intro", content="Bonjour", level=1)]
    return DocumentSpec(title=title, format=fmt, sections=sections, metadata=metadata or {})


# ──────────────────────────────────────────────────
# ToolRegistry tests
# ──────────────────────────────────────────────────

class TestToolRegistry:

    def test_register_and_len(self):
        reg = ToolRegistry()
        reg.register(_make_tool("a"))
        reg.register(_make_tool("b"))
        assert len(reg) == 2

    def test_unregister_found(self):
        reg = ToolRegistry()
        reg.register(_make_tool("a"))
        assert reg.unregister("a") is True
        assert len(reg) == 0

    def test_unregister_not_found(self):
        reg = ToolRegistry()
        assert reg.unregister("ghost") is False

    def test_get(self):
        reg = ToolRegistry()
        t = _make_tool("x")
        reg.register(t)
        assert reg.get("x") is t
        assert reg.get("y") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(_make_tool("a"))
        reg.register(_make_tool("b"))
        assert len(reg.list_tools()) == 2

    def test_list_by_category(self):
        reg = ToolRegistry()
        reg.register(_make_tool("a", category="document"))
        reg.register(_make_tool("b", category="web"))
        assert len(reg.list_by_category("document")) == 1
        assert reg.list_by_category("document")[0].name == "a"

    def test_search(self):
        reg = ToolRegistry()
        reg.register(_make_tool("code_runner", desc="Run code"))
        reg.register(_make_tool("web_search", desc="Search web"))
        assert len(reg.search("code")) == 1
        assert len(reg.search("search")) == 1
        assert len(reg.search("xyz")) == 0

    def test_to_llm_schema(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t"))
        schemas = reg.to_llm_schema()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "t"
        assert "parameters" in schemas[0]

    def test_save_and_load(self):
        reg = ToolRegistry()
        reg.register(_make_tool("alpha", category="code"))
        reg.register(_make_tool("beta", category="memory"))
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        reg.save_to_file(path)

        reg2 = ToolRegistry()
        count = reg2.load_from_file(path)
        assert count == 2
        assert len(reg2) == 2
        assert reg2.get("alpha") is not None
        assert reg2.get("beta") is not None

    def test_load_from_file_count(self):
        """Vérifie que load_from_file retourne le bon nombre."""
        data = {"tools": [
            {"name": "t1", "description": "d1", "category": "c1", "parameters": []},
            {"name": "t2", "description": "d2", "category": "c2", "parameters": [
                {"name": "p", "type": "str", "description": "desc"}
            ]},
        ]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        reg = ToolRegistry()
        assert reg.load_from_file(path) == 2


# ──────────────────────────────────────────────────
# DocumentGenerator tests
# ──────────────────────────────────────────────────

class TestDocumentGenerator:

    def setup_method(self):
        self.gen = DocumentGenerator()

    def test_validate_valid(self):
        spec = _make_doc()
        assert self.gen.validate_spec(spec) == []

    def test_validate_no_title(self):
        spec = _make_doc(title="")
        errors = self.gen.validate_spec(spec)
        assert any("Titre requis" in e for e in errors)

    def test_validate_no_sections(self):
        spec = _make_doc(sections=[])
        errors = self.gen.validate_spec(spec)
        assert any("section" in e.lower() for e in errors)

    def test_validate_empty_section(self):
        spec = _make_doc(sections=[DocSection(title="", content="text")])
        errors = self.gen.validate_spec(spec)
        assert any("titre requis" in e.lower() for e in errors)

    def test_validate_bad_format(self):
        spec = _make_doc(fmt="csv")
        errors = self.gen.validate_spec(spec)
        assert any("format" in e.lower() for e in errors)

    def test_generate_markdown(self):
        spec = _make_doc(title="Mon Rapport", metadata={"Auteur": "NURU"})
        md = self.gen.generate_markdown(spec)
        assert "# Mon Rapport" in md
        assert "**Auteur** : NURU" in md
        assert "Bonjour" in md

    def test_generate_json(self):
        spec = _make_doc()
        result = self.gen.generate_json(spec)
        assert result["title"] == "Rapport"
        assert result["format"] == "markdown"
        assert len(result["sections"]) == 1

    def test_generate_from_template(self):
        template = "Bonjour {{name}}, votre score est {{score}}."
        result = self.gen.generate_from_template(template, {"name": "NURU", "score": "95"})
        assert result == "Bonjour NURU, votre score est 95."

    def test_template_with_missing_keys(self):
        template = "Bonjour {{name}}, projet {{missing}}."
        result = self.gen.generate_from_template(template, {"name": "NURU"})
        assert "NURU" in result
        assert "{{missing}}" in result  # pas remplacé
