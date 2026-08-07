"""
NURU V16 — Home Page (Dashboard Kernel).

Page d'accueil connectée au kernel NURU.
Affiche en temps réel l'état du noyau : state, metrics, resources,
router, scheduler, cache.

Accède au kernel via NuruKernel() (singleton).
Timer Qt 2s rafraîchit les métriques.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Palette cyberpunk NURU ──
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
COLOR_IDLE = "#555555"


def _kernel():
    """Accès singleton au kernel."""
    try:
        from src.kernel import NuruKernel
        return NuruKernel()
    except Exception:
        return None


def _val(v, default="—"):
    """Retourne v si v est truthy, sinon default."""
    return v if v else default


# ════════════════════════════════════════════════════════════════
#  Mini-carte métrique compacte
# ════════════════════════════════════════════════════════════════


class _MiniCard(QFrame):
    """Petite carte métrique pour le dashboard kernel."""

    def __init__(self, title: str, value: str = "—", icon: str = "📊",
                 color: str = ACCENT_BLUE, parent=None):
        super().__init__(parent)
        self.setObjectName("MiniCard")
        self.setStyleSheet(f"""
            #MiniCard {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 14px; background: transparent;")
        header.addWidget(icon_lbl)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;"
        )
        header.addWidget(title_lbl)
        header.addStretch()
        layout.addLayout(header)

        self._value_lbl = QLabel(value)
        self._value_lbl.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(self._value_lbl)

    def set_value(self, value: str, color: str = ACCENT_BLUE) -> None:
        self._value_lbl.setText(_val(value))
        self._value_lbl.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: bold; background: transparent;"
        )


# ════════════════════════════════════════════════════════════════
#  Section de métriques (groupe de mini-cartes)
# ════════════════════════════════════════════════════════════════


class _MetricSection(QFrame):
    """Section nommée avec mini-cartes en grille."""

    def __init__(self, title: str, icon: str, cards: list[dict], parent=None):
        super().__init__(parent)
        self.setObjectName("MetricSection")
        self.setStyleSheet(f"""
            #MetricSection {{
                background-color: {BG_DARK};
                border: none;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QLabel(f"{icon}  {title}")
        header.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-size: 13px; font-weight: bold; "
            f"background: transparent; padding: 4px 0px;"
        )
        layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(6)

        self._card_widgets: dict[str, _MiniCard] = {}
        for idx, spec in enumerate(cards):
            card = _MiniCard(
                title=spec["title"], icon=spec.get("icon", "📊"),
                color=spec.get("color", ACCENT_BLUE),
            )
            setattr(self, spec["attr"], card)
            self._card_widgets[spec["attr"]] = card
            grid.addWidget(card, idx // 3, idx % 3)

        layout.addLayout(grid)

    def set_card(self, attr: str, value: str, color: str = ACCENT_BLUE) -> None:
        card = self._card_widgets.get(attr)
        if card:
            card.set_value(value, color)


# ════════════════════════════════════════════════════════════════
#  Status Bar
# ════════════════════════════════════════════════════════════════


class _StatusBar(QFrame):
    """Barre de statut générale (kernel alive, ressources, uptime)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KernelStatusBar")
        self.setStyleSheet(f"""
            #KernelStatusBar {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self._dot = QLabel("🟢")
        self._dot.setStyleSheet("font-size: 16px; background: transparent;")
        layout.addWidget(self._dot)

        self._state = QLabel("Kernel opérationnel")
        self._state.setStyleSheet(
            f"color: {ACCENT_GREEN}; font-size: 12px; font-weight: bold; "
            f"background: transparent;"
        )
        layout.addWidget(self._state)

        self._details = QLabel("")
        self._details.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;"
        )
        layout.addWidget(self._details, stretch=1)

        self._ram = QLabel("RAM: —")
        self._ram.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 11px; background: transparent;"
        )
        layout.addWidget(self._ram)

    def set_status(self, state_ok: bool, details: str, ram_info: str) -> None:
        self._dot.setText("🟢" if state_ok else "🔴")
        self._state.setText("Kernel opérationnel" if state_ok else "Kernel indisponible")
        self._state.setStyleSheet(
            f"color: {ACCENT_GREEN if state_ok else ACCENT_RED}; "
            f"font-size: 12px; font-weight: bold; background: transparent;"
        )
        self._details.setText(details)
        self._ram.setText(ram_info)


# ════════════════════════════════════════════════════════════════
#  HomePage — Dashboard Kernel
# ════════════════════════════════════════════════════════════════


class HomePage(QScrollArea):
    """Page d'accueil NURU : dashboard kernel temps réel.

    Se connecte au NuruKernel (singleton) et rafraîchit
    toutes les métriques toutes les 2s.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("HomePageKernel")
        self.setWidgetResizable(True)
        self.setStyleSheet(f"background-color: {BG_DARK}; border: none;")

        self._k = None
        self._build_ui()
        self._connect_kernel()

        # Timer 2s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(2000)
        self._refresh()

    # ── UI ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = QWidget()
        container.setStyleSheet(f"background-color: {BG_DARK};")
        self.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Status bar
        self._status = _StatusBar()
        layout.addWidget(self._status)

        # Titre
        title = QLabel("🏠  Dashboard Noyau")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 22px; font-weight: bold; "
            f"background: transparent;"
        )
        layout.addWidget(title)

        # ── Section 1 : État Kernel ──
        self._section_state = _MetricSection(
            "État du Kernel", "🧠",
            [
                {"attr": "model", "title": "Modèle actif", "icon": "🤖", "color": ACCENT_BLUE},
                {"attr": "worker", "title": "Worker", "icon": "⚙️", "color": ACCENT_GREEN},
                {"attr": "conv", "title": "Conversation", "icon": "💬", "color": ACCENT_PURPLE},
                {"attr": "provider", "title": "Provider", "icon": "🔌", "color": ACCENT_CYAN},
                {"attr": "started", "title": "Démarré depuis", "icon": "⏱️", "color": ACCENT_ORANGE},
                {"attr": "queries", "title": "Requêtes", "icon": "📝", "color": ACCENT_PINK},
            ],
        )
        layout.addWidget(self._section_state)

        # ── Section 2 : Métriques système ──
        self._section_metrics = _MetricSection(
            "Métriques système", "📊",
            [
                {"attr": "rss", "title": "RSS mémoire", "icon": "💾", "color": ACCENT_BLUE},
                {"attr": "ram_free", "title": "RAM libre", "icon": "🧮", "color": ACCENT_GREEN},
                {"attr": "swap", "title": "Swap", "icon": "🔄", "color": ACCENT_ORANGE},
                {"attr": "pressure", "title": "Pression mémoire", "icon": "🛡️", "color": ACCENT_RED},
                {"attr": "threads", "title": "Threads", "icon": "🧵", "color": ACCENT_PURPLE},
                {"attr": "cpu", "title": "CPU", "icon": "⚡", "color": ACCENT_CYAN},
            ],
        )
        layout.addWidget(self._section_metrics)

        # ── Section 3 : Ordonnanceur ──
        self._section_sched = _MetricSection(
            "Ordonnanceur", "📋",
            [
                {"attr": "running", "title": "Tâches en cours", "icon": "▶️", "color": ACCENT_GREEN},
                {"attr": "pending", "title": "En attente", "icon": "⏳", "color": ACCENT_ORANGE},
                {"attr": "completed", "title": "Terminées", "icon": "✅", "color": ACCENT_BLUE},
                {"attr": "cancelled", "title": "Annulées", "icon": "❌", "color": ACCENT_RED},
            ],
        )
        layout.addWidget(self._section_sched)

        # ── Section 4 : Cache ──
        self._section_cache = _MetricSection(
            "Cache", "🗂️",
            [
                {"attr": "entries", "title": "Entrées totales", "icon": "📦", "color": ACCENT_BLUE},
                {"attr": "hit_ratio", "title": "Hit ratio", "icon": "🎯", "color": ACCENT_GREEN},
                {"attr": "size_mb", "title": "Taille mémoire", "icon": "💾", "color": ACCENT_PURPLE},
                {"attr": "evictions", "title": "Évictions", "icon": "🗑️", "color": ACCENT_ORANGE},
            ],
        )
        layout.addWidget(self._section_cache)

        # Footer
        self._footer = QLabel("Mise à jour toutes les 2s · NURU V16")
        self._footer.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 9px; background: transparent;"
        )
        layout.addWidget(self._footer)

        layout.addStretch()

    # ── Connexion kernel ───────────────────────────────────────

    def _connect_kernel(self) -> None:
        self._k = _kernel()
        if self._k is not None:
            logger.info("🏠 HomePage connectée au kernel")
        else:
            logger.warning("🏠 HomePage: kernel non disponible")

    # ── Rafraîchissement ───────────────────────────────────────

    def _refresh(self) -> None:
        k = self._k
        if k is None:
            self._status.set_status(False, "kernel non connecté", "RAM: —")
            return

        try:
            state = k.get("state") if k.has("state") else None
            metrics = k.get("metrics") if k.has("metrics") else None
            resources = k.get("resources") if k.has("resources") else None
            cache = k.get("cache") if k.has("cache") else None
            sched = k.get("scheduler") if k.has("scheduler") else None

            self._refresh_state(state)
            self._refresh_metrics(metrics, resources)
            self._refresh_scheduler(sched)
            self._refresh_cache(cache)
            self._refresh_status(state, resources, metrics)
        except Exception as e:
            logger.warning("HomePage._refresh: %s", e)

    # ── Section par section ────────────────────────────────────

    def _refresh_state(self, state) -> None:
        if state is None:
            return
        try:
            snap = state.snapshot()
            self._section_state.set_card("model", _val(snap.get("active_model")), ACCENT_BLUE)
            self._section_state.set_card("worker", _val(snap.get("active_worker")), ACCENT_GREEN)
            self._section_state.set_card("conv", _val(snap.get("conversation_id")), ACCENT_PURPLE)
            self._section_state.set_card("provider", _val(snap.get("provider")), ACCENT_CYAN)

            started = snap.get("started_at")
            if started:
                import time
                elapsed = int(time.time() - started)
                h = elapsed // 3600
                m = (elapsed % 3600) // 60
                self._section_state.set_card("started", f"{h}h{m}m", ACCENT_ORANGE)
            else:
                self._section_state.set_card("started", "—", ACCENT_ORANGE)

            qcount = snap.get("query_count", 0)
            self._section_state.set_card("queries", str(qcount), ACCENT_PINK)
        except Exception as e:
            logger.warning("HomePage.state: %s", e)

    def _refresh_metrics(self, metrics, resources) -> None:
        if metrics is None:
            return
        try:
            snap = metrics.collect()
            self._section_metrics.set_card("rss", f'{snap.get("process_rss_mb", "—")} MB', ACCENT_BLUE)

            ram_free = snap.get("memory_free_gb")
            ram_free_str = f'{ram_free} Go' if ram_free is not None else "—"
            self._section_metrics.set_card("ram_free", ram_free_str, ACCENT_GREEN)

            swap = snap.get("swap_percent")
            swap_str = f'{swap}%' if swap is not None else "—"
            swap_color = ACCENT_GREEN
            if swap is not None:
                swap_color = ACCENT_GREEN if swap < 50 else ACCENT_ORANGE if swap < 80 else ACCENT_RED
            self._section_metrics.set_card("swap", swap_str, swap_color)

            self._section_metrics.set_card("threads", str(snap.get("thread_count", "—")), ACCENT_PURPLE)
            self._section_metrics.set_card("cpu", f'{snap.get("cpu_percent", "—")}%', ACCENT_CYAN)

            # Pression mémoire depuis resources
            if resources is not None:
                pres = resources.get_pressure()
                pres_color = ACCENT_GREEN if pres == "ok" else ACCENT_ORANGE if pres == "warning" else ACCENT_RED
                self._section_metrics.set_card("pressure", pres, pres_color)
        except Exception as e:
            logger.warning("HomePage.metrics: %s", e)

    def _refresh_scheduler(self, sched) -> None:
        if sched is None:
            return
        try:
            snap = sched.snapshot()
            self._section_sched.set_card("running", str(snap.get("running", 0)),
                                         ACCENT_GREEN if snap.get("running", 0) == 0 else ACCENT_BLUE)
            pending = snap.get("pending", 0)
            self._section_sched.set_card("pending", str(pending),
                                         ACCENT_ORANGE if pending > 0 else COLOR_IDLE)
            self._section_sched.set_card("completed", str(snap.get("total_completed", 0)), ACCENT_BLUE)
            self._section_sched.set_card("cancelled", str(snap.get("cancelled", 0)), ACCENT_RED)
        except Exception as e:
            logger.warning("HomePage.sched: %s", e)

    def _refresh_cache(self, cache) -> None:
        if cache is None:
            return
        try:
            s = cache.stats()
            self._section_cache.set_card("entries", str(s.get("total_entries", 0)), ACCENT_BLUE)
            hit = s.get("hit_ratio", 0)
            hit_color = ACCENT_GREEN if hit > 0.5 else ACCENT_ORANGE if hit > 0.2 else COLOR_IDLE
            self._section_cache.set_card("hit_ratio", f"{hit:.0%}", hit_color)
            size = s.get("total_size_mb", 0)
            self._section_cache.set_card("size_mb", f"{size:.1f} MB" if size else "—", ACCENT_PURPLE)
            self._section_cache.set_card("evictions", str(s.get("evictions", 0)), ACCENT_ORANGE)
        except Exception as e:
            logger.warning("HomePage.cache: %s", e)

    def _refresh_status(self, state, resources, metrics) -> None:
        try:
            model = "—"
            if state is not None:
                model = _val(state.snapshot().get("active_model"))

            details = f"Noyau actif · modèle: {model}"

            ram_info = "RAM: —"
            if metrics is not None:
                snap = metrics.collect()
                ram_free = snap.get("ram_free_gb", "—")
                swap = snap.get("swap_pct", "—")
                ram_info = f"RAM: {ram_free} Go libre · swap: {swap}%"

            self._status.set_status(True, details, ram_info)
        except Exception as e:
            logger.warning("HomePage.status: %s — ram_info=—", e)
            self._status.set_status(True, "Kernel connecté", "RAM: —")

    # ── Cleanup ────────────────────────────────────────────────

    def cleanup(self) -> None:
        try:
            self._timer.stop()
        except Exception:
            pass
