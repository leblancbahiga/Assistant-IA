"""NURU V8+ — Panneau de Diagnostic RAG (bleu-vert).

Remplaçant de MetricsPanel (violet) pour la migration 3 colonnes.
Composants :
  - MetricCard, MetricsGrid (2×2)
  - RamBar, RagScoreBar
  - StrategyRow, StrategyDiagnostic
  - IndexHealthWidget, FactCheckRow, FactCheckWidget
  - RetroBanner
  - RagTabWidget, RightPanelDiagnostic
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

logger = logging.getLogger(__name__)

# ── Couleurs du thème bleu-vert ───────────────────────────────────────────

SCORE_HIGH = "#2A8A4A"
SCORE_MED = "#8A7A2A"
SCORE_LOW = "#8A2A2A"
ACCENT_BLUE = "#1A6A9A"
ACCENT_BLUE_LIGHT = "#2A7FBF"
BG_DARK = "#0A0E14"
BG_PANEL = "#0C1018"
BG_SIDEBAR = "#0D1318"
BORDER_COLOR = "#1A2332"
TEXT_PRIMARY = "#E8EAF0"
TEXT_SECONDARY = "#4A6080"
TEXT_MUTED = "#3D5266"
TEXT_DIM = "#2D4052"


# ══════════════════════════════════════════════════════════════════════════
#  Module 5 — Composants atomiques
# ══════════════════════════════════════════════════════════════════════════


class MetricCard(QWidget):
    """Carte métrique réutilisable — label + valeur + sous-titre.

    Style sombre, bord #1A2332, fond #0A0E14.
    """

    def __init__(
        self,
        label: str = "",
        value: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFixedHeight(62)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._label_w = QLabel(label)
        self._label_w.setStyleSheet(
            "font-size: 9px; color: #2D4052; letter-spacing: 0.10em;"
            " text-transform: uppercase; background: transparent;"
        )
        layout.addWidget(self._label_w)

        value_row = QHBoxLayout()
        value_row.setSpacing(2)

        self._value_w = QLabel(value)
        self._value_w.setStyleSheet(
            "font-size: 18px; font-weight: 500; color: #4A8AB0;"
            " font-family: 'SF Mono', 'Consolas', monospace; background: transparent;"
        )
        value_row.addWidget(self._value_w)
        value_row.addStretch()
        layout.addLayout(value_row)

        self._subtitle_w = QLabel(subtitle)
        self._subtitle_w.setStyleSheet(
            "font-size: 9px; color: #2A5A3A; background: transparent;"
        )
        layout.addWidget(self._subtitle_w)

        self.setStyleSheet(
            f"background-color: {BG_DARK};"
            f" border: 0.5px solid {BORDER_COLOR};"
            " border-radius: 6px;"
        )

    def set_value(self, value: str) -> None:
        self._value_w.setText(value)

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle_w.setText(subtitle)

    def set_label(self, label: str) -> None:
        self._label_w.setText(label)


class StrategyRow(QWidget):
    """Ligne de diagnostic — icône + nom + score + temps.

    Score-high = #2A8A4A, score-med = #8A7A2A, score-low = #8A2A2A.
    Les stratégies skipées ont opacité réduite.
    """

    def __init__(
        self,
        icon: str = "○",
        name: str = "",
        score: str = "",
        time_str: str = "",
        skipped: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._skipped = skipped
        self.setFixedHeight(26 if not skipped else 24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._icon_w = QLabel(icon)
        self._icon_w.setStyleSheet(
            "font-size: 13px; background: transparent;"
        )
        layout.addWidget(self._icon_w)

        self._name_w = QLabel(name)
        self._name_w.setStyleSheet(
            "font-size: 10px; color: #4A6A8A; background: transparent;"
        )
        layout.addWidget(self._name_w, stretch=1)

        self._score_w = QLabel(score)
        score_color = TEXT_DIM if skipped else self._score_color(score)
        self._score_w.setStyleSheet(
            f"font-size: 10px; color: {score_color};"
            " font-family: 'SF Mono', 'Consolas', monospace; background: transparent;"
        )
        layout.addWidget(self._score_w)

        self._time_w = QLabel(time_str)
        self._time_w.setStyleSheet(
            "font-size: 9px; color: #2D4052; background: transparent;"
        )
        layout.addWidget(self._time_w)

        if skipped:
            self.setStyleSheet("opacity: 0.4;")
        else:
            self.setStyleSheet(
                f"background-color: {BG_DARK};"
                f" border: 0.5px solid {BORDER_COLOR};"
                " border-radius: 5px;"
            )

    @staticmethod
    def _score_color(score_str: str) -> str:
        """Détermine la couleur selon la valeur du score."""
        try:
            val = float(score_str)
            if val >= 0.70:
                return SCORE_HIGH
            elif val >= 0.40:
                return SCORE_MED
            else:
                return SCORE_LOW
        except (ValueError, TypeError):
            return TEXT_DIM

    def set_data(
        self, icon: str, name: str, score: str, time_str: str, skipped: bool = False
    ) -> None:
        self._icon_w.setText(icon)
        self._name_w.setText(name)
        self._score_w.setText(score)
        self._score_w.setStyleSheet(
            f"font-size: 10px; color: {TEXT_DIM if skipped else self._score_color(score)};"
            " font-family: 'SF Mono', 'Consolas', monospace; background: transparent;"
        )
        self._time_w.setText(time_str)
        self._skipped = skipped
        if skipped:
            self.setStyleSheet("opacity: 0.4;")
        else:
            self.setStyleSheet(
                f"background-color: {BG_DARK};"
                f" border: 0.5px solid {BORDER_COLOR};"
                " border-radius: 5px;"
            )


class FactCheckRow(QWidget):
    """Ligne de vérification — icône ✅/⚠️ + texte."""

    def __init__(
        self,
        text: str = "",
        verified: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFixedHeight(18)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        icon = "✅" if verified else "⚠️"
        icon_color = "#1A8A3A" if verified else "#8A6A1A"
        self._icon_w = QLabel(icon)
        self._icon_w.setStyleSheet(
            f"font-size: 11px; color: {icon_color}; background: transparent;"
        )
        layout.addWidget(self._icon_w)

        text_color = "#2A5A3A" if verified else "#7A5A1A"
        self._text_w = QLabel(text)
        self._text_w.setStyleSheet(
            f"font-size: 9px; color: {text_color}; background: transparent;"
        )
        layout.addWidget(self._text_w)

        layout.addStretch()

    def set_data(self, text: str, verified: bool = True) -> None:
        icon = "✅" if verified else "⚠️"
        icon_color = "#1A8A3A" if verified else "#8A6A1A"
        text_color = "#2A5A3A" if verified else "#7A5A1A"
        self._icon_w.setText(icon)
        self._icon_w.setStyleSheet(
            f"font-size: 11px; color: {icon_color}; background: transparent;"
        )
        self._text_w.setText(text)
        self._text_w.setStyleSheet(
            f"font-size: 9px; color: {text_color}; background: transparent;"
        )


class CitationChip(QLabel):
    """Chip de source cliquable (pour chat_bubble.py)."""

    def __init__(
        self,
        source_path: str = "",
        parent: QWidget | None = None,
    ):
        self._source_path = source_path
        filename = source_path.split("/")[-1] if source_path else "source"
        display = f"📄 {filename}"
        super().__init__(display, parent)
        self.setToolTip(source_path)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"background-color: #0A1830;"
            f" border: 0.5px solid #1A3050;"
            f" border-radius: 4px;"
            f" font-size: 9px;"
            f" color: #2A6AAA;"
            f" padding: 1px 6px;"
        )

    def set_source(self, source_path: str) -> None:
        self._source_path = source_path
        filename = source_path.split("/")[-1] if source_path else "source"
        self.setText(f"📄 {filename}")
        self.setToolTip(source_path)


# ══════════════════════════════════════════════════════════════════════════
#  Module 1 — RightPanelDiagnostic Components
# ══════════════════════════════════════════════════════════════════════════


class MetricsGrid(QWidget):
    """Grid 2×2 de MetricCards : Tokens/s, RAM, Chunks RAG, Latence."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MetricsGrid")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 4)
        layout.setSpacing(6)

        # Row 1
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self._tokens_card = MetricCard("Tokens/s", "0", "↑ —")
        self._ram_card = MetricCard("RAM", "0", "/ 0 Go · —")
        row1.addWidget(self._tokens_card)
        row1.addWidget(self._ram_card)
        layout.addLayout(row1)

        # Row 2
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self._chunks_card = MetricCard("Chunks RAG", "0", "0 haute · 0 moy.")
        self._latence_card = MetricCard("Latence", "0", "Query + gen.")
        row2.addWidget(self._chunks_card)
        row2.addWidget(self._latence_card)
        layout.addLayout(row2)

    def set_tokens(self, tok_s: float, subtitle: str = "↑ —") -> None:
        self._tokens_card.set_value(f"{tok_s:.0f}")
        self._tokens_card.set_subtitle(subtitle)

    def set_ram(self, used_gb: str, total_gb: str, status: str = "stable") -> None:
        self._ram_card.set_value(f"{used_gb}")
        self._ram_card.set_subtitle(f"/ {total_gb} Go · {status}")

    def set_chunks(self, high: int, medium: int, total: int) -> None:
        self._chunks_card.set_value(str(total))
        self._chunks_card.set_subtitle(f"{high} haute · {medium} moy.")

    def set_latence(self, seconds: float, subtitle: str = "Query + gen.") -> None:
        self._latence_card.set_value(f"{seconds:.1f}")
        self._latence_card.set_subtitle(subtitle)


class RamBar(QWidget):
    """Barre horizontale RAM unifiée."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(28)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(4)

        # Label
        self._label = QLabel("RAM unifiée · 0.0 / 0 Go")
        self._label.setStyleSheet(
            "font-size: 9px; color: #2D4052; letter-spacing: 0.08em;"
            " text-transform: uppercase; background: transparent;"
        )
        layout.addWidget(self._label)

        # Barre
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setFixedHeight(4)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(
            f"background-color: {BORDER_COLOR}; border-radius: 2px;"
            " border: none;"
        )
        self._bar.setObjectName("RamBarProgress")
        layout.addWidget(self._bar)

    def set_ram(self, percent: float, used_gb: str, total_gb: str) -> None:
        self._label.setText(f"RAM unifiée · {used_gb} / {total_gb} Go")
        pct = max(0, min(100, int(percent)))
        self._bar.setValue(pct)
        # Couleur de la barre via QSS
        self._bar.setStyleSheet(
            f"background-color: {BORDER_COLOR}; border-radius: 2px;"
            " border: none;"
            f" QProgressBar::chunk {{ background-color: #1A7A4A; border-radius: 2px; }}"
        )


class RagScoreBar(QWidget):
    """Barre Score RAG avec label."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._score: float = 0.0
        self.setFixedHeight(28)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.setSpacing(0)

        self._label = QLabel("Score RAG")
        self._label.setStyleSheet(
            "font-size: 9px; color: #2D4052; letter-spacing: 0.08em;"
            " text-transform: uppercase; background: transparent;"
        )
        header.addWidget(self._label)

        header.addStretch()

        self._value_label = QLabel("0.00 · —")
        self._value_label.setStyleSheet(
            "font-size: 9px; color: #2A7A4A; background: transparent;"
        )
        header.addWidget(self._value_label)
        layout.addLayout(header)

        # Barre
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setFixedHeight(3)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(
            f"background-color: {BORDER_COLOR}; border-radius: 2px;"
            " border: none;"
        )
        self._bar.setObjectName("RagScoreBarProgress")
        layout.addWidget(self._bar)

    def set_score(self, score: float) -> None:
        """Met à jour le score (0.0 → 1.0) et affiche le niveau."""
        self._score = max(0.0, min(1.0, score))
        pct = int(self._score * 100)
        self._bar.setValue(pct)

        if self._score >= 0.75:
            level = "HAUTE"
            color = SCORE_HIGH
        elif self._score >= 0.40:
            level = "MOYENNE"
            color = SCORE_MED
        else:
            level = "FAIBLE"
            color = SCORE_LOW

        self._value_label.setText(f"{self._score:.2f} · {level}")
        self._value_label.setStyleSheet(
            f"font-size: 9px; color: {color}; background: transparent;"
        )
        self._bar.setStyleSheet(
            f"background-color: {BORDER_COLOR}; border-radius: 2px;"
            " border: none;"
            f" QProgressBar::chunk {{ background-color: {color}; border-radius: 2px; }}"
        )


class StrategyDiagnostic(QWidget):
    """Liste des stratégies essayées."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: list[StrategyRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 4)
        layout.setSpacing(3)

        # Titre
        title = QLabel("Stratégies exécutées")
        title.setStyleSheet(
            "font-size: 9px; color: #2D4052; letter-spacing: 0.12em;"
            " text-transform: uppercase; background: transparent;"
        )
        layout.addWidget(title)

        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(3)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._list_layout)

        # Données par défaut (mock)
        self.set_strategies([
            ("🔺", "Vectoriel sqlite-vec", "0.81", "48ms", False),
            ("📝", "FTS5 BM25", "0.74", "12ms", False),
            ("🔍", "Grep fichiers", "skip", "—", True),
            ("✨", "HyDE", "skip", "—", True),
        ])

    def set_strategies(self, strategies: list[tuple]) -> None:
        """Met à jour toutes les stratégies.
        
        Chaque tuple : (icon, name, score, time, skipped)
        """
        # Nettoyer les anciennes lignes
        for row in self._rows:
            self._list_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()

        for icon, name, score, time_str, skipped in strategies:
            row = StrategyRow(icon, name, score, time_str, skipped)
            self._rows.append(row)
            self._list_layout.addWidget(row)

        self._list_layout.addStretch()


class IndexHealthWidget(QWidget):
    """Documents indexés, avertissements, dernier scan."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Titre
        title = QLabel("Index Health")
        title.setStyleSheet(
            "font-size: 9px; color: #2D4052; letter-spacing: 0.12em;"
            " text-transform: uppercase; background: transparent;"
        )
        layout.addWidget(title)

        # Documents
        self._docs_row = self._make_health_row("Documents indexés", "0 / 0", "health-ok")
        layout.addWidget(self._docs_row)

        # Avertissements
        self._warn_row = self._make_health_row("Avertissements", "—", "health-warn")
        layout.addWidget(self._warn_row)

        # Dernier scan
        self._scan_row = self._make_health_row("Dernier scan", "—", "health-muted")
        layout.addWidget(self._scan_row)

        self.setStyleSheet(
            f"background-color: {BG_DARK};"
            f" border: 0.5px solid {BORDER_COLOR};"
            " border-radius: 6px;"
        )

    def _make_health_row(self, label: str, value: str, style_class: str) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            "font-size: 9px; color: #2D4052; letter-spacing: 0.06em;"
            " background: transparent;"
        )
        layout.addWidget(lbl)

        layout.addStretch()

        val = QLabel(value)
        color = "#2A8A4A" if style_class == "health-ok" else (
            "#8A5A1A" if style_class == "health-warn" else "#2D4052"
        )
        val.setStyleSheet(
            f"font-size: 10px; color: {color};"
            " font-family: 'SF Mono', 'Consolas', monospace; background: transparent;"
        )
        layout.addWidget(val)

        return w

    def set_docs(self, indexed: int, total: int) -> None:
        self._docs_row.findChild(QLabel, "", Qt.FindChildrenRecursively).setText(
            f"{indexed} / {total}"
        )
        # On met à jour via le second QLabel
        labels = self._docs_row.findChildren(QLabel)
        for lbl in labels:
            if lbl.text().startswith("Documents"):
                continue
            lbl.setText(f"{indexed} / {total}")

    def set_warnings(self, text: str) -> None:
        labels = self._warn_row.findChildren(QLabel)
        for lbl in labels:
            if lbl.text().startswith("Avertissements"):
                continue
            lbl.setText(text)

    def set_last_scan(self, text: str) -> None:
        labels = self._scan_row.findChildren(QLabel)
        for lbl in labels:
            if lbl.text().startswith("Dernier"):
                continue
            lbl.setText(text)


class FactCheckWidget(QWidget):
    """Vérificateur de faits par source."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: list[FactCheckRow] = []
        self.setFixedHeight(60)  # Ajusté par le contenu

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        # Label
        lbl = QLabel("Vérificateur de faits")
        lbl.setStyleSheet(
            "font-size: 9px; color: #1A7A3A; letter-spacing: 0.08em;"
            " text-transform: uppercase; background: transparent;"
        )
        layout.addWidget(lbl)

        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(1)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._list_layout)

        # Données mock
        self.set_facts([
            ("14 compétences — sources confirmées", True),
            ("6 correspondances IITA — confirmées", True),
            ("IRR/SPIA — non trouvé dans les sources", False),
        ])

        self.setStyleSheet(
            "background-color: #040E08;"
            " border: 0.5px solid #1A3A1F;"
            " border-left: 2px solid #1A7A3A;"
            " border-radius: 0 5px 5px 0;"
        )

    def set_facts(self, facts: list[tuple[str, bool]]) -> None:
        """Met à jour les vérifications.
        
        Chaque tuple : (text, verified)
        """
        for row in self._rows:
            self._list_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()

        for text, verified in facts:
            row = FactCheckRow(text, verified)
            self._rows.append(row)
            self._list_layout.addWidget(row)


class RetroBanner(QWidget):
    """Bannière d'info décomposition et query rewriting."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        icon = QLabel("ℹ️")
        icon.setStyleSheet("font-size: 13px; color: #7A5A2A; background: transparent;")
        layout.addWidget(icon)

        self._text = QLabel(
            "Requête simple · Query rewriting inactif"
        )
        self._text.setStyleSheet(
            "font-size: 9px; color: #8A5A2A; line-height: 1.4; background: transparent;"
        )
        layout.addWidget(self._text, stretch=1)

        self.setStyleSheet(
            "background-color: #100A05;"
            " border: 0.5px solid #3A1A05;"
            " border-left: 2px solid #8A4A1A;"
            " border-radius: 0 5px 5px 0;"
        )

    def set_info(self, text: str) -> None:
        self._text.setText(text)


class MetricsTab(QWidget):
    """Onglet Métriques — grid + barres + diagnostic."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "background-color: transparent; border: none;"
        )

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # MetricsGrid
        self.metrics_grid = MetricsGrid()
        content_layout.addWidget(self.metrics_grid)

        # RamBar
        self.ram_bar = RamBar()
        content_layout.addWidget(self.ram_bar)

        # RagScoreBar
        self.rag_score_bar = RagScoreBar()
        content_layout.addWidget(self.rag_score_bar)

        # StrategyDiagnostic
        self.strategy_diag = StrategyDiagnostic()
        content_layout.addWidget(self.strategy_diag)

        # IndexHealth
        self.index_health = IndexHealthWidget()
        content_layout.addWidget(self.index_health)

        # FactCheckWidget
        self.fact_check = FactCheckWidget()
        content_layout.addWidget(self.fact_check)

        # RetroBanner
        self.retro_banner = RetroBanner()
        content_layout.addWidget(self.retro_banner)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)


class IndexTab(QWidget):
    """Onglet Index — santé de l'index."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel("Index des documents")
        label.setStyleSheet(
            "font-size: 11px; color: #4A6A8A; letter-spacing: 0.06em;"
            " text-transform: uppercase; background: transparent;"
        )
        layout.addWidget(label)

        # IndexHealth complet ici
        self.index_health = IndexHealthWidget()
        layout.addWidget(self.index_health)

        layout.addStretch()


class TracesTab(QWidget):
    """Onglet Traces — journal des opérations."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel("Traces d'exécution")
        label.setStyleSheet(
            "font-size: 11px; color: #4A6A8A; letter-spacing: 0.06em;"
            " text-transform: uppercase; background: transparent;"
        )
        layout.addWidget(label)

        self._trace_label = QLabel("Aucune trace pour l'instant.")
        self._trace_label.setStyleSheet(
            "color: #3D5266; font-size: 10px; background: transparent;"
        )
        layout.addWidget(self._trace_label)

        layout.addStretch()

    def set_traces(self, count: int) -> None:
        if count > 0:
            self._trace_label.setText(f"{count} traces enregistrées.")
        else:
            self._trace_label.setText("Aucune trace pour l'instant.")


class RagTabWidget(QTabWidget):
    """QTabWidget à 3 onglets — Métriques, Index, Traces."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RagTabWidget")

        self._metrics_tab = MetricsTab()
        self._index_tab = IndexTab()
        self._traces_tab = TracesTab()

        self.addTab(self._metrics_tab, "Métriques")
        self.addTab(self._index_tab, "Index")
        self.addTab(self._traces_tab, "Traces")

        # Style via QSS objectName
        self.setStyleSheet(
            f"#RagTabWidget::pane {{"
            f"  border: none; background-color: transparent;"
            f"}}"
            f"#RagTabWidget QTabBar::tab {{"
            f"  color: #3D5266; font-size: 10px; padding: 4px 10px;"
            f"  border-bottom: 1.5px solid transparent;"
            f"}}"
            f"#RagTabWidget QTabBar::tab:selected {{"
            f"  color: #2A7FBF; border-bottom: 1.5px solid #2A7FBF;"
            f"}}"
            f"#RagTabWidget QTabBar::tab:hover:!selected {{"
            f"  color: #5A7A9A;"
            f"}}"
        )

    @property
    def metrics(self) -> MetricsTab:
        return self._metrics_tab

    @property
    def index_tab(self) -> IndexTab:
        return self._index_tab

    @property
    def traces(self) -> TracesTab:
        return self._traces_tab


# ══════════════════════════════════════════════════════════════════════════
#  RightPanelDiagnostic — Widget principal
# ══════════════════════════════════════════════════════════════════════════


class RightPanelDiagnostic(QWidget):
    """Panneau droit complet de Diagnostic RAG (bleu-vert).

    Remplace MetricsPanel (violet). Même API publique :
      - set_ram(percent, used_gb, total_gb)
      - set_strategy(strategy, model)
      - set_llm(tok_per_sec, total_tokens, label)
      - set_rag_score(score, label)
      - set_traces(count, label)

    + Nouvelle API :
      - update_from_events() : draine EventBus et met à jour les widgets
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RightPanelDiagnostic")
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setObjectName("RightPanelHeader")
        header.setFixedHeight(34)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(6)

        title = QLabel("Diagnostic RAG")
        title.setStyleSheet(
            "font-size: 11px; color: #4A6A8A; letter-spacing: 0.06em;"
            " text-transform: uppercase; background: transparent;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        refresh_icon = QLabel("↻")
        refresh_icon.setStyleSheet(
            "font-size: 14px; color: #2D4052; background: transparent;"
        )
        header_layout.addWidget(refresh_icon)
        layout.addWidget(header)

        # ── Tab row ──
        self._tab_row = QWidget()
        self._tab_row.setFixedHeight(28)
        tab_layout = QHBoxLayout(self._tab_row)
        tab_layout.setContentsMargins(10, 6, 10, 0)
        tab_layout.setSpacing(2)

        self._tab_metrics = QLabel("Métriques")
        self._tab_metrics.setStyleSheet(
            "font-size: 10px; color: #2A7FBF; padding: 4px 10px;"
            " border-bottom: 1.5px solid #2A7FBF; background: transparent;"
        )
        tab_layout.addWidget(self._tab_metrics)

        self._tab_index = QLabel("Index")
        self._tab_index.setStyleSheet(
            "font-size: 10px; color: #3D5266; padding: 4px 10px;"
            " border-bottom: 1.5px solid transparent; background: transparent;"
        )
        tab_layout.addWidget(self._tab_index)

        self._tab_traces = QLabel("Traces")
        self._tab_traces.setStyleSheet(
            "font-size: 10px; color: #3D5266; padding: 4px 10px;"
            " border-bottom: 1.5px solid transparent; background: transparent;"
        )
        tab_layout.addWidget(self._tab_traces)

        tab_layout.addStretch()
        layout.addWidget(self._tab_row)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"color: {BORDER_COLOR}; background-color: {BORDER_COLOR}; border: none;")
        layout.addWidget(sep)

        # ── Contenu via RagTabWidget ──
        self._tab_widget = RagTabWidget()
        layout.addWidget(self._tab_widget, stretch=1)

        # État interne
        self._cloud_subtitle = "↑ Cloud actif"
        self._model_name = "phi-4-mini-4bit"
        self._ram_used = "0.0"
        self._ram_total = "0"
        self._ram_pct = 0.0
        self._rag_score = 0.0
        self._tok_s = 0.0
        self._total_tokens = 0
        self._traces_count = 0

    # ── API publique (compat MetricsPanel) ──

    def set_strategy(self, strategy: str, model: str = "") -> None:
        """Change la stratégie active affichée (compat MetricsPanel)."""
        if model:
            self._model_name = model

    def set_ram(self, percent: float, used_gb: str = "0", total_gb: str = "") -> None:
        """Met à jour la RAM (compat MetricsPanel)."""
        self._ram_pct = percent
        self._ram_used = used_gb
        self._ram_total = total_gb
        # Mettre à jour MetricsGrid
        self._tab_widget.metrics.metrics_grid.set_ram(used_gb, total_gb)
        # Mettre à jour RamBar
        self._tab_widget.metrics.ram_bar.set_ram(percent, used_gb, total_gb)

    def set_rag_score(self, score: float, label: str = "") -> None:
        """Met à jour le score RAG (compat MetricsPanel)."""
        self._rag_score = score
        self._tab_widget.metrics.rag_score_bar.set_score(score)

    def set_llm(self, tok_per_sec: float, total_tokens: int = 0, label: str = "") -> None:
        """Met à jour la métrique LLM / tokens (compat MetricsPanel)."""
        self._tok_s = tok_per_sec
        self._total_tokens = total_tokens
        subtitle = label or (f"↑ {self._cloud_subtitle}" if tok_per_sec > 0 else "↑ —")
        self._tab_widget.metrics.metrics_grid.set_tokens(tok_per_sec, subtitle)

    def set_traces(self, count: int, label: str = "") -> None:
        """Met à jour le nombre de traces (compat MetricsPanel)."""
        self._traces_count = count
        self._tab_widget.traces.set_traces(count)

    # ── Nouvelle API ──

    def update_from_diagnostics_viewmodel(self) -> None:
        """Met à jour depuis RAGDiagnosticViewModel (via signal updated).

        Le caller appelle ``viewmodel.updated.connect(self.update_from_diagnostics_viewmodel)``.
        """
        try:
            from src.ui.viewmodels.rag_diagnostic_vm import RAGDiagnosticViewModel

            # On utilise le sender pour récupérer le viewmodel
            sender = self.sender()
            if not isinstance(sender, RAGDiagnosticViewModel):
                logger.debug("update_from_diagnostics_viewmodel: sender not a RAGDiagnosticViewModel")
                return

            vm = sender
            score = vm.final_score
            label = vm.confidence_label
            strategies = vm.strategies
            chunks = vm.found_chunks
            fact_check = vm.fact_check_triggered

            # Score RAG
            self.set_rag_score(score, label)

            # Chunks
            self._tab_widget.metrics.metrics_grid.set_chunks(
                chunks // 2 if chunks > 1 else 0,
                0,
                chunks,
            )

            # Stratégies
            strategy_tuples = []
            for s in strategies:
                icon = "🔺" if "vectoriel" in s['name'].lower() else (
                    "📝" if "fts" in s['name'].lower() else (
                        "🔍" if "grep" in s['name'].lower() else (
                            "✨" if "hyde" in s['name'].lower() else "○"
                        )
                    )
                )
                score_str = str(s['top_score']) if s['hit'] else "skip"
                timing = f"{s['timing_ms']:.0f}ms" if s['timing_ms'] > 0 else "—"
                skipped = not s['hit']
                strategy_tuples.append((icon, s['name'], score_str, timing, skipped))
            if strategy_tuples:
                self._tab_widget.metrics.strategy_diag.set_strategies(strategy_tuples)

            # Verdict / Banner
            if hasattr(vm, 'verdict') and vm.verdict:
                self._tab_widget.metrics.retro_banner.set_info(vm.verdict)

        except ImportError as e:
            logger.debug("RAGDiagnosticViewModel non disponible: %s", e)
        except Exception as e:
            logger.debug("Erreur update_from_diagnostics_viewmodel: %s", e)

    def update_from_events(self) -> None:
        """Draine l'EventBus et met à jour les widgets du panneau droit."""
        try:
            from src.core.events import EventBus

            bus = EventBus()
            events = bus.drain()

            for event_type, data in events:
                if event_type == "rag_score":
                    score = data.get("score", 0.0) if isinstance(data, dict) else float(data or 0.0)
                    self.set_rag_score(score)
                    # Also update strategies if present
                    if isinstance(data, dict):
                        strategies = data.get("strategies", [])
                        if strategies:
                            self._tab_widget.metrics.strategy_diag.set_strategies(strategies)

                elif event_type == "generation_complete":
                    if isinstance(data, dict):
                        # Tokens
                        tok_s = data.get("tok_s", self._tok_s)
                        chunks = data.get("chunks", 0)
                        latence = data.get("latence", 0.0)
                        sub_queries = data.get("sub_queries", 0)

                        # Update metrics grid
                        self._tab_widget.metrics.metrics_grid.set_chunks(
                            data.get("chunks_high", 0),
                            data.get("chunks_med", 0),
                            chunks,
                        )
                        self._tab_widget.metrics.metrics_grid.set_latence(latence)

                        # Update retro banner
                        if sub_queries > 0:
                            final_strategy = data.get("final_strategy", "")
                            banner_text = (
                                f"Requête décomposée en {sub_queries} sous-requêtes · "
                                f"Query rewriting actif"
                            )
                            if final_strategy:
                                banner_text += f" · Stratégie finale : {final_strategy}"
                            self._tab_widget.metrics.retro_banner.set_info(banner_text)

                elif event_type == "verification_warning":
                    if isinstance(data, dict):
                        facts = data.get("facts", [])
                        if facts:
                            self._tab_widget.metrics.fact_check.set_facts(facts)

                elif event_type == "query.decomposed":
                    if isinstance(data, dict):
                        n = data.get("n", 0)
                        banner_text = (
                            f"Requête décomposée en {n} sous-requêtes · "
                            f"Query rewriting actif"
                        )
                        self._tab_widget.metrics.retro_banner.set_info(banner_text)

                elif event_type == "ram_update":
                    if isinstance(data, dict):
                        pct = data.get("percent", self._ram_pct)
                        used = data.get("used_gb", self._ram_used)
                        total = data.get("total_gb", self._ram_total)
                        self.set_ram(pct, used, total)

                elif event_type == "index_health":
                    if isinstance(data, dict):
                        self._tab_widget.metrics.index_health.set_docs(
                            data.get("indexed", 0), data.get("total", 0)
                        )
                        self._tab_widget.metrics.index_health.set_warnings(
                            data.get("warnings", "—")
                        )
                        self._tab_widget.metrics.index_health.set_last_scan(
                            data.get("last_scan", "—")
                        )

        except ImportError:
            logger.debug("EventBus non disponible — saut du drain")
        except Exception as e:
            logger.debug("Erreur drain EventBus: %s", e)


# ══════════════════════════════════════════════════════════════════════════
#  Test rapide
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    win = QMainWindow()
    win.setWindowTitle("RightPanelDiagnostic — Test")
    win.resize(400, 700)

    panel = RightPanelDiagnostic()
    panel.set_ram(34.0, "2.7", "8")
    panel.set_rag_score(0.81)
    panel.set_llm(147.0, 500, "↑ Groq actif")
    panel.set_traces(12)

    win.setCentralWidget(panel)
    win.show()

    sys.exit(app.exec())
