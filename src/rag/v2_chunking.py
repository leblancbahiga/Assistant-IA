"""
NURU V6 — Chunking hiérarchique robuste V2.

Problèmes du chunking V1 :
1. Chunks trop petits (max 1200 chars) → contexte haché
2. Pas d'agrégation → 50 petits bouts pour un CV de 10 pages
3. Pas de résumé de document → LLM n'a pas de vue d'ensemble
4. Métadonnées pauvres → pas de scoring par importance

Philosophie V2 — Hiérarchie riche :
1. Résumé du document entier (head)
2. Sections principales (body → sections)
3. Détails par section (body → subsections/paragraphs)
4. Marqueurs d'importance ([IMPORTANT], [DETAIL], [META])
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Seuils de taille
MAX_SECTION_CHARS = 4000     # Taille max d'une section
MAX_SUBSECTION_CHARS = 2000  # Taille max d'une sous-section
MIN_CHUNK_CHARS = 200        # En dessous : fusionner avec le voisin
OVERLAP_CHARS = 100          # Chevauchement entre chunks

# Marqueurs d'importance détectés dans le texte
IMPORTANCE_PATTERNS = {
    "high": re.compile(
        r'(expérience professionnelle|formation|diplôme|compétence|'
        r'résumé|profil|career|education|skill|achievement|'
        r'réalisation|mission|responsabilité|poste occupé)',
        re.IGNORECASE
    ),
    "medium": re.compile(
        r'(projet|référence|langue|réf[ée]rence|certification|'
        r'publication|distinction|prix|bourse)',
        re.IGNORECASE
    ),
}


@dataclass
class ChunkV2:
    """Chunk hiérarchique V2 avec métadonnées riches."""
    content: str                    # Texte du chunk
    source: str                     # Nom du fichier source
    doc_title: str = ""             # Titre du document parent
    section_title: str = ""         # Titre de la section
    level: str = "paragraph"        # document | section | subsection | paragraph
    importance: str = "normal"      # high | medium | normal | meta
    char_count: int = 0
    word_count: int = 0
    chunk_index: int = 0            # Position dans le document
    total_chunks: int = 0           # Nombre total de chunks du document

    def to_dict(self) -> dict:
        """Sérialisation pour insertion dans l'index."""
        # Contexte enrichi
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
    """Chunker hiérarchique robuste pour documents longs.

    Pipeline :
    1. Résumé du document entier (toujours indexé)
    2. Découpage en sections par titres
    3. Sections longues → sous-sections + paragraphes
    4. Marqueurs d'importance
    """

    def __init__(self, max_section_chars: int = MAX_SECTION_CHARS):
        self.max_section_chars = max_section_chars

    def chunk(self, text: str, source: str = "",
              doc_title: str = "") -> list[ChunkV2]:
        """Point d'entrée : découpe un texte en chunks hiérarchiques."""
        if not text.strip():
            return []

        doc_title = doc_title or source or "Document"
        all_chunks: list[ChunkV2] = []

        # 1. Résumé du document (les 200 premiers caractères comme résumé)
        summary = self._make_summary(text, source, doc_title)
        if summary:
            all_chunks.append(summary)

        # 2. Détection des sections
        sections = self._split_sections(text)

        for section_title, section_body in sections:
            chunk_index = len(all_chunks)
            
            # Marqueur d'importance
            importance = self._detect_importance(section_title + " " + section_body[:200])

            if len(section_body) <= self.max_section_chars:
                # Section de taille normale
                chunk = ChunkV2(
                    content=section_body.strip(),
                    source=source,
                    doc_title=doc_title,
                    section_title=section_title,
                    level="section",
                    importance=importance,
                    char_count=len(section_body),
                    word_count=len(section_body.split()),
                    chunk_index=chunk_index,
                )
                all_chunks.append(chunk)
            else:
                # Section longue → sous-sections
                subsections = self._split_subsections(section_title, section_body)
                for sub_title, sub_body in subsections:
                    chunk = ChunkV2(
                        content=sub_body.strip(),
                        source=source,
                        doc_title=doc_title,
                        section_title=sub_title or section_title,
                        level="subsection",
                        importance=importance,
                        char_count=len(sub_body),
                        word_count=len(sub_body.split()),
                        chunk_index=chunk_index,
                    )
                    all_chunks.append(chunk)
                    chunk_index += 1

        # 3. Marquer le nombre total de chunks
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
        """Crée un chunk résumé avec les infos clés du document."""
        # Résumé : début du document + métadonnées
        lines = text.strip().split("\n")[:10]  # Premières 10 lignes
        summary_text = "\n".join(lines)
        
        # Si le doc a un titre détectable
        title_match = re.match(r'^#\s+(.+)$', text, re.MULTILINE)
        if title_match:
            summary_text = f"Titre: {title_match.group(1)}\n" + summary_text

        if len(summary_text) < 50:
            return None

        return ChunkV2(
            content=summary_text[:2000],  # Limiter le résumé
            source=source,
            doc_title=doc_title,
            section_title="Résumé du document",
            level="document",
            importance="high",
            char_count=len(summary_text[:2000]),
            word_count=len(summary_text[:2000].split()),
            chunk_index=0,
        )

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        """Détecte les sections par titres markdown ou lignes majuscules."""
        lines = text.split("\n")
        sections: list[tuple[str, list[str]]] = [("", [])]

        # Patterns de titres
        heading_re = re.compile(r'^(#{1,3})\s+(.+)$')
        caps_re = re.compile(r'^([A-Z][A-Z\s\-À-ÜÉÈÊË]{3,})$')
        # Nouveau : titres de CV comme "EXPÉRIENCE PROFESSIONNELLE"
        cv_header_re = re.compile(
            r'^([A-ZÉÈÊËÀ-Ü]{4,}(?:\s+[A-ZÉÈÊËÀ-Ü]{2,})*)$'
        )

        for line in lines:
            m = heading_re.match(line) or caps_re.match(line) or cv_header_re.match(line)
            if m:
                sections.append((line.strip(), []))
            else:
                sections[-1][1].append(line)

        return [(t, "\n".join(b).strip()) for t, b in sections if b]

    def _split_subsections(self, parent_title: str, text: str) -> list[tuple[str, str]]:
        """Découpe une section longue en sous-sections."""
        # D'abord essayer les paragraphes
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if len(p.strip()) > MIN_CHUNK_CHARS]
        
        if not paragraphs:
            # Fallback : découpage par taille
            paragraphs = []
            while text:
                chunk = text[:self.max_section_chars // 2]
                text = text[self.max_section_chars // 2 - OVERLAP_CHARS:]
                paragraphs.append(chunk.strip())

        # Grouper les petits paragraphes
        merged = []
        buffer = ""
        for p in paragraphs:
            if len(buffer) + len(p) < self.max_section_chars // 2:
                buffer += "\n\n" + p if buffer else p
            else:
                if buffer:
                    merged.append((parent_title, buffer))
                buffer = p
        if buffer:
            merged.append((parent_title, buffer))

        return merged

    def _detect_importance(self, text: str) -> str:
        """Détecte le niveau d'importance d'un chunk."""
        text_lower = text.lower()
        for pattern_name, pattern in IMPORTANCE_PATTERNS.items():
            if pattern.search(text_lower):
                return pattern_name
        return "normal"
