"""RAGDiagnosticViewModel — Bridge Qt ↔ RAGDiagnostic.

Met à disposition les propriétés Qt d'un RAGDiagnostic pour l'UI,
avec un signal ``updated`` pour notifier les widgets.

Utilisation :
    vm = RAGDiagnosticViewModel()
    vm.updated.connect(panel.update_from_diagnostics_viewmodel)
    vm.update_from_diagnostic(diag)
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Property, Signal


class RAGDiagnosticViewModel(QObject):
    """ViewModel pour RAGDiagnostic — expose les champs comme propriétés Qt.

    Signaux
    -------
    updated : émis après chaque mise à jour depuis un RAGDiagnostic
    """

    updated = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._confidence_label: str = "—"
        self._final_score: float = 0.0
        self._strategies: list[dict] = []
        self._fact_check_triggered: bool = False
        self._found_chunks: int = 0
        self._query: str = ""
        self._verdict: str = ""

    # ── API publique ──

    def update_from_diagnostic(self, diag) -> None:
        """Met à jour toutes les propriétés depuis un RAGDiagnostic.

        Args:
            diag: Instance de RAGDiagnostic (src.rag.diagnostics)
        """
        self._confidence_label = getattr(diag, 'confidence_label', '—')
        self._found_chunks = getattr(diag, 'found_chunks', 0)
        self._query = getattr(diag, 'query', '')
        self._verdict = getattr(diag, 'verdict', '')

        # Calculer le score final à partir des stratégies
        strategies_results = getattr(diag, 'strategies_results', {})
        scores = [
            v.get('top_score', 0.0)
            for v in strategies_results.values()
            if isinstance(v, dict) and v.get('hit')
        ]
        self._final_score = max(scores) if scores else 0.0

        # Stratégies sous forme de liste de dicts
        self._strategies = [
            {
                'name': name,
                'found': info.get('found', 0),
                'top_score': info.get('top_score', 0.0),
                'hit': info.get('hit', False),
                'timing_ms': info.get('timing_ms', 0.0),
            }
            for name, info in strategies_results.items()
        ]

        # Fact-check triggered si une stratégie a 0 hit
        self._fact_check_triggered = any(
            not info.get('hit', False)
            for info in strategies_results.values()
        )

        self.updated.emit()

    # ── Propriétés Qt ──

    @Property(str, notify=updated)
    def confidence_label(self) -> str:
        return self._confidence_label

    @Property(float, notify=updated)
    def final_score(self) -> float:
        return self._final_score

    @Property(list, notify=updated)
    def strategies(self) -> list:
        return self._strategies

    @Property(bool, notify=updated)
    def fact_check_triggered(self) -> bool:
        return self._fact_check_triggered

    @Property(int, notify=updated)
    def found_chunks(self) -> int:
        return self._found_chunks

    @Property(str, notify=updated)
    def query(self) -> str:
        return self._query

    @Property(str, notify=updated)
    def verdict(self) -> str:
        return self._verdict
