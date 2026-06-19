"""
V11.2 — KpiDashboardPage : page d'accueil KPI pour NURU dashboard.

QScrollArea affichant 9 cartes KPI en grille 2 colonnes,
une barre de statut système, et une section d'activité récente.

Style cyberpunk sombre cohérent avec le reste du dashboard NURU.

API publique
------------
- set_memory_store(store)  : injecte le MemoryStore
- set_rag_engine(engine)   : injecte le RAGEngine
- refresh()                : met à jour toutes les métriques manuellement
- cleanup()                : arrête le timer (appelé par le parent)
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.ui.components.stat_card import StatCard

logger = logging.getLogger(__name__)

# ── Couleurs du thème cyberpunk NURU (copiées de performance_page.py) ──────

BG_DARK = "#0A0E14"
BG_PANEL = "#121620"
BORDER_COLOR = "rgba(255,255,255,0.08)"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
ACCENT_BLUE = "#00A3FF"
ACCENT_GREEN = "#39FF14"
ACCENT_RED = "#FF3333"
ACCENT_ORANGE = "#FF8C00"
ACCENT_PURPLE = "#A78BFA"
ACCENT_PINK = "#FF00FF"
ACCENT_CYAN = "#00E5FF"
WAITING_DATA = "#555555"

PANEL_STYLE = f"""
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
"""

# ── Statut système ─────────────────────────────────────────────────────────


def _status_dot(status: str) -> str:
    """Dot coloré pour le statut système."""
    return {
        "online": "🟢",
        "warning": "🟡",
        "offline": "🔴",
    }.get(status, "⚪")


def _format_delta(td: datetime.timedelta | None) -> str:
    """Formate un timedelta en chaîne 'il y a X minutes'."""
    if td is None:
        return "—"
    total_secs = int(td.total_seconds())
    if total_secs < 60:
        return f"il y a {total_secs}s"
    mins = total_secs // 60
    if mins < 60:
        return f"il y a {mins}min"
    hours = mins // 60
    mins_rem = mins % 60
    if hours < 24:
        return f"il y a {hours}h{mins_rem}"
    days = hours // 24
    return f"il y a {days}j"


def _format_count(val: int | None) -> str:
    """Formate un grand nombre (ex: 15234 → '15.2k')."""
    if val is None:
        return "—"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}k"
    return str(val)


def _format_ms(ms: float | None) -> str:
    """Formate des ms en secondes ou ms lisibles."""
    if ms is None:
        return "—"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _format_pct(val: float | None) -> str:
    """Formate un ratio en pourcentage."""
    if val is None:
        return "—"
    return f"{val * 100:.1f}%"


# ══════════════════════════════════════════════════════════════════════════
#  SectionHeader — Titre de section avec ligne décorative
# ══════════════════════════════════════════════════════════════════════════


class _SectionHeader(QWidget):
    """Titre de section avec icône et ligne décorative."""

    def __init__(self, title: str, icon: str = "📊", color: str = ACCENT_BLUE, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 16px; background: transparent;")
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title_lbl)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {BORDER_COLOR}; max-height: 1px;")
        layout.addWidget(line, stretch=1)


# ══════════════════════════════════════════════════════════════════════════
#  ActivityWidget — Widget de ligne d'activité récente
# ══════════════════════════════════════════════════════════════════════════


class _ActivityItem(QFrame):
    """Une ligne dans la liste d'activité récente."""

    def __init__(self, icon: str, text: str, time_str: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ActivityItem")
        self.setStyleSheet(f"""
            #ActivityItem {{
                background: transparent;
                border: none;
                border-bottom: 1px solid {BORDER_COLOR};
                padding: 6px 0px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 13px; background: transparent;")
        icon_lbl.setFixedWidth(20)
        layout.addWidget(icon_lbl)

        text_lbl = QLabel(text)
        text_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 11px; background: transparent;"
        )
        text_lbl.setWordWrap(True)
        layout.addWidget(text_lbl, stretch=1)

        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 9px; background: transparent;"
        )
        time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        time_lbl.setFixedWidth(80)
        layout.addWidget(time_lbl)

    def set_data(self, icon: str, text: str, time_str: str) -> None:
        """Met à jour les données affichées."""
        self.findChildren(QLabel)[0].setText(icon)
        self.findChildren(QLabel)[1].setText(text)
        self.findChildren(QLabel)[2].setText(time_str)


# ══════════════════════════════════════════════════════════════════════════
#  KpiDashboardPage — Page d'accueil KPI
# ══════════════════════════════════════════════════════════════════════════


class KpiDashboardPage(QScrollArea):
    """Page d'accueil KPI avec 9 cartes métriques et activité récente.

    Paramètres
    ----------
    parent : QWidget, optional
    memory_store : MemoryStore, optional
        Injecté par le dashboard via set_memory_store().
    rag_engine : RAGEngine, optional
        Injecté par le dashboard via set_rag_engine().

    API publique
    ------------
    set_memory_store(store)  — injecte le MemoryStore
    set_rag_engine(engine)   — injecte le RAGEngine
    refresh()                — met à jour manuellement les métriques
    cleanup()                — arrête le timer (appelé par le parent)
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("KpiDashboardPage")
        self.setWidgetResizable(True)
        self.setStyleSheet(f"background-color: {BG_DARK}; border: none;")

        # ── Backend stores (injectés par le dashboard) ──
        self._memory_store = None
        self._rag_engine = None

        # ── Dernière activité — timestamp mock ──
        self._last_activity_time = None

        self._build_ui()

        # Timer de rafraîchissement automatique (5s)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(5000)

        # Premier rafraîchissement
        self.refresh()

    # ──────────────────────────────────────────────────────────────────────
    #  UI Construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Construit toute l'interface."""
        container = QWidget()
        container.setStyleSheet(f"background-color: {BG_DARK};")
        self.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── 1. Barre de statut en haut ──
        self._status_bar = QFrame()
        self._status_bar.setObjectName("StatusBar")
        self._status_bar.setStyleSheet(f"""
            #StatusBar {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        status_layout = QHBoxLayout(self._status_bar)
        status_layout.setContentsMargins(14, 10, 14, 10)
        status_layout.setSpacing(8)

        self._status_dot = QLabel("🟢")
        self._status_dot.setStyleSheet("font-size: 16px; background: transparent;")
        status_layout.addWidget(self._status_dot)

        self._status_text = QLabel("NURU V11.2 — Groq llama-3.3-70b")
        self._status_text.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent;"
        )
        status_layout.addWidget(self._status_text, stretch=1)

        self._status_sub = QLabel("Système opérationnel")
        self._status_sub.setStyleSheet(
            f"color: {ACCENT_GREEN}; font-size: 10px; background: transparent;"
        )
        status_layout.addWidget(self._status_sub)

        layout.addWidget(self._status_bar)

        # ── 2. Titre de page ──
        header_lbl = QLabel("🏠 Tableau de bord KPI")
        header_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(header_lbl)

        # ── 3. Grille KPI (2 colonnes, 5 lignes — 9 cartes) ──
        layout.addWidget(_SectionHeader("📊 Métriques clés", "📊", ACCENT_BLUE))

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(10)

        # Définition des 9 cartes KPI
        # (attribut, titre, icône, couleur défaut)
        kpi_specs = [
            ("_card_queries", "Requêtes aujourd'hui", "🔍", ACCENT_BLUE),
            ("_card_tokens", "Tokens consommés", "⚡", ACCENT_ORANGE),
            ("_card_response_time", "Temps réponse moyen", "⏱️", ACCENT_PURPLE),
            ("_card_success_rate", "Taux de succès", "✅", ACCENT_GREEN),
            ("_card_memory_facts", "Faits mémoire", "🧠", ACCENT_CYAN),
            ("_card_system_status", "Statut système", "🖥️", ACCENT_GREEN),
            ("_card_last_activity", "Dernière activité", "🕐", TEXT_SECONDARY),
            ("_card_cache_rag", "Cache RAG (hit rate)", "💾", ACCENT_PINK),
            ("_card_active_strategy", "Stratégie active", "🎯", ACCENT_GREEN),
        ]

        self._kpi_cards: dict[str, StatCard] = {}
        for idx, (attr, title, icon, color) in enumerate(kpi_specs):
            card = StatCard(title=title, icon=icon, value="—", color=color)
            setattr(self, attr, card)
            self._kpi_cards[attr] = card
            row = idx // 2
            col = idx % 2
            kpi_grid.addWidget(card, row, col)

        # Si nombre impair, ajouter un stretch à la dernière case
        if len(kpi_specs) % 2 != 0:
            kpi_grid.addWidget(QWidget(), len(kpi_specs) // 2, 1)

        layout.addLayout(kpi_grid)

        # ── 4. Section Activité récente ──
        layout.addWidget(_SectionHeader("🕐 Activité récente", "🕐", ACCENT_CYAN))

        self._activity_panel = QFrame()
        self._activity_panel.setStyleSheet(PANEL_STYLE)
        activity_layout = QVBoxLayout(self._activity_panel)
        activity_layout.setContentsMargins(14, 10, 14, 10)
        activity_layout.setSpacing(0)

        # Sous-titre
        activity_sub = QLabel("Les 10 dernières interactions")
        activity_sub.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;"
        )
        activity_layout.addWidget(activity_sub)

        # Conteneur scrollable pour la liste d'activités
        self._activity_scroll = QScrollArea()
        self._activity_scroll.setWidgetResizable(True)
        self._activity_scroll.setStyleSheet(
            f"background: transparent; border: none;"
        )
        self._activity_scroll.setFixedHeight(220)

        activity_container = QWidget()
        activity_container.setStyleSheet("background: transparent;")
        self._activity_list_layout = QVBoxLayout(activity_container)
        self._activity_list_layout.setContentsMargins(0, 4, 0, 4)
        self._activity_list_layout.setSpacing(0)

        # Créer 10 lignes d'activité
        self._activity_items: list[_ActivityItem] = []
        for _ in range(10):
            item = _ActivityItem("💬", "—", "—")
            self._activity_items.append(item)
            self._activity_list_layout.addWidget(item)

        self._activity_list_layout.addStretch()
        self._activity_scroll.setWidget(activity_container)
        activity_layout.addWidget(self._activity_scroll)

        layout.addWidget(self._activity_panel)

        # ── 5. Espacement final ──
        layout.addStretch()

    # ──────────────────────────────────────────────────────────────────────
    #  API publique
    # ──────────────────────────────────────────────────────────────────────

    def set_memory_store(self, store) -> None:
        """Injecte le MemoryStore.

        Paramètres
        ----------
        store : MemoryStore ou None
        """
        self._memory_store = store
        logger.debug("KpiDashboardPage: memory_store injecté")
        self.refresh()

    def set_rag_engine(self, engine) -> None:
        """Injecte le RAGEngine.

        Paramètres
        ----------
        engine : RAGEngine ou None
        """
        self._rag_engine = engine
        logger.debug("KpiDashboardPage: rag_engine injecté")
        self.refresh()

    def refresh(self) -> None:
        """Met à jour toutes les métriques et l'activité récente.

        Appelé automatiquement par le timer interne (5s).
        Peut être appelé manuellement.
        """
        try:
            self._refresh_kpis()
            self._refresh_activity()
            self._refresh_status()
        except Exception as e:
            logger.warning("KpiDashboardPage.refresh: %s", e)

    def cleanup(self) -> None:
        """Arrête le timer. Appelé quand la page est détruite."""
        try:
            self._refresh_timer.stop()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────
    #  Internes
    # ──────────────────────────────────────────────────────────────────────

    def _refresh_kpis(self) -> None:
        """Met à jour les 9 cartes KPI avec les données disponibles."""
        # ── 1. Requêtes aujourd'hui ──
        queries_count = None
        try:
            if self._rag_engine is not None:
                if hasattr(self._rag_engine, "query_count"):
                    queries_count = self._rag_engine.query_count
                elif hasattr(self._rag_engine, "get_query_count"):
                    queries_count = self._rag_engine.get_query_count()
        except Exception:
            pass
        self._kpi_cards["_card_queries"].set_value(
            _format_count(queries_count),
            ACCENT_BLUE if queries_count is not None else WAITING_DATA,
        )

        # ── 2. Tokens consommés ──
        tokens = None
        try:
            from src.core.inference_worker import InferenceWorker

            if InferenceWorker is not None:
                worker = getattr(self, "_worker", None)
                if worker is not None and hasattr(worker, "total_tokens"):
                    tokens = worker.total_tokens
        except Exception:
            pass
        self._kpi_cards["_card_tokens"].set_value(
            _format_count(tokens),
            ACCENT_ORANGE if tokens is not None else WAITING_DATA,
        )

        # ── 3. Temps réponse moyen ──
        avg_time = None
        try:
            if self._rag_engine is not None:
                if hasattr(self._rag_engine, "avg_query_time"):
                    avg_time = self._rag_engine.avg_query_time
        except Exception:
            pass
        color_time = ACCENT_GREEN if (avg_time is not None and avg_time < 500) else (
            ACCENT_ORANGE if (avg_time is not None and avg_time < 2000) else (
                ACCENT_RED if avg_time is not None else WAITING_DATA
            )
        )
        self._kpi_cards["_card_response_time"].set_value(
            _format_ms(avg_time),
            color_time,
        )

        # ── 4. Taux de succès ──
        success_rate = None
        try:
            if self._rag_engine is not None:
                if hasattr(self._rag_engine, "success_rate"):
                    success_rate = self._rag_engine.success_rate
        except Exception:
            pass
        color_success = (
            ACCENT_GREEN
            if (success_rate is not None and success_rate >= 0.8)
            else (
                ACCENT_ORANGE
                if (success_rate is not None and success_rate >= 0.5)
                else (ACCENT_RED if success_rate is not None else WAITING_DATA)
            )
        )
        self._kpi_cards["_card_success_rate"].set_value(
            _format_pct(success_rate),
            color_success,
        )

        # ── 5. Faits mémoire ──
        facts_count = None
        try:
            if self._memory_store is not None:
                if hasattr(self._memory_store, "get_stats"):
                    stats = self._memory_store.get_stats()
                    if stats and isinstance(stats, dict):
                        facts_count = stats.get("facts_count") or stats.get("total_facts")
                elif hasattr(self._memory_store, "get_facts_count"):
                    facts_count = self._memory_store.get_facts_count()
                elif hasattr(self._memory_store, "get_all_facts"):
                    facts = self._memory_store.get_all_facts()
                    if facts:
                        facts_count = len(facts) if isinstance(facts, (list, str)) else None
        except Exception:
            pass
        self._kpi_cards["_card_memory_facts"].set_value(
            _format_count(facts_count),
            ACCENT_CYAN if facts_count is not None else WAITING_DATA,
        )

        # ── 6. Statut système ──
        status = "online"
        status_emoji = _status_dot(status)
        status_label = "🟢 En ligne"
        try:
            if self._memory_store is None and self._rag_engine is None:
                status = "offline"
                status_label = "🔴 Hors ligne"
        except Exception:
            status = "offline"
            status_label = "🔴 Hors ligne"
        self._kpi_cards["_card_system_status"].set_value(
            status_label,
            ACCENT_GREEN if status == "online" else ACCENT_RED,
        )

        # ── 7. Dernière activité ──
        delta_str = _format_delta(self._last_activity_time)
        self._kpi_cards["_card_last_activity"].set_value(
            delta_str,
            TEXT_SECONDARY,
        )

        # ── 8. Cache RAG hit rate ──
        hit_rate = None
        try:
            if self._memory_store is not None and hasattr(self._memory_store, "get_cache_stats"):
                cache_stats = self._memory_store.get_cache_stats()
                if cache_stats and isinstance(cache_stats, dict):
                    hit_rate = cache_stats.get("hit_rate")
        except Exception:
            pass
        color_cache = (
            ACCENT_GREEN
            if (hit_rate is not None and hit_rate >= 0.8)
            else (
                ACCENT_ORANGE
                if (hit_rate is not None and hit_rate >= 0.5)
                else (ACCENT_RED if hit_rate is not None else WAITING_DATA)
            )
        )
        self._kpi_cards["_card_cache_rag"].set_value(
            _format_pct(hit_rate),
            color_cache,
        )

        # ── 9. Stratégie active ──
        strategy = "—"
        try:
            if self._rag_engine is not None:
                if hasattr(self._rag_engine, "current_strategy"):
                    strategy = self._rag_engine.current_strategy
                elif hasattr(self._rag_engine, "get_strategy"):
                    strategy = self._rag_engine.get_strategy()
        except Exception:
            pass
        if strategy == "—" or strategy is None:
            strategy = "Hybride (sémantique + BM25)"
        self._kpi_cards["_card_active_strategy"].set_value(
            str(strategy),
            ACCENT_GREEN,
        )

    def _refresh_activity(self) -> None:
        """Met à jour la liste des 10 dernières interactions."""
        activities: list[tuple[str, str, str]] = []

        # Essayer de charger depuis le memory_store
        try:
            if self._memory_store is not None:
                if hasattr(self._memory_store, "get_recent_interactions"):
                    raw = self._memory_store.get_recent_interactions(limit=10)
                    if raw and isinstance(raw, list):
                        for entry in raw[:10]:
                            if isinstance(entry, dict):
                                icon = entry.get("icon", "💬")
                                text = entry.get("text", "—")
                                time_str = entry.get("time", "—")
                                activities.append((icon, text, time_str))
        except Exception:
            pass

        # Si aucune activité réelle, données simulées
        if not activities:
            mock = [
                ("💬", "Analyse des performances mémoire", "à l'instant"),
                ("📄", "Indexation du document « rapport_q3.pdf »", "il y a 2min"),
                ("🧠", "Nouveau fait enregistré : préférence utilisateur", "il y a 5min"),
                ("🎯", "Stratégie RAG : sémantique + BM25", "il y a 8min"),
                ("💬", "Question : « Quel est le taux de succès ? »", "il y a 12min"),
                ("📊", "Rafraîchissement des métriques dashboard", "il y a 15min"),
                ("⚡", "Consommation tokens : pic à 2.4k", "il y a 18min"),
                ("🖥️", "Vérification système : tout OK", "il y a 22min"),
                ("💾", "Cache RAG : hit rate à 87%", "il y a 30min"),
                ("🧠", "Mise à jour mémoire long terme", "il y a 45min"),
            ]
            activities = mock

        # Remplir les lignes (jusqu'à 10)
        for i in range(min(10, len(activities))):
            icon, text, time_str = activities[i]
            self._activity_items[i].set_data(icon, text, time_str)

        # Masquer les lignes excédentaires
        for i in range(len(activities), 10):
            self._activity_items[i].setVisible(False)

    def _refresh_status(self) -> None:
        """Met à jour la barre de statut en haut."""
        status = "online"
        if self._memory_store is None and self._rag_engine is None:
            status = "offline"
        elif self._memory_store is None or self._rag_engine is None:
            status = "warning"

        self._status_dot.setText(_status_dot(status))

        if status == "online":
            self._status_text.setText("NURU V11.2 — Groq llama-3.3-70b")
            self._status_sub.setText("🟢 Système opérationnel")
            self._status_sub.setStyleSheet(
                f"color: {ACCENT_GREEN}; font-size: 10px; background: transparent;"
            )
        elif status == "warning":
            self._status_text.setText("NURU V11.2 — Mode dégradé")
            self._status_sub.setText("🟡 Stockage partiel uniquement")
            self._status_sub.setStyleSheet(
                f"color: {ACCENT_ORANGE}; font-size: 10px; background: transparent;"
            )
        else:
            self._status_text.setText("NURU V11.2 — Déconnecté")
            self._status_sub.setText("🔴 Aucune source de données")
            self._status_sub.setStyleSheet(
                f"color: {ACCENT_RED}; font-size: 10px; background: transparent;"
            )

    def __repr__(self) -> str:
        return (
            f"KpiDashboardPage("
            f"memory_store={'✓' if self._memory_store else '✗'}, "
            f"rag_engine={'✓' if self._rag_engine else '✗'})"
        )
