"""
NURU V10 — StatsPage : Statistiques temps réel, coûts et tendances.

Alimenté par PerformanceTracker (~/.nuru/performance.db) + psutil.
Affiche :
  - RAM système (utilisée/totale, warning/critical)
  - Métriques RAG (Recall@5, score moyen, empty rate)
  - Métriques réponse (temps, tokens, hallucination rate)
  - Métriques Agent (taux succès, steps, recovery)
  - Métriques Feedback (thumbs up/down, rating)
  - Tendances sur période configurable

Design cyberpunk NURU : bg #0D1117, accent #00A3FF, vert #39FF14.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import psutil

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Couleurs du thème ──────────────────────────────────────────────────────

BG_DARK = "#0D1117"
BG_PANEL = "#161b22"
ACCENT_BLUE = "#00A3FF"
ACCENT_GREEN = "#39FF14"
ACCENT_RED = "#FF3333"
ACCENT_ORANGE = "#FF8C00"
ACCENT_PURPLE = "#A78BFA"
ACCENT_PINK = "#FF00FF"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
BORDER_COLOR = "rgba(255,255,255,0.08)"

PANEL_STYLE = f"""
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
"""

CARD_STYLE = f"""
    background-color: rgba(0, 0, 0, 0.5);
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 10px;
"""

PERIOD_OPTIONS = {
    "1h": 1,
    "6h": 6,
    "24h": 24,
    "7j": 168,
    "30j": 720,
}


# ══════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════


def _pct_color(pct: float, good: float = 50, warn: float = 80) -> str:
    """Couleur selon un seuil : vert si < good, orange si < warn, rouge sinon."""
    if pct < good:
        return ACCENT_GREEN
    elif pct < warn:
        return ACCENT_ORANGE
    return ACCENT_RED


def _bool_color(val: float, ideal_high: bool = True) -> str:
    """Colorie une valeur entre 0 et 1."""
    if ideal_high:
        if val >= 0.8:
            return ACCENT_GREEN
        elif val >= 0.5:
            return ACCENT_ORANGE
        return ACCENT_RED
    else:
        if val <= 0.1:
            return ACCENT_GREEN
        elif val <= 0.3:
            return ACCENT_ORANGE
        return ACCENT_RED


def _format_ms(ms: float) -> str:
    """Formate des ms en secondes ou ms lisibles."""
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _format_pct(val: float) -> str:
    """Formate un ratio en pourcentage."""
    return f"{val * 100:.1f}%"


# ══════════════════════════════════════════════════════════════════════════
#  StatCard — carte métrique unique
# ══════════════════════════════════════════════════════════════════════════


class StatCard(QFrame):
    """Carte métrique compacte avec icône, label, valeur et couleur dynamique."""

    def __init__(
        self,
        title: str,
        icon: str = "◆",
        value: str = "—",
        color: str = ACCENT_BLUE,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setStyleSheet(f"""
            #StatCard {{
                {CARD_STYLE}
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.setSpacing(6)
        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setStyleSheet(f"color: {color}; font-size: 14px; background: transparent;")
        header.addWidget(self._icon_lbl)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 9px; font-weight: bold; "
            f"letter-spacing: 1px; background: transparent;"
        )
        header.addWidget(self._title_lbl)
        header.addStretch()
        layout.addLayout(header)

        # Valeur
        self._value_lbl = QLabel(value)
        self._val_color = color
        self._update_value_style()
        layout.addWidget(self._value_lbl)

    def set_value(self, value: str, color: str | None = None) -> None:
        """Met à jour la valeur affichée et optionnellement la couleur."""
        self._value_lbl.setText(value)
        if color is not None:
            self._val_color = color
            self._update_value_style()

    def _update_value_style(self) -> None:
        self._value_lbl.setStyleSheet(
            f"color: {self._val_color}; font-size: 22px; font-weight: bold; "
            f"background: transparent;"
        )


# ══════════════════════════════════════════════════════════════════════════
#  MetricProgress — barre de progression avec label
# ══════════════════════════════════════════════════════════════════════════


class MetricProgress(QWidget):
    """Barre de progression horizontale avec label à gauche et valeur à droite."""

    def __init__(self, label: str, max_val: float = 1.0, color: str = ACCENT_GREEN, parent=None):
        super().__init__(parent)
        self._max_val = max_val
        self._color = color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._label_w = QLabel(label)
        self._label_w.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        self._label_w.setFixedWidth(110)
        layout.addWidget(self._label_w)

        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(10)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(255,255,255,0.05);
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self._bar, stretch=1)

        self._value_w = QLabel("—")
        self._value_w.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 10px; background: transparent;")
        self._value_w.setFixedWidth(55)
        self._value_w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._value_w)

    def set_value(self, val: float, text: str | None = None) -> None:
        """Met à jour la barre et le texte."""
        if self._max_val > 0:
            clamped = min(max(val / self._max_val, 0.0), 1.0)
            self._bar.setValue(int(clamped * 1000))
        self._value_w.setText(text if text is not None else f"{val:.2f}")


# ══════════════════════════════════════════════════════════════════════════
#  SectionHeader
# ══════════════════════════════════════════════════════════════════════════


class SectionHeader(QWidget):
    """Titre de section avec ligne décorative."""

    def __init__(self, title: str, icon: str = "📊", color: str = ACCENT_BLUE, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 6)
        layout.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 18px; background: transparent;")
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold; background: transparent;")
        layout.addWidget(title_lbl)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {BORDER_COLOR}; max-height: 1px;")
        layout.addWidget(line, stretch=1)


# ══════════════════════════════════════════════════════════════════════════
#  StatsPage — page principale de statistiques
# ══════════════════════════════════════════════════════════════════════════


class StatsPage(QScrollArea):
    """Page de statistiques temps réel — RAM, RAG, Réponse, Agent, Feedback.

    Se connecte à PerformanceTracker et psutil pour afficher les métriques
    réelles du système NURU.

    Périodes : 1h, 6h, 24h, 7j, 30j.
    Rafraîchissement automatique toutes les 5s.
    """

    def __init__(self, parent: QWidget | None = None, tracker=None):
        super().__init__(parent)
        self.setObjectName("StatsPage")
        self.setWidgetResizable(True)
        self.setStyleSheet(f"background-color: {BG_DARK}; border: none;")

        # ── Backend PerformanceTracker ──
        self._tracker = tracker
        if self._tracker is None:
            try:
                from src.learning.tracker import PerformanceTracker
                self._tracker = PerformanceTracker()
                logger.info("StatsPage: PerformanceTracker initialisé")
            except Exception as e:
                logger.warning("StatsPage: PerformanceTracker non disponible: %s", e)

        self._period_hours = 24
        self._build_ui()

        # Timer de rafraîchissement
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(5000)

        # Premier rafraîchissement
        self.refresh()

    def _build_ui(self) -> None:
        """Construit toute l'interface."""
        container = QWidget()
        container.setStyleSheet(f"background-color: {BG_DARK};")
        self.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── En-tête ──
        header = QHBoxLayout()
        title = QLabel("📊 Statistiques NURU V10")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 22px; font-weight: bold; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        # Sélecteur de période
        period_lbl = QLabel("Période :")
        period_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        header.addWidget(period_lbl)

        self._period_combo = QComboBox()
        self._period_combo.addItems(list(PERIOD_OPTIONS.keys()))
        self._period_combo.setCurrentText("24h")
        self._period_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {BG_PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                min-width: 70px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {TEXT_SECONDARY};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {BG_PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                selection-background-color: rgba(0, 163, 255, 0.2);
            }}
        """)
        self._period_combo.currentTextChanged.connect(self._on_period_changed)
        header.addWidget(self._period_combo)

        layout.addLayout(header)

        # ── Grille de cartes principales (haute priorité) ──
        self._card_grid = QGridLayout()
        self._card_grid.setSpacing(10)

        # RAM
        self._ram_card = StatCard("RAM Utilisée", "🧠", "—", ACCENT_GREEN)
        self._card_grid.addWidget(self._ram_card, 0, 0)

        # RAG Recall@5
        self._rag_recall_card = StatCard("Recall@5 RAG", "🎯", "—", ACCENT_BLUE)
        self._card_grid.addWidget(self._rag_recall_card, 0, 1)

        # Taux hallucination
        self._hallu_card = StatCard("Hallucination", "⚠️", "—", ACCENT_RED)
        self._card_grid.addWidget(self._hallu_card, 0, 2)

        # Taux succès agent
        self._agent_card = StatCard("Succès Agent", "🤖", "—", ACCENT_PURPLE)
        self._card_grid.addWidget(self._agent_card, 0, 3)

        layout.addLayout(self._card_grid)

        # ── RAM détaillée ──
        layout.addWidget(SectionHeader("🧠 RAM Système", "🧠", ACCENT_GREEN))

        self._ram_panel = QFrame()
        self._ram_panel.setStyleSheet(PANEL_STYLE)
        ram_layout = QVBoxLayout(self._ram_panel)
        ram_layout.setContentsMargins(14, 10, 14, 10)
        ram_layout.setSpacing(6)

        self._ram_bar = MetricProgress("RAM", max_val=100.0, color=ACCENT_GREEN)
        ram_layout.addWidget(self._ram_bar)

        self._ram_status_lbl = QLabel("Statut : OK")
        self._ram_status_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        ram_layout.addWidget(self._ram_status_lbl)

        layout.addWidget(self._ram_panel)

        # ── Métriques RAG ──
        layout.addWidget(SectionHeader("🎯 RAG — Recherche Documentaire", "🎯", ACCENT_BLUE))

        self._rag_panel = QFrame()
        self._rag_panel.setStyleSheet(PANEL_STYLE)
        rag_layout = QVBoxLayout(self._rag_panel)
        rag_layout.setContentsMargins(14, 10, 14, 10)
        rag_layout.setSpacing(6)

        self._rag_recall_bar = MetricProgress("Recall@5", color=ACCENT_BLUE)
        rag_layout.addWidget(self._rag_recall_bar)

        self._rag_score_bar = MetricProgress("Score moyen", color=ACCENT_BLUE)
        rag_layout.addWidget(self._rag_score_bar)

        self._rag_empty_bar = MetricProgress("Taux vide (inverse)", color=ACCENT_BLUE)
        rag_layout.addWidget(self._rag_empty_bar)

        self._rag_hyde_bar = MetricProgress("HyDE trigger", color=ACCENT_PURPLE)
        rag_layout.addWidget(self._rag_hyde_bar)

        layout.addWidget(self._rag_panel)

        # ── Métriques Cache LLM (V10.2) ──
        layout.addWidget(SectionHeader("💾 Cache LLM — Multi-niveau (L1 RAM + L2 SQLite)", "💾", ACCENT_BLUE))

        self._cache_panel = QFrame()
        self._cache_panel.setStyleSheet(PANEL_STYLE)
        cache_layout = QVBoxLayout(self._cache_panel)
        cache_layout.setContentsMargins(14, 10, 14, 10)
        cache_layout.setSpacing(6)

        cache_grid = QGridLayout()
        cache_grid.setSpacing(12)

        self._cache_hit_card = StatCard("Hit Rate L1", "🎯", "—", ACCENT_GREEN)
        cache_grid.addWidget(self._cache_hit_card, 0, 0)

        self._cache_size_card = StatCard("L1 Size", "📦", "—", ACCENT_BLUE)
        cache_grid.addWidget(self._cache_size_card, 0, 1)

        self._cache_miss_card = StatCard("Miss L1", "❌", "—", ACCENT_RED)
        cache_grid.addWidget(self._cache_miss_card, 0, 2)

        self._cache_expired_card = StatCard("Expired TTL", "⏳", "—", ACCENT_ORANGE)
        cache_grid.addWidget(self._cache_expired_card, 0, 3)

        cache_layout.addLayout(cache_grid)
        layout.addWidget(self._cache_panel)

        # ── Métriques Réponse ──
        layout.addWidget(SectionHeader("⚡ Réponse — Génération", "⚡", ACCENT_ORANGE))

        self._resp_panel = QFrame()
        self._resp_panel.setStyleSheet(PANEL_STYLE)
        resp_layout = QVBoxLayout(self._resp_panel)
        resp_layout.setContentsMargins(14, 10, 14, 10)
        resp_layout.setSpacing(6)

        resp_grid = QGridLayout()
        resp_grid.setSpacing(12)

        self._resp_time_card = StatCard("Temps moyen", "⏱️", "—", ACCENT_ORANGE)
        resp_grid.addWidget(self._resp_time_card, 0, 0)

        self._resp_tokens_card = StatCard("Tokens/réponse", "📝", "—", ACCENT_ORANGE)
        resp_grid.addWidget(self._resp_tokens_card, 0, 1)

        self._resp_hallu_card = StatCard("Taux hallucination", "⚠️", "—", ACCENT_RED)
        resp_grid.addWidget(self._resp_hallu_card, 0, 2)

        self._resp_cite_card = StatCard("Taux citation", "📎", "—", ACCENT_GREEN)
        resp_grid.addWidget(self._resp_cite_card, 0, 3)

        resp_layout.addLayout(resp_grid)
        layout.addWidget(self._resp_panel)

        # ── Métriques Agent ──
        layout.addWidget(SectionHeader("🤖 Agent — Boucle d'exécution", "🤖", ACCENT_PURPLE))

        self._agent_panel = QFrame()
        self._agent_panel.setStyleSheet(PANEL_STYLE)
        agent_layout = QVBoxLayout(self._agent_panel)
        agent_layout.setContentsMargins(14, 10, 14, 10)
        agent_layout.setSpacing(6)

        self._agent_success_bar = MetricProgress("Taux succès", color=ACCENT_GREEN)
        agent_layout.addWidget(self._agent_success_bar)

        self._agent_steps_bar = MetricProgress("Étapes/tâche", max_val=10.0, color=ACCENT_BLUE)
        agent_layout.addWidget(self._agent_steps_bar)

        self._agent_recovery_bar = MetricProgress("Récupération erreur", color=ACCENT_ORANGE)
        agent_layout.addWidget(self._agent_recovery_bar)

        layout.addWidget(self._agent_panel)

        # ── Métriques Feedback ──
        layout.addWidget(SectionHeader("💬 Feedback — Retour utilisateur", "💬", ACCENT_PINK))

        self._fb_panel = QFrame()
        self._fb_panel.setStyleSheet(PANEL_STYLE)
        fb_layout = QVBoxLayout(self._fb_panel)
        fb_layout.setContentsMargins(14, 10, 14, 10)
        fb_layout.setSpacing(6)

        fb_grid = QGridLayout()
        fb_grid.setSpacing(12)

        self._fb_up_card = StatCard("👍 Thumbs Up", "👍", "—", ACCENT_GREEN)
        fb_grid.addWidget(self._fb_up_card, 0, 0)

        self._fb_down_card = StatCard("👎 Thumbs Down", "👎", "—", ACCENT_RED)
        fb_grid.addWidget(self._fb_down_card, 0, 1)

        self._fb_correction_card = StatCard("✏️ Corrections", "✏️", "—", ACCENT_ORANGE)
        fb_grid.addWidget(self._fb_correction_card, 0, 2)

        self._fb_rating_card = StatCard("⭐ Note moyenne", "⭐", "—", ACCENT_PURPLE)
        fb_grid.addWidget(self._fb_rating_card, 0, 3)

        fb_layout.addLayout(fb_grid)
        layout.addWidget(self._fb_panel)

        # ── Points de données ──
        self._footer_lbl = QLabel("")
        self._footer_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        self._footer_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(self._footer_lbl)

        layout.addStretch()

    def _on_period_changed(self, period_key: str) -> None:
        """Change la période d'affichage."""
        self._period_hours = PERIOD_OPTIONS.get(period_key, 24)
        self.refresh()

    def refresh(self) -> None:
        """Rafraîchit toutes les métriques depuis les backends."""
        self._update_ram()
        self._update_rag()
        self._update_cache()
        self._update_response()
        self._update_agent()
        self._update_feedback()

    def _update_ram(self) -> None:
        """Met à jour les métriques RAM."""
        try:
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            pct = mem.percent
            free_gb = mem.available / (1024**3)

            color = _pct_color(pct)
            self._ram_card.set_value(f"{used_gb:.1f} / {total_gb:.0f} Go", color)

            self._ram_bar.set_value(pct, f"{pct:.0f}%")

            # Statut RAM
            if free_gb < 1.0:
                status = "🔴 CRITIQUE"
                status_color = ACCENT_RED
            elif free_gb < 2.0:
                status = "🟡 ATTENTION"
                status_color = ACCENT_ORANGE
            else:
                status = "🟢 OK"
                status_color = ACCENT_GREEN
            self._ram_status_lbl.setStyleSheet(
                f"color: {status_color}; font-size: 10px; font-weight: bold; background: transparent;"
            )
            self._ram_status_lbl.setText(f"Statut : {status}  ({free_gb:.1f} Go libre)")
        except Exception as e:
            logger.debug("StatsPage RAM: %s", e)

    def _update_rag(self) -> None:
        """Met à jour les métriques RAG via PerformanceTracker."""
        if not self._tracker:
            return
        try:
            avgs = self._tracker.get_averages(category="rag", since_hours=self._period_hours)
            recall = avgs.get("rag_recall@5", 0.0)
            avg_score = avgs.get("rag_avg_score", 0.0)
            empty_rate = avgs.get("rag_empty", 0.0)
            hyde_rate = avgs.get("rag_hyde_trigger", 0.0)

            self._rag_recall_card.set_value(
                _format_pct(recall), _bool_color(recall))
            self._rag_recall_bar.set_value(recall, _format_pct(recall))

            self._rag_score_bar.set_value(avg_score, f"{avg_score:.2f}")
            self._rag_empty_bar.set_value(1.0 - empty_rate, _format_pct(1.0 - empty_rate))
            self._rag_hyde_bar.set_value(hyde_rate, _format_pct(hyde_rate))
        except Exception as e:
            logger.debug("StatsPage RAG: %s", e)

    def _update_cache(self) -> None:
        """Met à jour les métriques du cache LLM multi-niveau."""
        try:
            from src.cache.llm_cache import LLMCache
            from src.memory_store import MemoryStore

            ms = MemoryStore()
            cache = LLMCache(ms)
            stats = cache.get_stats()

            hr = stats["l1_hit_rate"]
            self._cache_hit_card.set_value(
                f"{hr * 100:.1f}%",
                ACCENT_GREEN if hr >= 0.7 else ACCENT_ORANGE if hr >= 0.4 else ACCENT_RED,
            )
            self._cache_size_card.set_value(
                f"{stats['l1_size']} / {stats['l1_maxsize']}",
                ACCENT_GREEN if stats['l1_size'] < stats['l1_maxsize'] * 0.8 else ACCENT_ORANGE,
            )
            self._cache_miss_card.set_value(
                str(stats["l1_misses"]), ACCENT_RED if stats["l1_misses"] > stats["l1_hits"] * 2 else ACCENT_ORANGE,
            )
            self._cache_expired_card.set_value(
                str(stats["l1_expired"]), ACCENT_ORANGE if stats["l1_expired"] > 10 else TEXT_SECONDARY,
            )
        except Exception as e:
            logger.debug("StatsPage Cache: %s", e)

    def _update_response(self) -> None:
        """Met à jour les métriques de réponse."""
        if not self._tracker:
            return
        try:
            avgs = self._tracker.get_averages(category="response", since_hours=self._period_hours)
            time_ms = avgs.get("response_time_ms", 0.0)
            tokens = avgs.get("response_tokens", 0.0)
            hallu = avgs.get("response_hallucination", 0.0)
            cite = avgs.get("response_citation", 0.0)

            self._resp_time_card.set_value(_format_ms(time_ms), _bool_color(time_ms / 10000, ideal_high=False))
            self._resp_tokens_card.set_value(f"{tokens:.0f}", ACCENT_ORANGE)
            self._resp_hallu_card.set_value(_format_pct(hallu), _bool_color(1.0 - hallu))
            self._resp_cite_card.set_value(_format_pct(cite), _bool_color(cite))
        except Exception as e:
            logger.debug("StatsPage Response: %s", e)

    def _update_agent(self) -> None:
        """Met à jour les métriques Agent."""
        if not self._tracker:
            return
        try:
            avgs = self._tracker.get_averages(category="agent", since_hours=self._period_hours)
            success = avgs.get("agent_task_success", 0.0)
            steps = avgs.get("agent_steps", 0.0)
            recovery = avgs.get("agent_recovery", 0.0)

            self._agent_card.set_value(_format_pct(success), _bool_color(success))
            self._agent_success_bar.set_value(success, _format_pct(success))
            self._agent_steps_bar.set_value(steps, f"{steps:.1f}")
            self._agent_recovery_bar.set_value(recovery, _format_pct(recovery))
        except Exception as e:
            logger.debug("StatsPage Agent: %s", e)

    def _update_feedback(self) -> None:
        """Met à jour les métriques Feedback."""
        if not self._tracker:
            return
        try:
            avgs = self._tracker.get_averages(category="feedback", since_hours=self._period_hours)
            up = avgs.get("feedback_thumbs_up", 0.0)
            down = avgs.get("feedback_thumbs_down", 0.0)
            correction = avgs.get("feedback_correction", 0.0)
            rating = avgs.get("feedback_rating", 0.0)

            self._fb_up_card.set_value(_format_pct(up), _bool_color(up))
            self._fb_down_card.set_value(_format_pct(down), _bool_color(1.0 - down, ideal_high=False))
            self._fb_correction_card.set_value(_format_pct(correction), _bool_color(1.0 - correction, ideal_high=False))
            self._fb_rating_card.set_value(
                f"{rating:.1f} / 5" if rating > 0 else "—",
                ACCENT_PURPLE if rating >= 3.5 else ACCENT_ORANGE if rating > 0 else TEXT_SECONDARY,
            )

            # Footer
            total = getattr(self._tracker, 'count', lambda: 0)()
            self._footer_lbl.setText(
                f"🧮 {total} points de données  •  Période : {self._period_hours}h"
            )
        except Exception as e:
            logger.debug("StatsPage Feedback: %s", e)

    def cleanup(self) -> None:
        """Arrête le timer de rafraîchissement proprement."""
        if self._refresh_timer and self._refresh_timer.isActive():
            self._refresh_timer.stop()
