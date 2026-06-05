"""Chunking sémantique contextuel pour NURU V4.5.

Remplace le chunking fixe à 400 caractères de la V4.

Philosophie V4.5 — Context-Aware Chunking :
Chaque chunk contient son identité : [Document - Section]
Ainsi, même isolé, le chunk garde 100% de son sens pour le LLM.

3 niveaux : section → paragraph → evidence
Zéro dépendance externe (pas spaCy, pas NLTK — RAM préservée).
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SemanticChunk:
    """Unité de connaissance atomique avec contexte injecté."""
    doc_id: str = ""
    chunk_id: str = ""
    level: str = "paragraph"          # section | paragraph | evidence
    title: str = ""                   # Titre de la section parente
    text: str = ""                    # Texte brut (sans contexte)
    contextualized: str = ""          # Texte avec contexte injecté [Doc - Section]
    tokens: int = 0
    source: str = ""                  # Nom du fichier source
    metadata: dict = field(default_factory=dict)


class SemanticChunker:
    """Découpeur sémantique avec injection de contexte.

    Usage:
        chunker = SemanticChunker(max_chars=1200)
        chunks = chunker.chunk(text, source="Manuel_Agro.md",
                                metadata={"title": "Manuel Agroforesterie"})

    Chaque chunk reçoit un préfixe contextuel :
        [Manuel Agroforesterie - Gestion des Sols]
        Le biochar est un amendement organique...
    """

    def __init__(self, max_chars: int = 1200, overlap_chars: int = 150):
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk(self, text: str, source: str = "",
              doc_id: str = "", metadata: dict = None) -> list[SemanticChunk]:
        """Point d'entrée : découpe un texte en chunks contextuels."""
        if not text.strip():
            return []

        metadata = metadata or {}
        doc_title = metadata.get("title") or source or "Document"
        chunks: list[SemanticChunk] = []

        # 1. Découpage en sections par titres
        sections = self._split_sections(text)
        current_header = "Introduction"

        for section_title, section_body in sections:
            if section_title:
                current_header = section_title

            # Chunk de niveau section
            if len(section_body) <= self.max_chars and section_body.strip():
                chunk = self._make_chunk(
                    text=section_body.strip(),
                    level="section",
                    title=current_header,
                    doc_title=doc_title,
                    source=source, doc_id=doc_id,
                    metadata=metadata,
                )
                chunks.append(chunk)

            # Paragraphes (pour sections longues ou multi-paragraphes)
            paragraphs = self._split_paragraphs(section_body)
            for para in paragraphs:
                if len(para.strip()) < 20:
                    continue
                # Évite la duplication avec le chunk section
                if chunks and chunks[-1].text.strip() == para.strip():
                    continue

                chunk = self._make_chunk(
                    text=para.strip(),
                    level="paragraph",
                    title=current_header,
                    doc_title=doc_title,
                    source=source, doc_id=doc_id,
                    metadata=metadata,
                )
                chunks.append(chunk)

        # Fallback si rien n'a été détecté
        if not chunks:
            chunks.append(self._make_chunk(
                text=text.strip(), level="section",
                title="", doc_title=doc_title,
                source=source, doc_id=doc_id,
                metadata=metadata,
            ))

        logger.info(
            f"📄 {len(chunks)} chunks (sections="
            f"{sum(1 for c in chunks if c.level=='section')}, "
            f"paragraphs={sum(1 for c in chunks if c.level=='paragraph')})"
        )
        return chunks

    def _make_chunk(self, text: str, level: str, title: str,
                    doc_title: str, source: str, doc_id: str,
                    metadata: dict) -> SemanticChunk:
        """Crée un chunk avec contexte injecté."""
        # Injection de contexte : [Document - Section]
        context_prefix = f"[{doc_title}"
        if title:
            context_prefix += f" - {title}"
        context_prefix += "]\n"

        return SemanticChunk(
            doc_id=doc_id,
            chunk_id=f"c{hash(text[:50]) & 0xFFFF}",
            level=level,
            title=title,
            text=text,
            contextualized=context_prefix + text,
            tokens=len(text.split()),
            source=source,
            metadata={**metadata, "section": title, "level": level},
        )

    # ─── Méthodes internes ───

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        """Détecte les sections par titres markdown ou lignes majuscules."""
        lines = text.split("\n")
        sections: list[tuple[str, list[str]]] = [("", [])]

        heading_re = re.compile(r'^(#{1,3})\s+(.+)$')
        caps_re = re.compile(r'^([A-Z][A-Z\s\-À-ÜÉÈÊË]{3,})$')

        for line in lines:
            m = heading_re.match(line) or caps_re.match(line)
            if m:
                sections.append((line.strip(), []))
            else:
                sections[-1][1].append(line)

        return [(t, "\n".join(b).strip()) for t, b in sections if b]

    def _split_paragraphs(self, text: str) -> list[str]:
        """Paragraphes par doubles sauts de ligne."""
        return [p.strip() for p in re.split(r'\n\s*\n', text) if len(p.strip()) > 20]
