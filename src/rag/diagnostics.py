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


class RAGDiagnostic:
    """Rapport de diagnostic structuré pour une requête RAG.

    Champs principaux :
    - strategies_tried : liste ordonnée des noms de stratégies
    - strategies_results : dict {nom: {found, top_score, hit, timing_ms}}
    - verdict : résumé textuel du résultat
    - timing_ms : temps total de la recherche
    - index_stats : état de l'index au moment de la requête (optionnel)
    """

    def __init__(self, query: str = ""):
        self.query = query
        self.strategies_tried: list[str] = []
        self.strategies_results: dict[str, dict] = {}
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
            f"{self.timing_ms:.0f}ms → {self.verdict}"
        )
