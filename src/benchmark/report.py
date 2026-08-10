"""V18-15 — Rapport de benchmark (schéma JSON `benchmark_*.json`).

Contrainte d'activation (V18-15 spec §3.5/§7) : la Citation Coverage dépend
de V18-24 + V18-34b (prompt qui demande le format `[SOURCE i]`). Tant que ces
décisions ne sont pas implantées, la métrique coverage est REJETÉE comme
« contrainte d'activation non satisfaite » et jamais comptée comme 0/échec.

Le flag d'activation est fourni par le runner (détection auto du format de
citation dans le contexte, ou via la décision de traçabilité V18).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


class BenchmarkReport:
    """Construit puis écrit le rapport JSON du benchmark."""

    def __init__(
        self,
        *,
        scope: str = "routing+rag",
        mode: str = "full",
        routing: dict | None = None,
        rag: dict | None = None,
    ) -> None:
        self.scope = scope
        self.mode = mode
        self.routing = routing or {}
        self.rag = rag or {}

    # ── Contrainte d'activation de la coverage ───────────────────

    @staticmethod
    def _coverage_activation_status(rag_data: dict) -> tuple[bool, str]:
        """Vérifie si la métrique coverage est activable.

        L'activation dépend du format `[SOURCE i]` réellement produit dans le
        contexte RAG — qui résulte de V18-24 + V18-34b (prompt ).
        Retourne (activable, reason).
        """
        ctx = rag_data.get("sample_context", "") or ""
        if not ctx.strip():
            # Aucun contexte → la coverage n'est pas mesurable.
            return False, "format de citation inactif (V18-24/34b non implantés)"

        import re

        has_source_fmt = bool(re.search(r"\[SOURCE\s+\d+\]", ctx))
        if not has_source_fmt:
            return False, "format [SOURCE i] absent du contexte (V18-24/34b non implantés)"
        return True, "ok"

    # ── Assemblage ───────────────────────────────────────────────

    def build(self, *, timestamp: float | None = None,
              cibles: dict | None = None) -> dict:
        ts = timestamp if timestamp is not None else time.time()
        report: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts)),
            "version": VERSION,
            "scope": self.scope,
            "mode": self.mode,
            "routing": self.routing,
            "rag": self.rag,
            "cibles_v18_41": cibles or self._eval_cibles(),
        }
        return report

    def _eval_cibles(self) -> dict:
        """Évalue les cibles V18-41 (critères de sortie) quand possible."""
        cibles: dict[str, Any] = {"recall5_ok": False}
        rag = self.rag or {}
        # Actif coverage
        activable, reason = self._coverage_activation_status(rag)
        cibles["coverage_activable"] = activable
        cibles["coverage_ok"] = activable and (rag.get("citation_coverage") or 0.0) >= 0.8
        if not activable:
            cibles["coverage_reason"] = reason
        return cibles

    # ── Écriture ─────────────────────────────────────────────────

    def write(self, out_path: str | Path = "benchmark_<ts>.json") -> str:
        """Écrit le rapport JSON ; retourne le chemin écrit."""
        report = self.build()
        path = Path(out_path)
        if "<ts>" in str(path):
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            path = Path(str(path).replace("<ts>", ts))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("📊 Benchmark rapport écrit : %s", path)
        return str(path)

    def dumps(self) -> str:
        """Sérialise le rapport en JSON (pour la CI / tests)."""
        return json.dumps(self.build(), ensure_ascii=False, indent=2)