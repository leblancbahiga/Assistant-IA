"""NURU V8+ — Page Diagnostics (section 4.5 de la spec).

Affiche les diagnostics RAG complets :
- Vue d'ensemble (requêtes totales, succès, confiance)
- Stratégies les plus utilisées (barres horizontales)
- Documents les plus fréquents
- Requêtes échouées récentes

Les données viennent du TraceCollector (SQLite) avec fallback mock.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Couleurs du thème ────────────────────────────────────────────────────

BG_DARK = "#0A0E14"
BG_PANEL = "#0D1318"
BORDER_COLOR = "#1A2332"
TEXT_PRIMARY = "#E8EAF0"
TEXT_SECONDARY = "#4A6080"
TEXT_MUTED = "#3D5266"
ACCENT_BLUE = "#1A6A9A"
ACCENT_GREEN = "#2A8A4A"
ACCENT_GOLD = "#8A7A2A"
ACCENT_RED = "#8A2A2A"
BAR_BG = "#1A2332"
BAR_FILL = "#1A5F9A"


# ══════════════════════════════════════════════════════════════════════════
#  Mock data
# ══════════════════════════════════════════════════════════════════════════

MOCK_OVERVIEW = {
    "total_queries": 47,
    "success_rate": 89,
    "high_confidence": 38,
    "low_confidence": 5,
    "retries": 3,
    "hyde_used": 8,
}

MOCK_STRATEGIES = [
    ("Vectoriel sqlite-vec", 47, 100),
    ("FTS5 BM25", 41, 87),
    ("Grep fichiers", 9, 19),
    ("HyDE", 8, 17),
]

MOCK_TOP_DOCS = [
    ("CV_Leblanc_2024.pdf", 12),
    ("Rapport_Lubero_DRC.pdf", 8),
    ("PUA-CI_Avenant.docx", 5),
    ("Rendements_riz.xlsx", 4),
    ("Budget_2025_Agriculture.pdf", 3),
]

MOCK_FAILED_QUERIES = [
    ("14:23", "rendement sorgho", "ABSENT · retry"),
    ("11:47", "budget PUA", "FAIBLE · grep utilisé"),
    ("09:12", "IITA index 2024", "ABSENT · timeout"),
    ("07:33", "prix coton 2023", "FAIBLE · FTS only"),
]


# ══════════════════════════════════════════════════════════════════════════
#  OverviewWidget
# ══════════════════════════════════════════════════════════════════════════


class OverviewWidget(QWidget):
    """Vue d'ensemble — requêtes totales, succès, confiance, retries, HyDE."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ContentCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # Titre
        title = QLabel("Vue d'ensemble")
        title.setStyleSheet(
            "font-size: 10px; color: #2A5A8A; letter-spacing: 0.12em;"
            " text-transform: uppercase; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        # Grid 2×2 de métriques
        grid = QHBoxLayout()
        grid.setSpacing(8)

        # Colonne gauche
        col_left = QVBoxLayout()
        col_left.setSpacing(4)

        self._total_label = self._make_metric_pair("Requêtes totales", "0")
        self._high_conf_label = self._make_metric_pair("Confiance HAUTE", "0")
        col_left.addLayout(self._total_label)
        col_left.addLayout(self._high_conf_label)

        # Colonne droite
        col_right = QVBoxLayout()
        col_right.setSpacing(4)

        self._success_label = self._make_metric_pair("Succès", "0%")
        self._low_conf_label = self._make_metric_pair("Confiance FAIBLE", "0")
        col_right.addLayout(self._success_label)
        col_right.addLayout(self._low_conf_label)

        grid.addLayout(col_left)
        grid.addLayout(col_right)
        layout.addLayout(grid)

        # Détails (retries, HyDE)
        details = QHBoxLayout()
        details.setSpacing(12)

        self._retries_label = QLabel("Retries  0")
        self._retries_label.setStyleSheet(
            "font-size: 9px; color: #3D5266; background: transparent;"
        )
        details.addWidget(self._retries_label)

        self._hyde_label = QLabel("HyDE  0")
        self._hyde_label.setStyleSheet(
            "font-size: 9px; color: #3D5266; background: transparent;"
        )
        details.addWidget(self._hyde_label)

        details.addStretch()
        layout.addLayout(details)

        self.setStyleSheet(
            f"#ContentCard {{"
            f"  background-color: {BG_PANEL};"
            f"  border: 0.5px solid {BORDER_COLOR};"
            f"  border-radius: 10px;"
            f"}}"
        )

    def _make_metric_pair(self, label: str, value: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            "font-size: 9px; color: #2D4052; background: transparent;"
        )
        layout.addWidget(lbl)

        val = QLabel(value)
        val.setStyleSheet(
            "font-size: 14px; font-weight: 500; color: #4A8AB0;"
            " font-family: 'SF Mono', 'Consolas', monospace; background: transparent;"
        )
        layout.addWidget(val)

        layout.addStretch()
        return layout

    def set_overview(self, data: dict) -> None:
        """Met à jour les valeurs de la vue d'ensemble."""
        self._total_label.itemAt(1).widget().setText(str(data.get("total_queries", 0)))
        self._success_label.itemAt(1).widget().setText(f"{data.get('success_rate', 0)}%")
        self._high_conf_label.itemAt(1).widget().setText(str(data.get("high_confidence", 0)))
        self._low_conf_label.itemAt(1).widget().setText(str(data.get("low_confidence", 0)))
        self._retries_label.setText(f"Retries  {data.get('retries', 0)}")
        self._hyde_label.setText(f"HyDE  {data.get('hyde_used', 0)}")

    def set_mock(self) -> None:
        """Charge les données mockées."""
        self.set_overview(MOCK_OVERVIEW)


# ══════════════════════════════════════════════════════════════════════════
#  StrategiesChartWidget
# ══════════════════════════════════════════════════════════════════════════


class StrategiesChartWidget(QWidget):
    """Stratégies les plus utilisées — barres horizontales avec pourcentages."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ContentCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # Titre
        title = QLabel("Stratégies les plus utilisées")
        title.setStyleSheet(
            "font-size: 10px; color: #2A5A8A; letter-spacing: 0.12em;"
            " text-transform: uppercase; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        self._bars_layout = QVBoxLayout()
        self._bars_layout.setSpacing(4)
        self._bars_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._bars_layout)

        layout.addStretch()

        self.setStyleSheet(
            f"#ContentCard {{"
            f"  background-color: {BG_PANEL};"
            f"  border: 0.5px solid {BORDER_COLOR};"
            f"  border-radius: 10px;"
            f"}}"
        )

    def set_strategies(self, strategies: list[tuple[str, int, int]]) -> None:
        """Met à jour les barres.

        Chaque tuple : (name, count, percent)
        """
        # Nettoyer
        while self._bars_layout.count():
            item = self._bars_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for name, count, percent in strategies:
            row = QWidget()
            row.setFixedHeight(24)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            # Name
            name_label = QLabel(name)
            name_label.setStyleSheet(
                "font-size: 10px; color: #4A6A8A; background: transparent;"
            )
            name_label.setFixedWidth(140)
            row_layout.addWidget(name_label)

            # Bar
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setFixedHeight(8)
            bar.setValue(min(100, percent))
            bar.setTextVisible(False)
            bar.setStyleSheet(
                f"background-color: {BAR_BG}; border-radius: 4px; border: none;"
                f" QProgressBar::chunk {{"
                f"   background-color: {BAR_FILL}; border-radius: 4px;"
                f" }}"
            )
            row_layout.addWidget(bar, stretch=1)

            # Count
            count_label = QLabel(f"{count} ({percent}%)")
            count_label.setStyleSheet(
                "font-size: 10px; color: #6A8AAA;"
                " font-family: 'SF Mono', 'Consolas', monospace; background: transparent;"
            )
            count_label.setFixedWidth(70)
            row_layout.addWidget(count_label)

            self._bars_layout.addWidget(row)

    def set_mock(self) -> None:
        """Charge les données mockées."""
        self.set_strategies(MOCK_STRATEGIES)


# ══════════════════════════════════════════════════════════════════════════
#  TopDocsWidget
# ══════════════════════════════════════════════════════════════════════════


class TopDocsWidget(QWidget):
    """Documents les plus fréquents — liste avec compteur."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ContentCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        title = QLabel("Documents les plus fréquents")
        title.setStyleSheet(
            "font-size: 10px; color: #2A5A8A; letter-spacing: 0.12em;"
            " text-transform: uppercase; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        self._docs_layout = QVBoxLayout()
        self._docs_layout.setSpacing(2)
        self._docs_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._docs_layout)

        layout.addStretch()

        self.setStyleSheet(
            f"#ContentCard {{"
            f"  background-color: {BG_PANEL};"
            f"  border: 0.5px solid {BORDER_COLOR};"
            f"  border-radius: 10px;"
            f"}}"
        )

    def set_docs(self, docs: list[tuple[str, int]]) -> None:
        """Met à jour la liste.

        Chaque tuple : (filename, count)
        """
        while self._docs_layout.count():
            item = self._docs_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for filename, count in docs:
            row = QWidget()
            row.setFixedHeight(20)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 0, 4, 0)
            row_layout.setSpacing(6)

            icon = QLabel("📄")
            icon.setStyleSheet("font-size: 11px; background: transparent;")
            row_layout.addWidget(icon)

            name_label = QLabel(filename)
            name_label.setStyleSheet(
                "font-size: 10px; color: #5A7A9A; background: transparent;"
            )
            row_layout.addWidget(name_label, stretch=1)

            count_label = QLabel(f"{count} fois")
            count_label.setStyleSheet(
                "font-size: 10px; color: #3D5266; background: transparent;"
            )
            row_layout.addWidget(count_label)

            self._docs_layout.addWidget(row)

    def set_mock(self) -> None:
        """Charge les données mockées."""
        self.set_docs(MOCK_TOP_DOCS)


# ══════════════════════════════════════════════════════════════════════════
#  FailedQueriesWidget
# ══════════════════════════════════════════════════════════════════════════


class FailedQueriesWidget(QWidget):
    """Requêtes échouées récentes — liste chronologique."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ContentCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        title = QLabel("Requêtes échouées récentes")
        title.setStyleSheet(
            "font-size: 10px; color: #2A5A8A; letter-spacing: 0.12em;"
            " text-transform: uppercase; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        self._queries_layout = QVBoxLayout()
        self._queries_layout.setSpacing(2)
        self._queries_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._queries_layout)

        layout.addStretch()

        self.setStyleSheet(
            f"#ContentCard {{"
            f"  background-color: {BG_PANEL};"
            f"  border: 0.5px solid {BORDER_COLOR};"
            f"  border-radius: 10px;"
            f"}}"
        )

    def set_queries(self, queries: list[tuple[str, str, str]]) -> None:
        """Met à jour la liste.

        Chaque tuple : (time, query, reason)
        """
        while self._queries_layout.count():
            item = self._queries_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for time_str, query, reason in queries:
            row = QWidget()
            row.setFixedHeight(20)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 0, 4, 0)
            row_layout.setSpacing(8)

            time_label = QLabel(f"[{time_str}]")
            time_label.setStyleSheet(
                "font-size: 9px; color: #3D5266;"
                " font-family: 'SF Mono', 'Consolas', monospace; background: transparent;"
            )
            time_label.setFixedWidth(50)
            row_layout.addWidget(time_label)

            query_label = QLabel(f"\"{query}\"")
            query_label.setStyleSheet(
                "font-size: 10px; color: #8A6A5A; background: transparent;"
            )
            row_layout.addWidget(query_label, stretch=1)

            reason_label = QLabel(f"— {reason}")
            reason_label.setStyleSheet(
                "font-size: 9px; color: #7A4A3A; background: transparent;"
            )
            row_layout.addWidget(reason_label)

            self._queries_layout.addWidget(row)

    def set_mock(self) -> None:
        """Charge les données mockées."""
        self.set_queries(MOCK_FAILED_QUERIES)


# ══════════════════════════════════════════════════════════════════════════
#  DiagnosticsPage — Page complète
# ══════════════════════════════════════════════════════════════════════════


class DiagnosticsPage(QWidget):
    """Page Diagnostics V8+ complète — sidebar slug 'diagnostics'.

    Affiche :
    - Filtres (période, type)
    - Vue d'ensemble
    - Stratégies les plus utilisées (barres)
    - Documents les plus fréquents
    - Requêtes échouées récentes
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DiagnosticsPage")

        # Layout principal
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(
            f"background-color: {BG_PANEL};"
            f" border-bottom: 0.5px solid {BORDER_COLOR};"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        header_layout.setSpacing(12)

        title = QLabel("DIAGNOSTICS V8+")
        title.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #4A8AB0;"
            " letter-spacing: 0.10em; background: transparent;"
        )
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Filtres
        self._period_combo = QComboBox()
        self._period_combo.addItems(["Aujourd'hui", "Cette semaine", "Ce mois", "Tout"])
        self._period_combo.setStyleSheet(
            f"background-color: {BG_DARK}; color: #4A6080;"
            f" border: 0.5px solid {BORDER_COLOR}; border-radius: 6px;"
            f" padding: 4px 10px; font-size: 10px; min-width: 120px;"
        )
        header_layout.addWidget(self._period_combo)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["Tous", "Échecs", "Succès", "HyDE"])
        self._filter_combo.setStyleSheet(
            f"background-color: {BG_DARK}; color: #4A6080;"
            f" border: 0.5px solid {BORDER_COLOR}; border-radius: 6px;"
            f" padding: 4px 10px; font-size: 10px; min-width: 100px;"
        )
        header_layout.addWidget(self._filter_combo)

        outer_layout.addWidget(header)

        # Scroll area pour le contenu
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "background-color: transparent; border: none;"
        )

        content = QWidget()
        content.setStyleSheet(f"background-color: {BG_DARK};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 16, 20, 20)
        content_layout.setSpacing(12)

        # Vue d'ensemble
        self._overview = OverviewWidget()
        content_layout.addWidget(self._overview)

        # Stratégies
        self._strategies_chart = StrategiesChartWidget()
        content_layout.addWidget(self._strategies_chart)

        # Top Docs + Failed Queries side by side
        row = QHBoxLayout()
        row.setSpacing(12)

        self._top_docs = TopDocsWidget()
        self._failed_queries = FailedQueriesWidget()

        row.addWidget(self._top_docs, stretch=1)
        row.addWidget(self._failed_queries, stretch=1)
        content_layout.addLayout(row)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll, stretch=1)

        # Charger les données mockées
        self.load_mock_data()

        # Timer pour rafraîchissement périodique (toutes les 10s)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(10000)
        self._refresh_timer.timeout.connect(self._refresh_data)
        self._refresh_timer.start()

    def load_mock_data(self) -> None:
        """Charge les données mockées pour l'affichage initial."""
        self._overview.set_mock()
        self._strategies_chart.set_mock()
        self._top_docs.set_mock()
        self._failed_queries.set_mock()

    def _refresh_data(self) -> None:
        """Rafraîchit les données depuis TraceCollector ou garde les mock."""
        try:
            from src.learning.trace_collector import TraceCollector
            import os

            tc = TraceCollector()
            # Tentative de lecture depuis la base SQLite
            import sqlite3

            if os.path.exists(tc.db_path):
                conn = sqlite3.connect(tc.db_path)
                cursor = conn.cursor()

                # Total queries
                cursor.execute("SELECT COUNT(*) FROM traces")
                total = cursor.fetchone()[0]

                # Succès (confidence > 0.5)
                cursor.execute("SELECT COUNT(*) FROM traces WHERE confidence > 0.5")
                high_conf = cursor.fetchone()[0]

                # Échecs
                low_conf = total - high_conf

                success_rate = int(high_conf / total * 100) if total > 0 else 0

                self._overview.set_overview({
                    "total_queries": total,
                    "success_rate": success_rate,
                    "high_confidence": high_conf,
                    "low_confidence": low_conf,
                    "retries": 0,
                    "hyde_used": 0,
                })

                # Dernières requêtes échouées
                cursor.execute(
                    "SELECT timestamp, query, confidence FROM traces "
                    "WHERE confidence < 0.5 ORDER BY timestamp DESC LIMIT 10"
                )
                failed = cursor.fetchall()
                if failed:
                    queries = []
                    for ts, q, conf in failed:
                        time_str = ts.split(" ")[1][:5] if " " in ts else ts[:5]
                        reason = "FAIBLE" if conf > 0 else "ABSENT"
                        queries.append((time_str, q, f"{reason} · DB"))
                    self._failed_queries.set_queries(queries)

                conn.close()
        except Exception as e:
            logger.debug("TraceCollector refresh: %s (keeping mock data)", e)
