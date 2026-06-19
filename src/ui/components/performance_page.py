"""
P1-E Fusion — PerformancePage fusionne StatsPage et DiagnosticsPage.

Une seule page QScrollArea avec :
  - Section 1 : Aperçu (4 StatCards horizontales)
  - Section 2 : Performance (métriques temps réel : RAM, RAG, Cache, Response, Agent)
  - Section 3 : Stratégies (bar chart depuis StrategiesChartWidget)
  - Section 4 : Documents populaires (TopDocsWidget)
  - Section 5 : Requêtes échouées (FailedQueriesWidget)

Style cyberpunk NURU : fond #0A0E14, cartes #121620.
Timer auto-refresh 5s.
API publique : refresh(), cleanup().
"""

from __future__ import annotations

import logging
from typing import Optional

import psutil

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.ui.components.stat_card import StatCard

# ── Widgets réutilisés depuis DiagnosticsPage ──
from src.ui.components.diagnostics_page import (
    FailedQueriesWidget,
    MOCK_FAILED_QUERIES,
    MOCK_OVERVIEW,
    MOCK_STRATEGIES,
    MOCK_TOP_DOCS,
    StrategiesChartWidget,
    TopDocsWidget,
)

logger = logging.getLogger(__name__)

# ── Couleurs du thème cyberpunk NURU ────────────────────────────────────

BG_DARK = "#0A0E14"
BG_PANEL = "#121620"
WAITING_DATA_COLOR = "#555555"
ACCENT_BLUE = "#00A3FF"
ACCENT_GREEN = "#39FF14"
ACCENT_RED = "#FF3333"
ACCENT_ORANGE = "#FF8C00"
ACCENT_PURPLE = "#A78BFA"
ACCENT_PINK = "#FF00FF"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
BORDER_COLOR = "rgba(255,255,255,0.08)"
BAR_BG = "#1A2332"
BAR_FILL = "#1A5F9A"

PANEL_STYLE = f"""
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
"""


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
#  PerformancePage — Page unique fusionnant Stats + Diagnostics
# ══════════════════════════════════════════════════════════════════════════


class PerformancePage(QScrollArea):
    """Page unique fusionnant StatsPage et DiagnosticsPage.

    Sections :
      1. Aperçu — 4 StatCards (Requêtes totales, Temps moyen, Taux succès, Sources indexées)
      2. Performance — métriques temps réel (RAM, RAG, Cache, Response, Agent)
      3. Stratégies — bar chart des stratégies utilisées (StrategiesChartWidget)
      4. Documents populaires — TopDocsWidget
      5. Requêtes échouées — FailedQueriesWidget

    Rafraîchissement automatique toutes les 5s.
    API publique : refresh(), cleanup().
    """

    def __init__(self, parent: QWidget | None = None, tracker=None):
        super().__init__(parent)
        self.setObjectName("PerformancePage")
        self.setWidgetResizable(True)
        self.setStyleSheet(f"background-color: {BG_DARK}; border: none;")

        # ── Backend PerformanceTracker ──
        self._tracker = tracker
        if self._tracker is None:
            try:
                from src.learning.tracker import PerformanceTracker
                self._tracker = PerformanceTracker()
                logger.info("PerformancePage: PerformanceTracker initialisé")
            except Exception as e:
                logger.warning("PerformancePage: PerformanceTracker non disponible: %s", e)

        self._tracker_has_data = False
        self._cache_instance = None

        self._build_ui()

        # Timer de rafraîchissement (5s comme StatsPage)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(5000)

        # Premier rafraîchissement
        self.refresh()

    # ──────────────────────────────────────────────────────────────────────
    #  UI Construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Construit toute l'interface avec les 5 sections."""
        container = QWidget()
        container.setStyleSheet(f"background-color: {BG_DARK};")
        self.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── En-tête ──
        header_lbl = QLabel("⚡ Performance & Diagnostics")
        header_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 22px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(header_lbl)

        # ═══════════════════════════════════════════════════════════════════
        #  SECTION 1 — Aperçu (Overview top row, 4 StatCards)
        # ═══════════════════════════════════════════════════════════════════
        layout.addWidget(SectionHeader("📊 Aperçu général", "📊", ACCENT_BLUE))

        self._overview_grid = QGridLayout()
        self._overview_grid.setSpacing(10)

        self._total_queries_card = StatCard("Requêtes totales", "🔍", "—", ACCENT_BLUE)
        self._overview_grid.addWidget(self._total_queries_card, 0, 0)

        self._avg_time_card = StatCard("Temps moyen", "⏱️", "—", ACCENT_ORANGE)
        self._overview_grid.addWidget(self._avg_time_card, 0, 1)

        self._success_rate_card = StatCard("Taux succès", "✅", "—", ACCENT_GREEN)
        self._overview_grid.addWidget(self._success_rate_card, 0, 2)

        self._indexed_sources_card = StatCard("Sources indexées", "📚", "—", ACCENT_PURPLE)
        self._overview_grid.addWidget(self._indexed_sources_card, 0, 3)

        layout.addLayout(self._overview_grid)

        # ═══════════════════════════════════════════════════════════════════
        #  SECTION 2 — Performance (métriques temps réel)
        # ═══════════════════════════════════════════════════════════════════
        layout.addWidget(SectionHeader("🧠 Performance — Métriques temps réel", "🧠", ACCENT_GREEN))

        # -- RAM --
        self._ram_panel = QFrame()
        self._ram_panel.setStyleSheet(PANEL_STYLE)
        ram_layout = QVBoxLayout(self._ram_panel)
        ram_layout.setContentsMargins(14, 10, 14, 10)
        ram_layout.setSpacing(6)

        ram_title = QLabel("🧠 RAM Système")
        ram_title.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 11px; font-weight: bold; background: transparent;")
        ram_layout.addWidget(ram_title)

        self._ram_bar = MetricProgress("RAM", max_val=100.0, color=ACCENT_GREEN)
        ram_layout.addWidget(self._ram_bar)

        self._ram_status_lbl = QLabel("Statut : OK")
        self._ram_status_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        ram_layout.addWidget(self._ram_status_lbl)

        layout.addWidget(self._ram_panel)

        # -- RAG --
        self._rag_panel = QFrame()
        self._rag_panel.setStyleSheet(PANEL_STYLE)
        rag_layout = QVBoxLayout(self._rag_panel)
        rag_layout.setContentsMargins(14, 10, 14, 10)
        rag_layout.setSpacing(6)

        rag_title = QLabel("🎯 RAG — Recherche Documentaire")
        rag_title.setStyleSheet(f"color: {ACCENT_BLUE}; font-size: 11px; font-weight: bold; background: transparent;")
        rag_layout.addWidget(rag_title)

        self._rag_recall_bar = MetricProgress("Recall@5", color=ACCENT_BLUE)
        rag_layout.addWidget(self._rag_recall_bar)

        self._rag_score_bar = MetricProgress("Score moyen", color=ACCENT_BLUE)
        rag_layout.addWidget(self._rag_score_bar)

        self._rag_empty_bar = MetricProgress("Taux vide (inverse)", color=ACCENT_BLUE)
        rag_layout.addWidget(self._rag_empty_bar)

        self._rag_hyde_bar = MetricProgress("HyDE trigger", color=ACCENT_PURPLE)
        rag_layout.addWidget(self._rag_hyde_bar)

        layout.addWidget(self._rag_panel)

        # -- Cache --
        self._cache_panel = QFrame()
        self._cache_panel.setStyleSheet(PANEL_STYLE)
        cache_layout = QVBoxLayout(self._cache_panel)
        cache_layout.setContentsMargins(14, 10, 14, 10)
        cache_layout.setSpacing(6)

        cache_title = QLabel("💾 Cache LLM — Multi-niveau")
        cache_title.setStyleSheet(f"color: {ACCENT_BLUE}; font-size: 11px; font-weight: bold; background: transparent;")
        cache_layout.addWidget(cache_title)

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

        # -- Response --
        self._resp_panel = QFrame()
        self._resp_panel.setStyleSheet(PANEL_STYLE)
        resp_layout = QVBoxLayout(self._resp_panel)
        resp_layout.setContentsMargins(14, 10, 14, 10)
        resp_layout.setSpacing(6)

        resp_title = QLabel("⚡ Réponse — Génération")
        resp_title.setStyleSheet(f"color: {ACCENT_ORANGE}; font-size: 11px; font-weight: bold; background: transparent;")
        resp_layout.addWidget(resp_title)

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

        # -- Agent --
        self._agent_panel = QFrame()
        self._agent_panel.setStyleSheet(PANEL_STYLE)
        agent_layout = QVBoxLayout(self._agent_panel)
        agent_layout.setContentsMargins(14, 10, 14, 10)
        agent_layout.setSpacing(6)

        agent_title = QLabel("🤖 Agent — Boucle d'exécution")
        agent_title.setStyleSheet(f"color: {ACCENT_PURPLE}; font-size: 11px; font-weight: bold; background: transparent;")
        agent_layout.addWidget(agent_title)

        self._agent_success_bar = MetricProgress("Taux succès", color=ACCENT_GREEN)
        agent_layout.addWidget(self._agent_success_bar)

        self._agent_steps_bar = MetricProgress("Étapes/tâche", max_val=10.0, color=ACCENT_BLUE)
        agent_layout.addWidget(self._agent_steps_bar)

        self._agent_recovery_bar = MetricProgress("Récupération erreur", color=ACCENT_ORANGE)
        agent_layout.addWidget(self._agent_recovery_bar)

        layout.addWidget(self._agent_panel)

        # ═══════════════════════════════════════════════════════════════════
        #  SECTION 3 — Stratégies (StrategiesChartWidget)
        # ═══════════════════════════════════════════════════════════════════
        layout.addWidget(SectionHeader("📈 Stratégies les plus utilisées", "📈", ACCENT_GREEN))

        self._strategies_chart = StrategiesChartWidget()
        self._strategies_chart.set_mock()
        layout.addWidget(self._strategies_chart)

        # ═══════════════════════════════════════════════════════════════════
        #  SECTION 4+5 — Documents populaires + Requêtes échouées (côte à côte)
        # ═══════════════════════════════════════════════════════════════════
        row = QHBoxLayout()
        row.setSpacing(12)

        self._top_docs = TopDocsWidget()
        self._top_docs.set_mock()
        row.addWidget(self._top_docs, stretch=1)

        self._failed_queries = FailedQueriesWidget()
        self._failed_queries.set_mock()
        row.addWidget(self._failed_queries, stretch=1)

        layout.addLayout(row)

        # ── Footer ──
        self._footer_lbl = QLabel("")
        self._footer_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        self._footer_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(self._footer_lbl)

        layout.addStretch()

    # ──────────────────────────────────────────────────────────────────────
    #  Rafraîchissement complet
    # ──────────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Rafraîchit toutes les sections : performance + diagnostics."""
        self._check_tracker_data()

        # Toujours mettre à jour la RAM (indépendante du tracker)
        self._update_ram()

        if self._tracker is not None and self._tracker_has_data:
            # Performance via tracker
            self._update_tracker_metrics()
        else:
            # Afficher un état d'attente
            self._show_pending_state()

        # Mise à jour des sections diagnostics (toujours avec mock pour l'instant)
        self._update_diagnostics_overview()

    def cleanup(self) -> None:
        """Arrête le timer de rafraîchissement proprement."""
        if self._refresh_timer and self._refresh_timer.isActive():
            self._refresh_timer.stop()

    # ──────────────────────────────────────────────────────────────────────
    #  Internes — Performance
    # ──────────────────────────────────────────────────────────────────────

    def _check_tracker_data(self) -> None:
        """Vérifie si le PerformanceTracker contient des données réelles."""
        if self._tracker is None:
            self._tracker_has_data = False
            return
        try:
            count = getattr(self._tracker, 'count', lambda: 0)()
            self._tracker_has_data = count > 0
        except Exception:
            self._tracker_has_data = False

    def _show_pending_state(self) -> None:
        """Affiche un état 'En attente de données' sur les métriques perf."""
        waiting_value = "⏳ En attente..."
        self._avg_time_card.set_value(waiting_value, WAITING_DATA_COLOR)
        self._success_rate_card.set_value(waiting_value, WAITING_DATA_COLOR)
        self._indexed_sources_card.set_value(waiting_value, WAITING_DATA_COLOR)

        self._resp_time_card.set_value(waiting_value, WAITING_DATA_COLOR)
        self._resp_tokens_card.set_value(waiting_value, WAITING_DATA_COLOR)
        self._resp_hallu_card.set_value(waiting_value, WAITING_DATA_COLOR)
        self._resp_cite_card.set_value(waiting_value, WAITING_DATA_COLOR)

        self._rag_recall_bar.set_value(0, "—")
        self._rag_score_bar.set_value(0, "—")
        self._rag_empty_bar.set_value(0, "—")
        self._rag_hyde_bar.set_value(0, "—")

        self._agent_success_bar.set_value(0, "—")
        self._agent_steps_bar.set_value(0, "—")
        self._agent_recovery_bar.set_value(0, "—")

        # Cache : tentative de mise à jour même en mode pending
        self._update_cache()

    def _update_ram(self) -> None:
        """Met à jour les métriques RAM."""
        try:
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            pct = mem.percent
            free_gb = mem.available / (1024**3)

            color = _pct_color(pct)
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
            self._ram_status_lbl.setText(
                f"Statut : {status}  ({used_gb:.1f} / {total_gb:.0f} Go, {free_gb:.1f} Go libre)"
            )
        except Exception as e:
            logger.debug("PerformancePage RAM: %s", e)

    def _update_tracker_metrics(self) -> None:
        """Met à jour les métriques depuis PerformanceTracker (RAG, Cache, Response, Agent)."""
        self._update_rag()
        self._update_cache()
        self._update_response()
        self._update_agent()

        # Mettre à jour les StatCards d'aperçu
        self._update_overview_cards()

    def _update_rag(self) -> None:
        """Met à jour les métriques RAG via PerformanceTracker."""
        if not self._tracker or not self._tracker_has_data:
            return
        try:
            from src.ui.components.stats_page import PERIOD_OPTIONS
            period_hours = 24
            avgs = self._tracker.get_averages(category="rag", since_hours=period_hours)
            recall = avgs.get("rag_recall@5", None)
            avg_score = avgs.get("rag_avg_score", None)
            empty_rate = avgs.get("rag_empty", None)
            hyde_rate = avgs.get("rag_hyde_trigger", None)

            if recall is not None:
                self._rag_recall_bar.set_value(recall, _format_pct(recall))
            if avg_score is not None:
                self._rag_score_bar.set_value(avg_score, f"{avg_score:.2f}")
            if empty_rate is not None:
                self._rag_empty_bar.set_value(1.0 - empty_rate, _format_pct(1.0 - empty_rate))
            if hyde_rate is not None:
                self._rag_hyde_bar.set_value(hyde_rate, _format_pct(hyde_rate))
        except Exception as e:
            logger.debug("PerformancePage RAG: %s", e)

    def _update_cache(self) -> None:
        """Met à jour les métriques du cache LLM multi-niveau."""
        try:
            stats = None
            if self._cache_instance is not None:
                stats = self._cache_instance.get_stats()
            else:
                try:
                    from src.cache.llm_cache import LLMCache
                    from src.memory_store import MemoryStore
                    ms = MemoryStore()
                    self._cache_instance = LLMCache(ms)
                    stats = self._cache_instance.get_stats()
                    logger.info("PerformancePage: LLMCache instance créée")
                except ImportError:
                    logger.debug("PerformancePage: LLMCache/MemoryStore non disponible")
                except Exception as e:
                    logger.debug("PerformancePage: LLMCache init error: %s", e)

            if stats is None:
                try:
                    from src.memory_store import MemoryStore
                    ms = MemoryStore()
                    stats = ms.get_cache_stats()
                except ImportError:
                    logger.debug("PerformancePage: MemoryStore non disponible")
                except Exception as e:
                    logger.debug("PerformancePage: MemoryStore cache stats error: %s", e)

            if stats and any(v not in (None, 0, 0.0) for k, v in stats.items() if isinstance(v, (int, float))):
                hr = stats.get("l1_hit_rate", 0.0)
                self._cache_hit_card.set_value(
                    f"{hr * 100:.1f}%" if "l1_hit_rate" in stats else "—",
                    ACCENT_GREEN if hr >= 0.7 else ACCENT_ORANGE if hr >= 0.4 else ACCENT_RED,
                )
                l1_size = stats.get("l1_size", None)
                l1_maxsize = stats.get("l1_maxsize", None)
                if l1_size is not None and l1_maxsize is not None:
                    self._cache_size_card.set_value(
                        f"{l1_size} / {l1_maxsize}",
                        ACCENT_GREEN if l1_size < l1_maxsize * 0.8 else ACCENT_ORANGE,
                    )
                else:
                    total = stats.get("total_entries", 0)
                    self._cache_size_card.set_value(str(total), ACCENT_BLUE)
                misses = stats.get("l1_misses", None)
                if misses is not None:
                    hits = stats.get("l1_hits", 0)
                    self._cache_miss_card.set_value(
                        str(misses), ACCENT_RED if misses > hits * 2 else ACCENT_ORANGE,
                    )
                expired = stats.get("l1_expired", None)
                if expired is not None:
                    self._cache_expired_card.set_value(
                        str(expired), ACCENT_ORANGE if expired > 10 else TEXT_SECONDARY,
                    )
            elif stats:
                self._cache_hit_card.set_value("0.0%", TEXT_SECONDARY)
                self._cache_size_card.set_value("0", TEXT_SECONDARY)
                self._cache_miss_card.set_value("0", TEXT_SECONDARY)
                self._cache_expired_card.set_value("0", TEXT_SECONDARY)
            else:
                no_cache_msg = "⏳ Non disponible"
                self._cache_hit_card.set_value(no_cache_msg, WAITING_DATA_COLOR)
                self._cache_size_card.set_value(no_cache_msg, WAITING_DATA_COLOR)
                self._cache_miss_card.set_value(no_cache_msg, WAITING_DATA_COLOR)
                self._cache_expired_card.set_value(no_cache_msg, WAITING_DATA_COLOR)
        except Exception as e:
            logger.debug("PerformancePage Cache: %s", e)

    def _update_response(self) -> None:
        """Met à jour les métriques de réponse."""
        if not self._tracker or not self._tracker_has_data:
            return
        try:
            from src.ui.components.stats_page import PERIOD_OPTIONS
            period_hours = 24
            avgs = self._tracker.get_averages(category="response", since_hours=period_hours)
            time_ms = avgs.get("response_time_ms", None)
            tokens = avgs.get("response_tokens", None)
            hallu = avgs.get("response_hallucination", None)
            cite = avgs.get("response_citation", None)

            if time_ms is not None:
                self._resp_time_card.set_value(_format_ms(time_ms), _bool_color(time_ms / 10000, ideal_high=False))
            if tokens is not None:
                self._resp_tokens_card.set_value(f"{tokens:.0f}", ACCENT_ORANGE)
            if hallu is not None:
                self._resp_hallu_card.set_value(_format_pct(hallu), _bool_color(1.0 - hallu))
            if cite is not None:
                self._resp_cite_card.set_value(_format_pct(cite), _bool_color(cite))
        except Exception as e:
            logger.debug("PerformancePage Response: %s", e)

    def _update_agent(self) -> None:
        """Met à jour les métriques Agent."""
        if not self._tracker or not self._tracker_has_data:
            return
        try:
            from src.ui.components.stats_page import PERIOD_OPTIONS
            period_hours = 24
            avgs = self._tracker.get_averages(category="agent", since_hours=period_hours)
            success = avgs.get("agent_task_success", None)
            steps = avgs.get("agent_steps", None)
            recovery = avgs.get("agent_recovery", None)

            if success is not None:
                self._agent_success_bar.set_value(success, _format_pct(success))
            if steps is not None:
                self._agent_steps_bar.set_value(steps, f"{steps:.1f}")
            if recovery is not None:
                self._agent_recovery_bar.set_value(recovery, _format_pct(recovery))
        except Exception as e:
            logger.debug("PerformancePage Agent: %s", e)

    def _update_overview_cards(self) -> None:
        """Met à jour les 4 StatCards d'aperçu avec les données du tracker."""
        if not self._tracker or not self._tracker_has_data:
            return
        try:
            from src.ui.components.stats_page import PERIOD_OPTIONS
            period_hours = 24
            total = getattr(self._tracker, 'count', lambda: 0)()

            # Total queries
            self._total_queries_card.set_value(str(total), ACCENT_BLUE)

            # Avg response time
            resp_avgs = self._tracker.get_averages(category="response", since_hours=period_hours)
            time_ms = resp_avgs.get("response_time_ms", None)
            if time_ms is not None:
                self._avg_time_card.set_value(_format_ms(time_ms), ACCENT_ORANGE)

            # Success rate (agent success)
            agent_avgs = self._tracker.get_averages(category="agent", since_hours=period_hours)
            success = agent_avgs.get("agent_task_success", None)
            if success is not None:
                self._success_rate_card.set_value(
                    _format_pct(success), _bool_color(success)
                )

            # Indexed sources (RAG estimate)
            try:
                import os
                from pathlib import Path
                nuru_dir = Path.home() / ".nuru"
                index_count = 0
                if nuru_dir.exists():
                    index_count = len(list(nuru_dir.glob("*.db")))
                self._indexed_sources_card.set_value(
                    f"{index_count}", ACCENT_PURPLE
                )
            except Exception:
                self._indexed_sources_card.set_value("—", TEXT_SECONDARY)

            # Footer
            self._footer_lbl.setText(f"🧮 {total} points de données  •  Période : 24h")
        except Exception as e:
            logger.debug("PerformancePage overview cards: %s", e)

    def _update_diagnostics_overview(self) -> None:
        """Met à jour les sections diagnostics (mock pour l'instant)."""
        # Stratégies — déjà chargées avec set_mock dans _build_ui
        try:
            # Tentative de lecture depuis TraceCollector
            from src.learning.trace_collector import TraceCollector
            import os
            import sqlite3

            tc = TraceCollector()
            if os.path.exists(tc.db_path):
                conn = sqlite3.connect(tc.db_path)
                cursor = conn.cursor()

                # Total queries pour la StatCard d'aperçu
                cursor.execute("SELECT COUNT(*) FROM traces")
                total = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM traces WHERE confidence > 0.5")
                high_conf = cursor.fetchone()[0]
                success_rate = int(high_conf / total * 100) if total > 0 else 0

                self._total_queries_card.set_value(str(total), ACCENT_BLUE)
                self._success_rate_card.set_value(f"{success_rate}%", ACCENT_GREEN)

                # Requêtes échouées
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
            logger.debug("PerformancePage diagnostics refresh: %s", e)
