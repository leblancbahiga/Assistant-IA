"""
NURU V8+ — Diagnostic temps réel des recherches RAG.

Enregistre pour chaque requête : les stratégies tentées, leurs résultats,
les scores, les timings, et le verdict final. Permet de debugger pourquoi
un document a ou n'a pas été trouvé.

Utilisation :
    diag = RAGDiagnostic(query="rendement riz")
    diag.log_strategy("vectorielle", 3, 0.65, True, 45.2)  # 45.2 ms
    diag.log_strategy("fts", 0, 0.0, False, 12.1)
    print(diag.to_json())
"""
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StrategyInfo:
    """Informations détaillées sur une stratégie de recherche exécutée.

    Attributes:
        name: Nom de la stratégie (vectorielle, fts, grep, hyde...)
        found: Nombre de résultats trouvés
        top_score: Meilleur score de la stratégie
        hit: True si la stratégie a produit des résultats exploitables
        timing_ms: Temps d'exécution en ms
    """
    name: str
    found: int = 0
    top_score: float = 0.0
    hit: bool = False
    timing_ms: float = 0.0


class RAGDiagnostic:
    """Rapport de diagnostic structuré pour une requête RAG.

    Champs principaux :
    - strategies_tried : liste ordonnée des noms de stratégies
    - strategies_results : dict {nom: StrategyInfo}
    - confidence_label : niveau de confiance (HAUTE/MOYENNE/FAIBLE/ABSENT)
    - found_chunks : nombre de chunks trouvés après déduplication
    - verdict : résumé textuel du résultat
    - timing_ms : temps total de la recherche
    - index_stats : état de l'index au moment de la requête (optionnel)
    """

    def __init__(self, query: str = ""):
        self.query = query
        self.strategies_tried: list[str] = []
        self.strategies_results: dict[str, dict] = {}
        self.confidence_label: str = "HAUTE"
        self.found_chunks: int = 0
        self.verdict: str = ""
        self.timing_ms: float = 0.0
        self.t_start: float = 0.0
        self.index_stats: dict = {}
        self._started: bool = False

    def start(self):
        """Démarre le chronomètre (appelé en début de retrieve)."""
        self._started = True
        self.t_start = time.time()

    def stop(self):
        """Arrête le chronomètre."""
        if self._started:
            self.timing_ms = (time.time() - self.t_start) * 1000
            self._started = False

    def log_strategy(self, name: str, found: int, top_score: float,
                     hit: bool, timing_ms: float = 0.0):
        """Enregistre le résultat d'une stratégie de recherche.

        Args:
            name: Nom de la stratégie (vectorielle, fts, grep, hyde...)
            found: Nombre de résultats trouvés
            top_score: Meilleur score de la stratégie
            hit: True si la stratégie a produit des résultats exploitables
            timing_ms: Temps d'exécution en ms
        """
        self.strategies_tried.append(name)
        self.strategies_results[name] = {
            "found": found,
            "top_score": round(top_score, 3),
            "hit": hit,
            "timing_ms": round(timing_ms, 1),
        }

    def log_strategy_info(self, info: StrategyInfo):
        """Enregistre une stratégie à partir d'un objet StrategyInfo."""
        self.strategies_tried.append(info.name)
        self.strategies_results[info.name] = {
            "found": info.found,
            "top_score": round(info.top_score, 3),
            "hit": info.hit,
            "timing_ms": round(info.timing_ms, 1),
        }

    def set_confidence(self, label: str, found_chunks: int = 0):
        """Définit le niveau de confiance et le nombre de chunks trouvés.

        Args:
            label: HAUTE | MOYENNE | FAIBLE | ABSENT
            found_chunks: Nombre de chunks après déduplication
        """
        self.confidence_label = label
        self.found_chunks = found_chunks

    def set_verdict(self, verdict: str):
        """Définit le verdict de la recherche."""
        self.verdict = verdict

    def set_query(self, query: str):
        """Définit la requête (utilisé après création)."""
        self.query = query

    def set_index_stats(self, stats: dict):
        """Ajoute l'état de l'index au diagnostic."""
        self.index_stats = stats

    def to_dict(self) -> dict:
        """Sérialisation en dict pour stockage JSON."""
        return {
            "query": self.query[:200],  # Limiter la taille
            "strategies_tried": self.strategies_tried,
            "strategies_results": self.strategies_results,
            "confidence_label": self.confidence_label,
            "found_chunks": self.found_chunks,
            "verdict": self.verdict,
            "timing_ms": round(self.timing_ms, 1),
            "index_stats": self.index_stats,
        }

    def to_json(self, indent: int = 2) -> str:
        """Sérialisation en JSON."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def summary(self) -> str:
        """Résumé concis d'une ligne."""
        n_strategies = len(self.strategies_tried)
        n_hits = sum(1 for r in self.strategies_results.values() if r.get("hit"))
        return (
            f"[RAG] {n_strategies} stratégies, {n_hits} hits, "
            f"[{self.confidence_label}] {self.found_chunks} chunks, "
            f"{self.timing_ms:.0f}ms → {self.verdict}"
        )
