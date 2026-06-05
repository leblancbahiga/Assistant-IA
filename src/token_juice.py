"""NURU V6 — TokenJuice : Middleware de Compression de Contexte.

Inspiré d'OpenHuman (TokenJuice — économise jusqu'à 80% des tokens).
Positionné à 2 points d'injection :
  1. Avant le SemanticRouter (requête utilisateur)
  2. Après le RAG, avant l'envoi au LLM (chunks + contexte)

Économise ~0.5 Go de RAM sur M1 8 Go en réduisant le nombre de tokens
à traiter par Phi-4-mini-4bit.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Helpers ──


def _dedup_consecutive(text: str) -> str:
    """Supprime les lignes consécutives identiques (logs redondants)."""
    lines = text.splitlines()
    result = []
    prev = None
    for line in lines:
        if line != prev:
            result.append(line)
            prev = line
    return "\n".join(result)


def _crush_logs(text: str) -> str:
    """Supprime les lignes de log DEBUG/INFO/WARNING."""
    return re.sub(r'(?:DEBUG|INFO|WARNING|TRACE)[^\n]*\n', '', text)


def _crush_timestamps(text: str) -> str:
    """Remplace les timestamps ISO par un marqueur court [TS]."""
    # Timestamp complet (date + heure)
    text = re.sub(
        r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?',
        '[TS]',
        text,
    )
    # Date seule (format ISO)
    text = re.sub(
        r'\b\d{4}-\d{2}-\d{2}\b',
        '[DATE]',
        text,
    )
    return text


def _shrink_urls(text: str) -> str:
    """Tronque les URLs longues (>50 chars)."""
    return re.sub(
        r'https?://[^\s){}\[\]]{50,}',
        lambda m: m.group(0)[:55] + '...',
        text,
    )


def _shrink_paths(text: str) -> str:
    """Tronque les chemins longs avec plusieurs niveaux."""
    return re.sub(
        r'(?:/[^/\s]{20,}){2,}',
        lambda m: m.group(0)[-40:] if len(m.group(0)) > 40 else m.group(0),
        text,
    )


def _strip_html(text: str) -> str:
    """Conversion HTML basique vers Markdown (sans dépendance lourde)."""
    if '<' not in text and '>' not in text:
        return text
    # Enlever les balises <style> et <script> et leur contenu
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    # Remplacer <br>, <p>, </div> par des sauts de ligne
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>', '\n', text)
    text = re.sub(r'</div>', '\n', text)
    text = re.sub(r'</li>', '\n', text)
    text = re.sub(r'<li>', '- ', text)
    text = re.sub(r'<h[1-6][^>]*>', '## ', text)
    text = re.sub(r'</h[1-6]>', '\n', text)
    # Enlever toutes les autres balises
    text = re.sub(r'<[^>]+>', '', text)
    # Dé-duplication des sauts de ligne
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _token_truncate(text: str, max_chars: int = 2000) -> str:
    """Troncature par caractères (approximation ~4 chars par token)."""
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[... tronqué ...]"


# ── Pipeline principal ──


class TokenJuice:
    """Pipeline de compression de contexte.

    Applique une série de règles de réduction (HTML→MD, troncature URLs,
    dédup, crush logs/timestamps) avant que les données n'atteignent le LLM.
    """

    def __init__(self, enabled: bool = True, max_chunk_chars: int = 2000):
        self.enabled = enabled
        self.max_chunk_chars = max_chunk_chars
        self._stats = {
            "pre_compress_chars": 0,
            "post_compress_chars": 0,
            "compressions": 0,
        }

    def compress(self, text: str, stage: str = "pre") -> str:
        """Compresse un texte brut (requête, prompt, etc.).

        Args:
            text: Texte à compresser
            stage: "pre" (avant router) ou "post" (après RAG)

        Returns:
            Texte compressé
        """
        if not self.enabled or not text:
            return text

        pre_len = len(text)

        # Pas de compression si < 20 chars (gain négligeable)
        if pre_len < 20:
            return text

        result = text

        # Étape 1 : Nettoyage HTML (indolore)
        result = _strip_html(result)

        # Étape 2 : Crush logs (post-stage uniquement)
        if stage == "post":
            result = _crush_logs(result)

        # Étape 3 : Crush timestamps
        result = _crush_timestamps(result)

        # Étape 4 : Raccourcir URLs longues
        result = _shrink_urls(result)

        # Étape 5 : Raccourcir chemins longs
        result = _shrink_paths(result)

        # Étape 6 : Déduplication des lignes consécutives
        result = _dedup_consecutive(result)

        self._stats["pre_compress_chars"] += pre_len
        self._stats["post_compress_chars"] += len(result)
        self._stats["compressions"] += 1

        saved = pre_len - len(result)
        saved_pct = (saved / pre_len * 100) if pre_len > 0 else 0
        if saved_pct > 10:
            logger.debug(
                f"🧃 TokenJuice: {pre_len} → {len(result)} chars "
                f"(-{saved_pct:.0f}%) [{stage}]"
            )

        return result

    def compress_chunks(self, chunks: list[str]) -> str:
        """Compresse une liste de chunks RAG avant envoi au LLM.

        Applique une troncature individuelle puis fusionne et compresse.

        Args:
            chunks: Liste de textes de chunks

        Returns:
            Contexte RAG compressé, prêt pour l'injection dans le prompt
        """
        if not self.enabled or not chunks:
            return "\n---\n".join(chunks) if chunks else ""

        # Troncature individuelle
        trimmed = [
            _token_truncate(c, self.max_chunk_chars) for c in chunks
        ]

        # Fusion
        merged = "\n---\n".join(trimmed)

        return self.compress(merged, stage="post")

    def compress_query(self, query: str) -> str:
        """Compresse la requête utilisateur avant routage.

        Plus léger que compress() — préserve le sens original.
        """
        if not self.enabled or not query or len(query) < 50:
            return query

        result = query.strip()
        result = _crush_timestamps(result)
        result = _shrink_urls(result)
        # Pas de dédup sur une requête (perte de sens)
        return result

    @property
    def stats(self) -> dict:
        """Retourne les statistiques de compression."""
        if self._stats["pre_compress_chars"] > 0:
            ratio = (
                1
                - self._stats["post_compress_chars"]
                / self._stats["pre_compress_chars"]
            )
        else:
            ratio = 0
        return {
            **self._stats,
            "compression_ratio": round(ratio, 3),
        }

    def reset_stats(self):
        self._stats = {
            "pre_compress_chars": 0,
            "post_compress_chars": 0,
            "compressions": 0,
        }
