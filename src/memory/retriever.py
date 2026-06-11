"""
NURU V9 — MemoryRetriever : point d'entrée unifié pour la recherche multi-mémoire.

Interroge EpisodicMemory + SemanticMemory + UserMemory + ErrorMemory
et fusionne les résultats par pertinence.

Usage:
    from src.memory.retriever import MemoryRetriever
    from src.memory.schema import MemorySchema

    schema = MemorySchema()
    retriever = MemoryRetriever(schema)

    # Recherche tous types
    results = retriever.recall("Leblanc YARID")

    # Résultats fusionnés
    combined = retriever.recall_combined("analyse Walikale")

    # Contexte formaté pour LLM
    context = retriever.get_context_for_query("Qui est Leblanc ?")
"""

import logging
from typing import Any, Optional

from src.memory.schema import MemorySchema
from src.memory.episodic import EpisodicMemory
from src.memory.semantic import SemanticMemory
from src.memory.user import UserMemory
from src.memory.errors import ErrorMemory

logger = logging.getLogger(__name__)

# Tous les types de mémoire supportés
ALL_MEMORY_TYPES = ["episodic", "semantic", "user", "error"]

# Libellés pour le formatage du contexte (get_context_for_query)
CONTEXT_LABELS = {
    "episodic": "MÉMOIRE ÉPISODIQUE",
    "semantic": "FAITS CONSOLIDÉS",
    "error": "ERREURS RÉCENTES",
}


class MemoryRetriever:
    """
    Point d'entrée unique pour la recherche multi-mémoire.
    Interroge EpisodicMemory + SemanticMemory + UserMemory + ErrorMemory
    et fusionne les résultats par pertinence.
    """

    def __init__(
        self,
        schema: MemorySchema,
        episodic: Optional[EpisodicMemory] = None,
        semantic: Optional[SemanticMemory] = None,
        user: Optional[UserMemory] = None,
        error: Optional[ErrorMemory] = None,
    ):
        """
        Args:
            schema: Instance de MemorySchema (obligatoire)
            episodic: Instance existante d'EpisodicMemory (créée par défaut)
            semantic: Instance existante de SemanticMemory (créée par défaut)
            user: Instance existante de UserMemory (créée par défaut)
            error: Instance existante d'ErrorMemory (créée par défaut)
        """
        self.schema = schema
        self._episodic = episodic or EpisodicMemory(schema)
        self._semantic = semantic or SemanticMemory(schema)
        self._user = user or UserMemory(schema)
        self._error = error or ErrorMemory(schema)

    # ── Propriétés d'accès aux sous-modules ───────────────────────────

    @property
    def episodic(self) -> EpisodicMemory:
        return self._episodic

    @property
    def semantic(self) -> SemanticMemory:
        return self._semantic

    @property
    def user(self) -> UserMemory:
        return self._user

    @property
    def error(self) -> ErrorMemory:
        return self._error

    # ── Recherche multi-mémoire ───────────────────────────────────────

    def recall(
        self,
        query: str,
        memory_types: Optional[list[str]] = None,
        top_k_per_type: int = 5,
        time_range: Optional[tuple[float, float]] = None,
    ) -> dict[str, list]:
        """Recherche multi-mémoire : interroge une ou plusieurs mémoires
        et retourne les résultats groupés par type.

        Args:
            query: Texte de recherche
            memory_types: Types de mémoire à interroger.
                         None = tous ('episodic', 'semantic', 'user', 'error')
            top_k_per_type: Nombre max de résultats par type de mémoire
            time_range: Filtre temporel (start, end) en timestamp UNIX.
                        Applicable uniquement à episodic et error.

        Returns:
            dict: {"episodic": [...], "semantic": [...],
                   "user": [...], "error": [...]}
                  Les types non interrogés sont absents du dict.
        """
        if memory_types is None:
            memory_types = ALL_MEMORY_TYPES

        results: dict[str, list] = {}

        for mtype in memory_types:
            mtype = mtype.lower()
            if mtype == "episodic":
                try:
                    items = self._episodic.recall(query, top_k=top_k_per_type)
                    if time_range:
                        items = self._filter_by_time(items, time_range)
                    results["episodic"] = items
                except Exception as e:
                    logger.error("Erreur recall episodic: %s", e)
                    results["episodic"] = []

            elif mtype == "semantic":
                try:
                    results["semantic"] = self._semantic.recall(query, top_k=top_k_per_type)
                except Exception as e:
                    logger.error("Erreur recall semantic: %s", e)
                    results["semantic"] = []

            elif mtype == "user":
                try:
                    # UserMemory n'a pas de recall sémantique natif, on utilise search()
                    items = self._user.search(query)
                    # Tronquer au top_k demandé
                    items = items[:top_k_per_type]
                    results["user"] = items
                except Exception as e:
                    logger.error("Erreur recall user: %s", e)
                    results["user"] = []

            elif mtype == "error":
                try:
                    items = self._error.recall(query, top_k=top_k_per_type)
                    if time_range:
                        items = self._filter_by_time(items, time_range)
                    results["error"] = items
                except Exception as e:
                    logger.error("Erreur recall error: %s", e)
                    results["error"] = []

        return results

    def recall_combined(self, query: str, top_k: int = 5) -> list[dict]:
        """Recherche fusionnée : interroge toutes les mémoires,
        fusionne les résultats par score décroissant,
        et ajoute le champ 'memory_type' à chaque résultat.

        Args:
            query: Texte de recherche
            top_k: Nombre max total de résultats fusionnés

        Returns:
            Liste de dicts triés par 'score' décroissant, chaque entrée
            ayant un champ 'memory_type' supplémentaire.
        """
        by_type = self.recall(query, top_k_per_type=top_k)

        combined: list[dict] = []

        for mtype, items in by_type.items():
            for item in items:
                entry = dict(item)
                entry["memory_type"] = mtype
                # S'assurer qu'un champ 'score' existe pour le tri
                if "score" not in entry:
                    # Pour user_memory, pas de score natif : on lui donne
                    # un score par défaut basé sur le confidence
                    entry["score"] = entry.get("confidence", 0.5)
                combined.append(entry)

        # Tri par score décroissant
        combined.sort(key=lambda x: x.get("score", 0.0), reverse=True)

        return combined[:top_k]

    def get_context_for_query(self, query: str) -> str:
        """Génère un texte formaté pour injection dans le prompt LLM.

        Combine les résultats de toutes les mémoires en un bloc texte
        structuré avec des sections claires.

        Args:
            query: Texte de recherche

        Returns:
            str: Bloc texte formaté, ou chaîne vide si aucun résultat.
        """
        by_type = self.recall(query, top_k_per_type=5)
        sections: list[str] = []

        # ── User memory en premier (contexte persistant) ──
        # Les informations utilisateur sont toujours pertinentes pour le LLM
        user_items = self._user.get_all()
        if user_items:
            lines = ["[PROFIL UTILISATEUR]"]
            seen = set()
            for item in user_items:
                key = item.get("key", "")
                value = item.get("value", "")
                confidence = item.get("confidence", 0.0)
                if key and key not in seen:
                    seen.add(key)
                    lines.append(f"- {key}: {value} (confiance: {confidence})")
            sections.append("\n".join(lines))

        # ── Mémoire épisodique ──
        episodic_items = by_type.get("episodic", [])
        if episodic_items:
            lines = ["[MÉMOIRE ÉPISODIQUE]"]
            for item in episodic_items:
                timestamp = item.get("timestamp", 0)
                summary = item.get("summary", "")
                importance = item.get("importance", 0.0)
                score = item.get("score", 0.0)
                lines.append(
                    f"- {self._format_time(timestamp)}: {summary} "
                    f"(importance: {importance}, score: {score})"
                )
            sections.append("\n".join(lines))

        # ── Faits consolidés (sémantique) ──
        semantic_items = by_type.get("semantic", [])
        if semantic_items:
            lines = ["[FAITS CONSOLIDÉS]"]
            for item in semantic_items:
                fact = item.get("fact", "")
                confidence = item.get("confidence", 0.0)
                score = item.get("score", 0.0)
                lines.append(f"- {fact} (confiance: {confidence}, score: {score})")
            sections.append("\n".join(lines))

        # ── Erreurs récentes ──
        error_items = by_type.get("error", [])
        if error_items:
            lines = ["[ERREURS RÉCENTES]"]
            for item in error_items:
                description = item.get("description", "")
                error_type = item.get("error_type", "")
                correction = item.get("correction", "")
                lines.append(
                    f"- [{error_type}] {description}"
                    + (f" → correction: {correction}" if correction else "")
                )
            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    def count_all(self) -> dict[str, int]:
        """Compte le nombre total d'entrées dans chaque mémoire.

        Returns:
            dict: {"episodic": N, "semantic": N, "user": N, "error": N}
        """
        return {
            "episodic": self._episodic.count(),
            "semantic": self._semantic.count(),
            "user": self._user.count(),
            "error": self._error.count(),
        }

    # ── Méthodes auxiliaires ──────────────────────────────────────────

    @staticmethod
    def _filter_by_time(
        items: list[dict],
        time_range: tuple[float, float],
    ) -> list[dict]:
        """Filtre une liste de résultats par intervalle de temps.

        Args:
            items: Liste de dicts avec champ 'timestamp'
            time_range: (start, end) en timestamp UNIX

        Returns:
            Liste filtrée
        """
        start, end = time_range
        return [it for it in items if start <= it.get("timestamp", 0) <= end]

    @staticmethod
    def _format_time(timestamp: float) -> str:
        """Formate un timestamp UNIX en date lisible.

        Args:
            timestamp: Timestamp UNIX

        Returns:
            str: Date formatée (YYYY-MM-DD) ou 'date inconnue'
        """
        try:
            import datetime
            dt = datetime.datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            return "date inconnue"
