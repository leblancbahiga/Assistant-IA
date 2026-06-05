"""
NURU V6 — Learning Loop : MiningWorker.

Analyse les traces d'interaction pour détecter :
- Patterns de routage sous-optimal
- Questions récurrentes qui échouent
- Ajustements de seuils suggérés
- Nouvelles règles TokenJuice candidates

Déclenché périodiquement (toutes les 50 requêtes ou manuellement).
"""
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MiningWorker:
    """Analyse les traces et produit des suggestions d'amélioration."""

    def __init__(self, trace_collector=None, config=None):
        self.traces = trace_collector
        self.config = config

    async def mine(self) -> dict:
        """Analyse les traces et retourne les patterns détectés."""
        result = {
            "bad_routing": [],
            "low_confidence": [],
            "recurring_fails": [],
            "suggestions": [],
            "stats": {},
        }

        if not self.traces:
            return result

        failed = self.traces.get_failed(limit=100)
        recent = self.traces.get_recent(limit=200)

        # Stats générales
        total = self.traces.count()
        fail_count = len(failed)
        result["stats"] = {
            "total_traces": total,
            "failed": fail_count,
            "fail_rate": round(fail_count / max(total, 1) * 100, 1),
        }

        # 1. Détection des mauvais routages
        #   Si une requête avec des mots-clés RAG est passée en CLOUD
        #   (hors cas où c'était intentionnel)
        from src.semantic_router import RAG_KEYWORDS
        for trace in failed:
            query = trace.get("query", "").lower()
            mode = trace.get("mode", "")
            has_rag_kw = any(kw in query for kw in RAG_KEYWORDS)

            if has_rag_kw and "CLOUD" in mode:
                result["bad_routing"].append({
                    "query": query[:80],
                    "mode": mode,
                    "reason": "Requête documentaire en cloud",
                    "fix": "Ajouter des mots-clés WEB_TRIGGERS ou ajuster le seuil RAG",
                })
            elif has_rag_kw and "LOCAL" in mode and trace.get("confidence", 0) < 0.3:
                result["bad_routing"].append({
                    "query": query[:80],
                    "mode": mode,
                    "confidence": trace.get("confidence"),
                    "reason": "RAG local de faible confiance sans fallback",
                    "fix": "Baisser RAG_SCORE_THRESHOLD ou activer le mode hybride",
                })

        # 2. Détection des faibles confiances récurrentes
        for trace in recent:
            if trace.get("feedback", 0) == -1 and trace.get("confidence", 0) < 0.4:
                result["low_confidence"].append({
                    "query": trace["query"][:80],
                    "confidence": trace.get("confidence"),
                })

        # 3. Mots-clés récurrents dans les échecs
        fail_queries = [t.get("query", "").lower() for t in failed if t.get("query")]
        words = []
        for q in fail_queries:
            words.extend(re.findall(r'\b[a-zéèêàù]{4,}\b', q))
        word_counts = Counter(words)
        common_words = [
            {"word": w, "count": c}
            for w, c in word_counts.most_common(10)
            if c >= 2
        ]
        if common_words:
            result["recurring_fails"] = common_words

        # 4. Suggestions automatiques
        suggestions = []

        if result["bad_routing"]:
            suggestions.append(
                "📊 Plusieurs requêtes documentaires routées en cloud. "
                "Vérifier les seuils RAG_SCORE_THRESHOLD et WEB_TRIGGERS."
            )

        if result["low_confidence"]:
            suggestions.append(
                f"📉 {len(result['low_confidence'])} réponses avec faible confiance. "
                "Envisager d'ajouter des documents sources ou d'affiner les prompts."
            )

        fail_rate = result["stats"]["fail_rate"]
        if fail_rate > 20:
            suggestions.append(
                f"⚠️ Taux d'échec élevé ({fail_rate}%). "
                "Vérifier la connectivité cloud et la qualité des documents indexés."
            )
        elif fail_rate < 5 and total > 20:
            suggestions.append(
                f"✅ Taux d'échec bas ({fail_rate}%). Bon fonctionnement général."
            )

        result["suggestions"] = suggestions
        return result

    async def generate_report(self) -> str:
        """Génère un rapport humain lisible."""
        data = await self.mine()

        lines = [
            "📊 **Rapport Learning Loop NURU**",
            f"   Traces: {data['stats'].get('total_traces', 0)} total, "
            f"{data['stats'].get('failed', 0)} échecs "
            f"({data['stats'].get('fail_rate', 0)}%)",
        ]

        if data["bad_routing"]:
            lines.append(f"\n🔴 **Mauvais routages ({len(data['bad_routing'])}):**")
            for r in data["bad_routing"][:5]:
                lines.append(f"   - \"{r['query']}\" → {r['reason']}")

        if data["low_confidence"]:
            lines.append(f"\n🟡 **Faibles confiances ({len(data['low_confidence'])}):**")
            for r in data["low_confidence"][:5]:
                lines.append(f"   - \"{r['query']}\" (conf: {r['confidence']:.2f})")

        if data["recurring_fails"]:
            lines.append(f"\n🔤 **Mots fréquents dans les échecs:**")
            for w in data["recurring_fails"][:5]:
                lines.append(f"   - \"{w['word']}\" ({w['count']}x)")

        if data["suggestions"]:
            lines.append(f"\n💡 **Suggestions:**")
            for s in data["suggestions"]:
                lines.append(f"   {s}")

        return "\n".join(lines)
