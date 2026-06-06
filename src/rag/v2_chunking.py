"""
NURU V6 — Chunking hiérarchique robuste V2 (corrigé).

Problèmes V2 corrigés :
1. Résumé trop superficiel (10 premières lignes) → extraction structurée de TOUTES les sections
2. Détection des sections fragile → fallback phrase pour textes non structurés
3. Fusion des petits paragraphes insuffisante → accumulation jusqu'à MAX_SECTION_CHARS
4. MIN_CHUNK_CHARS trop bas (200) → 500
5. Profils par type de document (CV vs rapport vs note)
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Profils de chunking ──
PROFILES = {
    "cv": {"max_section": 6000, "min_chunk": 500, "overlap": 200},
    "rapport": {"max_section": 4000, "min_chunk": 300, "overlap": 100},
    "note": {"max_section": 2000, "min_chunk": 150, "overlap": 50},
}

# Par défaut (profil CV — le plus permissif pour les données denses)
MAX_SECTION_CHARS = 6000
MIN_CHUNK_CHARS = 500
OVERLAP_CHARS = 200

# Si le texte fait moins de cette taille, on ne chunk pas du tout
SHORT_DOC_THRESHOLD = 2000  # ~500 tokens — V6.2 : abaissé pour chunker les docs courts

IMPORTANCE_PATTERNS = {
    "high": re.compile(
        r'(expérience professionnelle|formation|diplôme|compétence|'
        r'résumé|profil|career|education|skill|achievement|'
        r'réalisation|mission|responsabilité|poste occupé|'
        r'emploi|travail|job|expérience)',
        re.IGNORECASE
    ),
    "medium": re.compile(
        r'(projet|référence|langue|réf[ée]rence|certification|'
        r'publication|distinction|prix|bourse|langue|informatique)',
        re.IGNORECASE
    ),
}

# Détection du type de document par le nom de fichier
CV_PATTERNS = re.compile(
    r'\b(cv|curriculum|vitae|resume|profil|motivation|lettre|candidature|cover)\b'
    r'|cv[_\-]',
    re.IGNORECASE,
)

RAPPORT_PATTERNS = re.compile(
    r'\b(rapport|report|étude|analysis|survey|baseline|assessment|review)\b',
    re.IGNORECASE,
)


@dataclass
class ChunkV2:
    content: str
    source: str
    doc_title: str = ""
    section_title: str = ""
    level: str = "paragraph"       # document | section | subsection | paragraph
    importance: str = "normal"
    char_count: int = 0
    word_count: int = 0
    chunk_index: int = 0
    total_chunks: int = 0

    def to_dict(self) -> dict:
        context_parts = []
        if self.level == "document":
            context_parts.append(f"[RÉSUMÉ] {self.doc_title}")
        elif self.section_title:
            context_parts.append(f"[{self.doc_title} - {self.section_title}]")
        else:
            context_parts.append(f"[{self.doc_title}]")
        if self.importance == "high":
            context_parts.append("[IMPORTANT]")
        content = " ".join(context_parts) + "\n" + self.content
        return {
            "content": content,
            "source": self.source,
            "importance": self.importance,
            "level": self.level,
            "section": self.section_title,
            "char_count": self.char_count,
        }


class HierarchicalChunkerV2:
    """Chunker hiérarchique avec profils par type de document."""

    def __init__(self, profile: str = "cv"):
        p = PROFILES.get(profile, PROFILES["cv"])
        self.max_section_chars = p["max_section"]
        self.min_chunk_chars = p["min_chunk"]
        self.overlap_chars = p["overlap"]

    @staticmethod
    def detect_profile(filename: str) -> str:
        """Détecte le profil de chunking adapté au fichier."""
        if CV_PATTERNS.search(filename):
            return "cv"
        if RAPPORT_PATTERNS.search(filename):
            return "rapport"
        return "note"

    def chunk(self, text: str, source: str = "",
              doc_title: str = "") -> list[ChunkV2]:
        if not text.strip():
            return []

        doc_title = doc_title or source or "Document"
        text = text.strip()

        # ── DOCUMENTS COURTS : pas de chunking du tout ──
        if len(text) < SHORT_DOC_THRESHOLD:
            chunk = ChunkV2(
                content=text,
                source=source,
                doc_title=doc_title,
                section_title="Document complet",
                level="document",
                importance="high",
                char_count=len(text),
                word_count=len(text.split()),
                chunk_index=0,
                total_chunks=1,
            )
            logger.info(f"📄 Chunker V2: document court ({len(text)} chars) → 1 chunk unique")
            return [chunk]

        all_chunks: list[ChunkV2] = []

        # 1. Résumé structuré de tout le document
        summary = self._make_summary(text, source, doc_title)
        if summary:
            all_chunks.append(summary)

        # 2. Détection des sections
        sections = self._split_sections(text)

        for section_title, section_body in sections:
            if not section_body.strip():
                continue

            importance = self._detect_importance(
                section_title + " " + section_body[:300]
            )

            # Accumulation des paragraphes jusqu'à MAX_SECTION_CHARS
            accumulated = self._accumulate_paragraphs(
                section_body, section_title, source, doc_title,
                importance, len(all_chunks)
            )
            all_chunks.extend(accumulated)

        total = len(all_chunks)
        for c in all_chunks:
            c.total_chunks = total

        logger.info(
            f"📄 Chunker V2: {total} chunks "
            f"(résumé + {sum(1 for c in all_chunks if c.level=='section')} sections "
            f"+ {sum(1 for c in all_chunks if c.level=='subsection')} sous-sections)"
        )
        return all_chunks

    def _make_summary(self, text: str, source: str, doc_title: str) -> Optional[ChunkV2]:
        """Résumé complet — contient le texte intégral du document pour éviter
        que le résumé (score RRF élevé) concurrence les chunks de contenu réel.
        V6.2 : inclu le texte complet des sections, pas seulement la première ligne.
        """
        sections = self._split_sections(text)
        summary_parts = [f"Document: {doc_title}"]

        for title, body in sections[:20]:  # Jusqu'à 20 sections
            if title and body:
                # Inclure tout le corps de la section (pas juste la première ligne)
                body_text = body.strip()
                if len(body_text) > 500:
                    body_text = body_text[:500] + "..."
                summary_parts.append(f"• {title}: {body_text}")

        summary_text = "\n".join(summary_parts)

        if len(summary_text) < 80:
            return None

        return ChunkV2(
            content=summary_text[:4000],  # 4K chars max pour le résumé
            source=source,
            doc_title=doc_title,
            section_title="Résumé du document",
            level="document",
            importance="high",
            char_count=len(summary_text[:4000]),
            word_count=len(summary_text[:4000].split()),
            chunk_index=0,
        )

    def _accumulate_paragraphs(self, text: str, section_title: str,
                                source: str, doc_title: str,
                                importance: str, start_index: int) -> list[ChunkV2]:
        """Accumule les paragraphes d'une section jusqu'à MAX_SECTION_CHARS."""
        paragraphs = self._split_paragraphs(text)
        if not paragraphs:
            # Fallback : la section entière en un chunk
            return [ChunkV2(
                content=text.strip(),
                source=source, doc_title=doc_title,
                section_title=section_title,
                level="section", importance=importance,
                char_count=len(text), word_count=len(text.split()),
                chunk_index=start_index,
            )]

        chunks = []
        buffer = ""
        idx = start_index

        for para in paragraphs:
            # Si le paragraphe seul dépasse la limite, le traiter comme chunk unique
            if len(para) >= self.max_section_chars:
                # Sauvegarder le buffer d'abord
                if buffer:
                    chunks.append(ChunkV2(
                        content=buffer.strip(),
                        source=source, doc_title=doc_title,
                        section_title=section_title,
                        level="subsection", importance=importance,
                        char_count=len(buffer), word_count=len(buffer.split()),
                        chunk_index=idx,
                    ))
                    idx += 1
                    buffer = ""
                # Puis le gros paragraphe
                chunks.append(ChunkV2(
                    content=para.strip(),
                    source=source, doc_title=doc_title,
                    section_title=section_title,
                    level="subsection", importance=importance,
                    char_count=len(para), word_count=len(para.split()),
                    chunk_index=idx,
                ))
                idx += 1
                continue

            # Accumulation
            candidate = (buffer + "\n\n" + para) if buffer else para
            if len(candidate) <= self.max_section_chars:
                buffer = candidate
            else:
                if buffer:
                    chunks.append(ChunkV2(
                        content=buffer.strip(),
                        source=source, doc_title=doc_title,
                        section_title=section_title,
                        level="section", importance=importance,
                        char_count=len(buffer), word_count=len(buffer.split()),
                        chunk_index=idx,
                    ))
                    idx += 1
                buffer = para

        # Dernier buffer
        if buffer:
            chunks.append(ChunkV2(
                content=buffer.strip(),
                source=source, doc_title=doc_title,
                section_title=section_title,
                level="section", importance=importance,
                char_count=len(buffer), word_count=len(buffer.split()),
                chunk_index=idx,
            ))

        return chunks

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        """Détecte les sections. Fallback phrase si aucun titre détecté."""
        lines = text.split("\n")
        sections: list[tuple[str, list[str]]] = [("", [])]

        heading_re = re.compile(r'^(#{1,3})\s+(.+)$')
        caps_re = re.compile(r'^([A-Z][A-Z\s\-À-ÜÉÈÊË]{4,})$')
        cv_header_re = re.compile(r'^([A-ZÉÈÊËÀ-Ü]{4,}(?:\s+[A-ZÉÈÊËÀ-Ü]{2,})*)$')

        for line in lines:
            m = heading_re.match(line) or caps_re.match(line) or cv_header_re.match(line)
            if m:
                sections.append((line.strip(), []))
            else:
                sections[-1][1].append(line)

        result = [(t, "\n".join(b).strip()) for t, b in sections if b]

        # Fallback : si aucune section détectée, section unique
        if not result:
            result = [("", text.strip())]

        return result

    def _split_paragraphs(self, text: str) -> list[str]:
        """Paragraphes par doubles sauts de ligne, filtre les micro-chunks."""
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text)]
        return [p for p in paragraphs if len(p) >= self.min_chunk_chars]

    def _detect_importance(self, text: str) -> str:
        text_lower = text.lower()
        for pattern_name, pattern in IMPORTANCE_PATTERNS.items():
            if pattern.search(text_lower):
                return pattern_name
        return "normal"
