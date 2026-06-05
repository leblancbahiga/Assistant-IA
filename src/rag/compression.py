"""Compression contextuelle pour NURU V4.5.

Réduit le nombre de tokens d'un contexte RAG en ne gardant
que les phrases contenant des mots-clés de la requête.
Pas de LLM — regex pure, 0 tok/s perdu.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ContextCompressor:
    """Compresse un contexte RAG en extrayant les phrases pertinentes.

    Stratégie :
    1. Tokenise la requête en mots significatifs (> 3 caractères, stop words exclus)
    2. Pour chaque chunk, ne garde que les phrases contenant au moins un mot-clé
    3. Tronque au budget tokens max si nécessaire

    Usage:
        compressor = ContextCompressor()
        compressed = compressor.compress(chunks, query, max_tokens=1024)
    """

    STOP_WORDS = {
        "de", "la", "le", "les", "un", "une", "en", "que", "qui", "dans",
        "par", "pour", "sur", "avec", "du", "des", "se", "sa", "son", "ce",
        "et", "ou", "mais", "donc", "car", "ni", "ne", "pas", "plus", "aux",
        "au", "the", "a", "an", "and", "or", "but", "for", "with", "in",
        "on", "at", "of", "to", "is", "are", "this", "that",
    }

    def __init__(self, max_tokens: int = 1024,
                 min_sentence_chars: int = 20,
                 keep_all_if_small: bool = True):
        self.max_tokens = max_tokens
        self.min_sentence_chars = min_sentence_chars
        self.keep_all_if_small = keep_all_if_small

    def compress(self, chunks: list, query: str) -> str:
        """Compresse une liste de chunks en contexte pertinent.

        Args:
            chunks: liste de tuples (content, source, score) ou d'objets SemanticChunk
            query: requête utilisateur originale

        Returns:
            Contexte compressé (str)
        """
        if not chunks:
            return ""

        # Extraire les textes des chunks
        texts = []
        for c in chunks:
            if hasattr(c, 'text'):
                texts.append(c.text)
            elif isinstance(c, tuple) and len(c) >= 1:
                texts.append(str(c[0]))
            else:
                texts.append(str(c))

        full = "\n\n".join(texts)

        # Estimer les tokens (approx 4 chars/token)
        estimated_tokens = len(full) // 4

        if self.keep_all_if_small and estimated_tokens <= self.max_tokens:
            return full

        # Tokens significatifs de la requête
        query_tokens = self._extract_tokens(query)

        if not query_tokens:
            # Fallback : troncature simple
            return full[:self.max_tokens * 4] + "\n[...tronqué]"

        # Filtrer les phrases
        kept = []
        for text in texts:
            sentences = self._split_sentences(text)
            for s in sentences:
                if len(s) < self.min_sentence_chars:
                    continue
                s_lower = s.lower()
                matches = sum(1 for t in query_tokens if t in s_lower)
                if matches > 0:
                    kept.append(s)

        compressed = "\n".join(kept)
        if len(compressed) // 4 > self.max_tokens:
            compressed = compressed[:self.max_tokens * 4] + "\n[...tronqué]"

        return compressed if compressed else full[:self.max_tokens * 4]

    def _extract_tokens(self, query: str) -> list[str]:
        """Extrait les tokens significatifs d'une requête."""
        tokens = re.findall(r'\b\w{3,}\b', query.lower())
        return [t for t in tokens if t not in self.STOP_WORDS]

    def _split_sentences(self, text: str) -> list[str]:
        """Détection simple de phrases."""
        raw = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in raw if s.strip()]
