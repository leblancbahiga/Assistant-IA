from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class DocFormat(str, Enum):
    WORD = "word"
    PDF = "pdf"
    PPT = "pptx"
    EXCEL = "xlsx"
    MARKDOWN = "markdown"

@dataclass
class DocSection:
    title: str
    content: str
    level: int = 1  # 1=h1, 2=h2, etc.

@dataclass
class DocumentSpec:
    title: str
    format: DocFormat
    sections: list[DocSection]
    metadata: dict[str, str] = field(default_factory=dict)  # auteur, date, etc.

class DocumentGenerator:
    """Génère des documents structurés en plusieurs formats."""

    SUPPORTED_FORMATS = {DocFormat.WORD, DocFormat.PDF, DocFormat.PPT, DocFormat.EXCEL, DocFormat.MARKDOWN}

    def validate_spec(self, spec: DocumentSpec) -> list[str]:
        """Valide un DocumentSpec. Retourne la liste des erreurs (vide = OK)."""
        errors = []
        if not spec.title:
            errors.append("Titre requis")
        if not spec.sections:
            errors.append("Au moins une section requise")
        for i, s in enumerate(spec.sections):
            if not s.title:
                errors.append(f"Section {i+1}: titre requis")
            if not s.content:
                errors.append(f"Section {i+1}: contenu requis")
        if spec.format not in self.SUPPORTED_FORMATS:
            errors.append(f"Format non supporté: {spec.format}")
        return errors

    def generate_markdown(self, spec: DocumentSpec) -> str:
        """Génère le contenu Markdown à partir d'un DocumentSpec."""
        lines = [f"# {spec.title}", ""]
        if spec.metadata:
            for k, v in spec.metadata.items():
                lines.append(f"**{k}** : {v}")
            lines.append("")
        for section in spec.sections:
            prefix = "#" * min(section.level + 1, 6)
            lines.extend([f"{prefix} {section.title}", "", section.content, ""])
        return "\n".join(lines)

    def generate_json(self, spec: DocumentSpec) -> dict:
        """Génère une représentation JSON du document."""
        return {
            "title": spec.title,
            "format": spec.format.value,
            "metadata": spec.metadata,
            "sections": [{"title": s.title, "content": s.content, "level": s.level} for s in spec.sections],
        }

    def generate_from_template(self, template: str, data: dict[str, str]) -> str:
        """Remplace les placeholders {{key}} dans un template."""
        result = template
        for key, value in data.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result
