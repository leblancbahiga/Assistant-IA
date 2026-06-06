"""
Long-Term Memory (LTM) — Extraction et gestion des faits utilisateur.

Utilise le CloudLLM (Groq) pour extraire des faits structurés
des conversations, les stocke dans `user_facts` (SQLite), et
fournit une recherche sémantique pour injection dans le contexte.
"""

import asyncio
import json
import logging
from typing import Optional

from src.config import config
from src.memory_store import MemoryStore
from src.llm_cloud import CloudLLM

logger = logging.getLogger(__name__)

# Prompt système pour l'extraction de faits utilisateur
EXTRACT_SYSTEM_PROMPT = """Tu es un extracteur de faits utilisateur pour NURU, l'assistant IA personnel.
À partir de l'historique de conversation ci-dessous, extrais les informations personnelles
sur l'utilisateur sous forme de faits structurés.

Types de faits possibles :
- personal_info : prénom, nom, âge, localisation, contact
- preference : goûts, préférences, aversions
- project : projets en cours ou terminés
- task : tâches, objectifs, deadlines
- skill : compétences, expertise
- relationship : relations personnelles ou professionnelles
- context : contexte de vie ou de travail
- other : autre information pertinente

Règles :
- N'inclus QUE les faits explicitement mentionnés dans la conversation
- Ne devine pas et n'invente pas
- Format de réponse : un JSON array d'objets avec "fact_type", "content", "confidence"
- confidence : 0.0-1.0 (1.0 = explicitement dit, 0.5 = fortement suggéré)
- Si aucun nouveau fait n'est trouvé, réponds : {"facts": []}

Exemple de réponse :
{"facts": [{"fact_type": "personal_info", "content": "L'utilisateur s'appelle Leblanc", "confidence": 1.0}, {"fact_type": "preference", "content": "L'utilisateur préfère les réponses en français", "confidence": 0.9}]}

Réponds UNIQUEMENT avec le JSON, rien d'autre."""


class LongTermMemory:
    """Gestionnaire de mémoire long terme structurée.

    Extrait, stocke, recherche et consolide les faits utilisateur
    à partir des conversations.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        cloud_llm: Optional[CloudLLM] = None,
        embedder=None,
    ):
        self.memory_store = memory_store
        self.cloud_llm = cloud_llm or CloudLLM()
        self.embedder = embedder  # Optionnel : pour recherche sémantique améliorée

    # ──────────────────────────────────────
    # Extraction de faits depuis une conversation
    # ──────────────────────────────────────

    async def extract_facts(self, conversation_history: list[dict]) -> list[dict]:
        """Extrait les faits utilisateur d'un historique de conversation via LLM.

        Args:
            conversation_history: Liste de messages [{"role": ..., "content": ...}]

        Returns:
            Liste de dicts {"fact_type": ..., "content": ..., "confidence": ...}
        """
        if not conversation_history:
            return []

        # Formater l'historique pour le prompt
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in conversation_history[-10:]  # Derniers 10 échanges max
        )

        prompt = (
            f"## HISTORIQUE DE CONVERSATION\n\n"
            f"{history_text}\n\n"
            f"## INSTRUCTION\n"
            f"Extrais les faits utilisateur de cette conversation "
            f"et retourne-les au format JSON."
        )

        try:
            response_chunks = []
            async for chunk in self.cloud_llm.generate_stream(
                prompt,
                intent="SIMPLE",
                system_prompt=EXTRACT_SYSTEM_PROMPT,
            ):
                response_chunks.append(chunk)

            raw_response = "".join(response_chunks).strip()
            facts = self._parse_facts_response(raw_response)
            logger.info(
                f"📋 Extraction LTM : {len(facts)} faits extraits "
                f"de {len(conversation_history)} messages"
            )
            return facts

        except Exception as e:
            logger.warning(f"⚠️ Échec extraction LTM : {e}")
            return []

    def _parse_facts_response(self, raw: str) -> list[dict]:
        """Parse la réponse JSON du LLM en liste de faits."""
        # Nettoyer : enlever les marqueurs de code ```json ... ```
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        try:
            data = json.loads(raw)
            facts = data.get("facts", data) if isinstance(data, dict) else data
            if isinstance(facts, list):
                return [
                    f for f in facts
                    if isinstance(f, dict)
                    and f.get("fact_type")
                    and f.get("content")
                ]
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"Parse LTM : JSON invalide — {e}")

        # Fallback : tenter de trouver un JSON array dans le texte
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                if isinstance(data, list):
                    return data
        except (json.JSONDecodeError, IndexError):
            pass

        return []

    # ──────────────────────────────────────
    # Stockage de faits
    # ──────────────────────────────────────

    def store_fact(
        self,
        fact_type: str,
        content: str,
        source: str = "conversation",
        confidence: float = 0.8,
    ) -> int:
        """Stocke un fait utilisateur dans la base.

        Args:
            fact_type: Catégorie du fait (personal_info, preference, project, …)
            content: Contenu textuel du fait
            source: Origine (conversation, document, manual)
            confidence: Niveau de confiance (0.0-1.0)

        Returns:
            ID du fait inséré ou mis à jour
        """
        return self.memory_store.store_user_fact(
            fact_type=fact_type,
            content=content,
            source=source,
            confidence=confidence,
        )

    # ──────────────────────────────────────
    # Recherche de faits pertinents
    # ──────────────────────────────────────

    async def get_relevant_facts(
        self, query: str, limit: int = 10
    ) -> list[dict]:
        """Recherche les faits utilisateur pertinents pour une requête.

        Stratégie à deux niveaux :
        1. Mots-clés extraits de la requête → LIKE search (toujours disponible)
        2. Embeddings sémantiques si embedder disponible

        Args:
            query: Requête utilisateur
            limit: Nombre maximum de faits à retourner

        Returns:
            Liste de dicts faits triés par pertinence décroissante
        """
        # Niveau 1 : recherche par mots-clés
        keywords = self._extract_keywords(query)
        if keywords:
            keyword_results = self.memory_store.search_user_facts(
                keywords=keywords, limit=limit
            )
            if keyword_results:
                logger.debug(
                    f"🔍 LTM keyword search: {len(keyword_results)} résultats "
                    f"pour {keywords}"
                )
                return keyword_results

        # Niveau 2 : fallback — tous les faits récents
        all_facts = self.memory_store.get_user_facts(limit=limit)
        # Filtrer ceux qui contiennent au moins un mot de la requête
        query_lower = query.lower()
        filtered = [
            f for f in all_facts
            if any(w in f["content"].lower() for w in query_lower.split())
        ]
        return filtered or all_facts[:5]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extrait les mots-clés significatifs d'une requête."""
        # Mots vides français
        stop_words = {
            "le", "la", "les", "un", "une", "des", "du", "de", "ce", "cet",
            "cette", "ces", "mon", "ton", "son", "ma", "ta", "sa", "mes",
            "tes", "ses", "nos", "vos", "leurs", "notre", "votre",
            "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
            "ai", "as", "a", "avons", "avez", "ont", "suis", "es", "est",
            "sommes", "êtes", "sont", "dans", "sur", "avec", "sans", "pour",
            "par", "vers", "chez", "entre", "sous", "depuis", "jusqu",
            "et", "ou", "mais", "donc", "ni", "car", "que", "qui", "quoi",
            "dont", "où", "comment", "pourquoi", "quand",
            "ne", "pas", "plus", "moins", "très", "aussi", "si",
            "est-ce", "c'est", "qu'est-ce", "au", "aux", "en", "y",
            "lui", "leur", "eux", "elle", "celui", "celle", "ceux",
        }
        words = text.lower().split()
        return [w for w in words if len(w) > 2 and w not in stop_words][:10]

    # ──────────────────────────────────────
    # Consolidation des faits
    # ──────────────────────────────────────

    def consolidate(self) -> int:
        """Fusionne les faits similaires et supprime les doublons.

        Stratégie :
        1. Groupe les faits par type
        2. Dans chaque groupe, fusionne ceux qui partagent ≥60% de mots
        3. Conserve celui avec la plus haute confiance

        Returns:
            Nombre de doublons fusionnés/supprimés
        """
        all_facts = self.memory_store.get_user_facts(limit=1000)
        if len(all_facts) < 2:
            return 0

        # Grouper par type
        by_type: dict[str, list[dict]] = {}
        for f in all_facts:
            by_type.setdefault(f["fact_type"], []).append(f)

        merged_count = 0

        for fact_type, facts in by_type.items():
            if len(facts) < 2:
                continue

            # Comparaison pairwise
            processed_ids = set()
            for i, f1 in enumerate(facts):
                if f1["id"] in processed_ids:
                    continue
                words1 = set(f1["content"].lower().split())
                if not words1:
                    continue

                for f2 in facts[i + 1:]:
                    if f2["id"] in processed_ids:
                        continue
                    words2 = set(f2["content"].lower().split())
                    if not words2:
                        continue

                    # Jaccard similarity
                    intersection = len(words1 & words2)
                    union = len(words1 | words2)
                    if union == 0:
                        continue
                    similarity = intersection / union

                    if similarity >= 0.60:
                        # Garder celui avec la plus haute confiance
                        if f1["confidence"] >= f2["confidence"]:
                            self.memory_store.deactivate_user_fact(f2["id"])
                            processed_ids.add(f2["id"])
                            # Mettre à jour updated_at et booster confidence
                            self.memory_store.store_user_fact(
                                fact_type=fact_type,
                                content=f1["content"],
                                source=f1["source"],
                                confidence=min(f1["confidence"] + 0.05, 1.0),
                            )
                        else:
                            self.memory_store.deactivate_user_fact(f1["id"])
                            processed_ids.add(f1["id"])
                        merged_count += 1

        if merged_count > 0:
            logger.info(f"🧹 Consolidation LTM : {merged_count} faits fusionnés")
        return merged_count

    # ──────────────────────────────────────
    # Formatage pour injection dans le contexte
    # ──────────────────────────────────────

    def format_facts_for_prompt(self, facts: list[dict]) -> str:
        """Formate une liste de faits en texte structuré pour le prompt.

        Args:
            facts: Liste de dicts {"fact_type": ..., "content": ..., "confidence": ...}

        Returns:
            Texte formaté pour la section ## INFORMATIONS SUR L'UTILISATEUR
        """
        if not facts:
            return ""

        sections: dict[str, list[str]] = {}
        for f in facts:
            t = f.get("fact_type", "other")
            sections.setdefault(t, []).append(f["content"])

        lines = []
        type_labels = {
            "personal_info": "👤 Coordonnées & identité",
            "preference": "❤️ Préférences",
            "project": "📁 Projets",
            "task": "✅ Tâches & objectifs",
            "skill": "🎯 Compétences",
            "relationship": "🤝 Relations",
            "context": "🌍 Contexte",
            "other": "📌 Autres informations",
        }

        for fact_type in ["personal_info", "preference", "project", "task",
                          "skill", "relationship", "context", "other"]:
            if fact_type in sections:
                label = type_labels.get(fact_type, fact_type.capitalize())
                lines.append(f"### {label}")
                for content in sections[fact_type]:
                    lines.append(f"- {content}")
                lines.append("")

        return "\n".join(lines)
