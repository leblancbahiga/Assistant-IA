"""
NURU V7 — NavSidebar + CyberDashboard V7 (Aether Dashboard).

Trois colonnes : NavSidebar (200px) | QStackedWidget (pages) | MetricsPanel (280px).

Classes
-------
NavSidebar       : Sidebar navigation avec 3 groupes + signal page_changed(slug)
PlaceholderPage  : Page vide centrée avec titre + description
CyberDashboard   : QMainWindow assemblant sidebar, pages console, metrics
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
from pathlib import Path

import psutil

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# ── Path setup ────────────────────────────────────────────────────────────
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

# ── Conditional imports ──────────────────────────────────────────────────
try:
    from src.ui.components.nuru_widgets import MetricsPanel
    from src.ui.components.console_page import ConsolePage
except ImportError as e:
    logger.warning("Import partiel (composants UI) : %s", e)
    # Définir des stubs pour permettre l'import du module
    ConsolePage = None
    MetricsPanel = None


# ══════════════════════════════════════════════════════════════════════════
#  CONSTANTES
# ══════════════════════════════════════════════════════════════════════════

NAV_GROUPS = [
    {
        "label": "Principal",
        "items": [
            ("💬 Console", "console"),
            ("🕒 Sessions", "sessions"),
        ],
    },
    {
        "label": "Connaissances",
        "items": [
            ("📄 Documents", "documents"),
            ("🧠 Mémoire", "memory"),
            ("🌲 Nuru Brain", "nuru_brain"),
        ],
    },
    {
        "label": "Système",
        "items": [
            ("📊 V6 System", "v6_system"),
            ("⚙️ Paramètres", "settings"),
            ("📋 Logs", "logs"),
        ],
    },
]

PLACEHOLDER_PAGES: dict[str, tuple[str, str]] = {
    "sessions":   ("🕒 Sessions",       "Historique des sessions et conversations passées."),
    "documents":  ("📄 Documents",      "Gestion de la base documentaire et des sources RAG."),
    "memory":     ("🧠 Mémoire",        "Aperçu de la mémoire persistante du système."),
    "nuru_brain": ("🌲 Nuru Brain",     "Architecture neuronale et cognition augmentée."),
    "v6_system":  ("📊 V6 System",      "Panneau de contrôle des modules V6 hérités."),
    "settings":   ("⚙️ Paramètres",     "Configuration de l'application NURU."),
    "logs":       ("📋 Logs",           "Journaux système et traces de débogage."),
}


# ══════════════════════════════════════════════════════════════════════════
#  NavSidebar
# ══════════════════════════════════════════════════════════════════════════


class NavSidebar(QWidget):
    """Sidebar de navigation V7 — 3 groupes : Principal, Connaissances, Système.

    Signaux
    -------
    page_changed(str) : slug de la page sélectionnée
    """

    page_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)

        self._buttons: dict[str, QPushButton] = {}
        self._active_slug: str = ""

        self._build_ui()

    # ── Build ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header : logo + label + badge ──
        header = QWidget()
        header.setObjectName("SidebarHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 12)
        header_layout.setSpacing(8)

        logo_label = QLabel("N")
        logo_label.setObjectName("LogoLabel")
        logo_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #7f77dd;"
        )
        header_layout.addWidget(logo_label)

        name_label = QLabel("NURU")
        name_label.setObjectName("LogoLabel")
        name_label.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #e8eaf0; letter-spacing: -0.3px;"
        )
        header_layout.addWidget(name_label)

        header_layout.addStretch()

        badge = QLabel("V7")
        badge.setObjectName("VersionBadge")
        badge.setStyleSheet(
            "background-color: #242836; color: #555e78; font-size: 10px;"
            " font-weight: 600; padding: 2px 8px; border-radius: 4px;"
            " border: 1px solid #2e3347; margin: 0;"
        )
        header_layout.addWidget(badge)

        layout.addWidget(header)

        # ── Groupes de navigation ──
        for group in NAV_GROUPS:
            # Section label
            section = QLabel(group["label"])
            section.setObjectName("NavSectionLabel")
            section.setStyleSheet(
                "color: #555e78; font-size: 10px; font-weight: 700;"
                " text-transform: uppercase; letter-spacing: 1.2px;"
                " padding: 16px 16px 6px 16px; background: transparent;"
            )
            layout.addWidget(section)

            for label_text, slug in group["items"]:
                btn = QPushButton(label_text)
                btn.setObjectName("NavButton")
                btn.setProperty("slug", slug)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setCheckable(True)
                btn.setStyleSheet(
                    "QPushButton#NavButton {"
                    "  background-color: transparent; color: #9098b0;"
                    "  border: none; border-radius: 6px;"
                    "  padding: 8px 16px; margin: 0 8px;"
                    "  font-size: 13px; font-weight: 500; text-align: left;"
                    "}"
                    "QPushButton#NavButton:hover {"
                    "  background-color: #242836; color: #e8eaf0;"
                    "}"
                    "QPushButton#NavButton:pressed {"
                    "  background-color: #2e3347; color: #e8eaf0;"
                    "}"
                    "QPushButton#NavButton[active=\"true\"],"
                    "QPushButton#NavButton:checked {"
                    "  background-color: #1a1d26; color: #7f77dd;"
                    "  border-left: 2px solid #7f77dd;"
                    "  padding: 8px 16px 8px 14px;"
                    "}"
                )
                btn.clicked.connect(lambda _checked=False, s=slug: self._on_nav_click(s))
                layout.addWidget(btn)
                self._buttons[slug] = btn

        layout.addStretch()

        # ── Footer : Info modèle ──
        self._model_label = QLabel("Modèle: ...  •  En attente")
        self._model_label.setObjectName("ModelInfoFooter")
        self._model_label.setStyleSheet(
            "color: #4b5563; font-size: 9px; padding: 8px 16px;"
        )
        self._model_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._model_label)

    # ── Internes ─────────────────────────────────────────────────────────

    def _on_nav_click(self, slug: str) -> None:
        """Gère le clic sur un bouton de navigation."""
        self.set_active(slug)
        self.page_changed.emit(slug)

    # ── API publique ─────────────────────────────────────────────────────

    def set_active(self, slug: str) -> None:
        """Active le bouton correspondant au slug donné."""
        if self._active_slug and self._active_slug in self._buttons:
            old_btn = self._buttons[self._active_slug]
            old_btn.setProperty("active", "false")
            old_btn.setChecked(False)
            self._unpolish(old_btn)

        if slug in self._buttons:
            new_btn = self._buttons[slug]
            new_btn.setProperty("active", "true")
            new_btn.setChecked(True)
            self._unpolish(new_btn)
            self._active_slug = slug

    def update_model_info(self, name: str, stats: str) -> None:
        """Met à jour l'info modèle dans le footer de la sidebar."""
        self._model_label.setText(f"{name}  •  {stats}")

    @staticmethod
    def _unpolish(widget: QWidget) -> None:
        """Force le rafraîchissement du QSS après changement de propriété."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)


# ══════════════════════════════════════════════════════════════════════════
#  PlaceholderPage
# ══════════════════════════════════════════════════════════════════════════


class PlaceholderPage(QWidget):
    """Page vide avec titre et description centrés."""

    def __init__(
        self,
        title: str = "Page",
        description: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("PlaceholderPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 40)
        layout.setAlignment(Qt.AlignCenter)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("PageTitle")
        self._title_label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #e8eaf0;"
            " padding: 0 0 4px 0; background: transparent;"
        )
        self._title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_label)

        if description:
            self._desc_label = QLabel(description)
            self._desc_label.setObjectName("PageSubtitle")
            self._desc_label.setStyleSheet(
                "font-size: 13px; color: #9098b0;"
                " padding: 0; background: transparent;"
            )
            self._desc_label.setAlignment(Qt.AlignCenter)
            self._desc_label.setWordWrap(True)
            layout.addWidget(self._desc_label)

        layout.addStretch()


# ══════════════════════════════════════════════════════════════════════════
#  CyberDashboard (V7)
# ══════════════════════════════════════════════════════════════════════════


class CyberDashboard(QMainWindow):
    """Fenêtre principale NURU V7 — three-panel Aether Dashboard.

    Architecture
    ------------
    [ NavSidebar 200px | QStackedWidget (pages) | MetricsPanel 280px ]

    Pages
    -----
    - console (ConsolePage — chat complet)
    - sessions, documents, memory, nuru_brain, v6_system, settings, logs
      (PlaceholderPages — à implémenter)

    Signaux (forwarding ConsolePage)
    ---------------------------------
    query_submitted(str, bool) : (query, strict_mode)
    citation_clicked(str, int)
    feedback_positive(str)
    feedback_negative(str)
    new_chat()  : nouvelle conversation
    voice_toggled()
    """

    query_submitted = Signal(str, bool)
    citation_clicked = Signal(str, int)
    feedback_positive = Signal(str)
    feedback_negative = Signal(str)
    new_chat = Signal()
    voice_toggled = Signal()

    def __init__(self):
        super().__init__()
        logger.info("CyberDashboard V7 — initialisation...")

        # ── État interne ──
        self._rag_scores_session: list[float] = []
        self._rag_docs_found: list[int] = []
        self._rag_rejections: int = 0
        self._rag_queries_total: int = 0
        self._rag_sources_diversity: list[int] = []

        self._build_window()
        self._build_ui()
        self._wire_signals()
        self._init_timers()
        self.load_styles()

        # Message de bienvenue
        self.console_page.clear_chat()
        self.console_page.add_message(
            "NURU",
            "Bonjour, je suis NURU V7. Comment puis-je vous aider ?",
            is_user=False,
        )

        self._pages.setCurrentIndex(0)
        self._sidebar.set_active("console")

        logger.info("CyberDashboard V7 — prêt.")

    # ══════════════════════════════════════════════════════════════════════
    #  BUILD
    # ══════════════════════════════════════════════════════════════════════

    def _build_window(self) -> None:
        """Configure les propriétés de la fenêtre."""
        self.setWindowTitle("NURU V7")
        self.setMinimumSize(1100, 680)
        self.resize(1400, 860)

    def _build_ui(self) -> None:
        """Assemble les trois panneaux."""
        central = QWidget()
        self.setCentralWidget(central)

        self._main_layout = QHBoxLayout(central)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # ── 1. Sidebar ──
        self._sidebar = NavSidebar()
        self._main_layout.addWidget(self._sidebar)

        # ── 2. Pages centrales ──
        self._pages = QStackedWidget()
        self._pages.setObjectName("PagesStack")

        # Console (index 0)
        if ConsolePage is not None:
            self.console_page = ConsolePage()
        else:
            self.console_page = PlaceholderPage("Console", "Console non disponible")
        self._pages.addWidget(self.console_page)

        # Placeholder pages (index 1..7)
        self._placeholder_map: dict[str, QWidget] = {}
        for slug, (title, desc) in PLACEHOLDER_PAGES.items():
            page = PlaceholderPage(title, desc)
            self._pages.addWidget(page)
            self._placeholder_map[slug] = page

        self._main_layout.addWidget(self._pages, stretch=1)

        # ── 3. Metrics Panel ──
        if MetricsPanel is not None:
            self._metrics = MetricsPanel()
        else:
            self._metrics = QWidget()
            self._metrics.setObjectName("MetricsPanel")
            self._metrics.setFixedWidth(280)
            layout = QVBoxLayout(self._metrics)
            layout.addWidget(QLabel("Métriques non disponibles"))
        self._main_layout.addWidget(self._metrics)

    def _wire_signals(self) -> None:
        """Connecte les signaux entre composants."""
        # Sidebar → page switching
        self._sidebar.page_changed.connect(self._on_page_changed)

        # Console → signaux dashboard
        if hasattr(self.console_page, "query_submitted"):
            self.console_page.query_submitted.connect(self._on_query)
            self.console_page.citation_clicked.connect(
                self.citation_clicked.emit
            )
            self.console_page.feedback_positive.connect(
                self.feedback_positive.emit
            )
            self.console_page.feedback_negative.connect(
                self.feedback_negative.emit
            )
            self.console_page.new_chat.connect(self.new_chat.emit)
            self.console_page.voice_toggled.connect(self.voice_toggled.emit)
            self.console_page.clear_requested.connect(self._on_console_clear)

    def _init_timers(self) -> None:
        """Initialise le timer de mise à jour des métriques."""
        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(1000)  # 1 s
        self._metrics_timer.timeout.connect(self._update_metrics)
        self._metrics_timer.start()

    # ══════════════════════════════════════════════════════════════════════
    #  STYLES
    # ══════════════════════════════════════════════════════════════════════

    def load_styles(self) -> None:
        """Charge le fichier styles.qss."""
        style_path = Path(__file__).parent / "styles.qss"
        if style_path.exists():
            try:
                with open(style_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
                logger.info("Styles chargés depuis %s", style_path)
            except Exception as e:
                logger.warning("Impossible de charger les styles : %s", e)
        else:
            logger.info("Aucun fichier styles.qss trouvé à %s", style_path)

    # ══════════════════════════════════════════════════════════════════════
    #  CALLBACKS
    # ══════════════════════════════════════════════════════════════════════

    def _on_page_changed(self, slug: str) -> None:
        """Change la page affichée selon le slug."""
        if slug == "console":
            self._pages.setCurrentIndex(0)
            return

        page = self._placeholder_map.get(slug)
        if page:
            idx = self._pages.indexOf(page)
            if idx >= 0:
                self._pages.setCurrentIndex(idx)

    def _on_query(self, text: str, strict_mode: bool) -> None:
        """Traite une requête utilisateur.

        Mode démo : répond directement dans la console.
        Mode async (via signal) : émet query_submitted pour le parent.
        """
        logger.info("Requête reçue : text=%s, strict=%s", text[:60], strict_mode)

        # En mode démo, on simule une réponse
        if os.environ.get("NURU_DEMO_MODE", "0") == "1":
            self.console_page.messages.show_typing()
            QTimer.singleShot(800, lambda: self._demo_response(text))
        else:
            # Forward au parent via signal
            self.query_submitted.emit(text, strict_mode)

    def _demo_response(self, query: str) -> None:
        """Réponse simulée en mode démo."""
        self.console_page.messages.hide_typing()
        responses = {
            "bonjour": "Bonjour ! Je suis NURU V7. Comment puis-je vous aider ?",
            "aide": "Je peux vous assister sur vos documents, répondre à vos questions, "
                    "et gérer votre base de connaissances. En mode démo, mes réponses "
                    "sont simulées.",
        }
        reply = "Désolé, je ne peux pas traiter cette requête en mode démo. "
        "Activez le mode normal pour utiliser NURU avec toutes ses capacités."
        for key, resp in responses.items():
            if key in query.lower():
                reply = resp
                break

        self.console_page.messages.add_message(text=reply, role="assistant")

    def _on_console_clear(self) -> None:
        """Réinitialise la console après nettoyage."""
        self._pages.setCurrentIndex(0)
        self._sidebar.set_active("console")

        # Réinitialiser les métriques RAG
        self._rag_scores_session.clear()
        self._rag_docs_found.clear()
        self._rag_rejections = 0
        self._rag_queries_total = 0
        self._rag_sources_diversity.clear()

    # ══════════════════════════════════════════════════════════════════════
    #  MÉTRIQUES
    # ══════════════════════════════════════════════════════════════════════

    def _update_metrics(self) -> None:
        """Met à jour les métriques système (RAM, CPU, etc.) toutes les secondes."""
        try:
            # Métriques RAM via psutil
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024**3)
            used_gb = mem.used / (1024**3)
            free_gb = mem.available / (1024**3)
            ram_pct = mem.percent

            if hasattr(self._metrics, "set_ram"):
                self._metrics.set_ram(ram_pct, f"{used_gb:.1f}", f"{total_gb:.0f}")

            # Stratégie active
            if hasattr(self._metrics, "set_strategy"):
                self._metrics.set_strategy("LOCAL", "phi-4-mini-4bit")

            # Métriques simulées
            if hasattr(self._metrics, "set_rag_score"):
                avg_rag = (
                    sum(self._rag_scores_session) / len(self._rag_scores_session)
                    if self._rag_scores_session
                    else 0.0
                )
                self._metrics.set_rag_score(avg_rag)

        except Exception as e:
            logger.debug("Échec mise à jour métriques : %s", e)

    # ══════════════════════════════════════════════════════════════════════
    #  BACKWARD COMPATIBILITY (legacy API de CyberDashboard V6)
    # ══════════════════════════════════════════════════════════════════════

    def add_message(
        self,
        sender: str,
        text: str,
        is_user: bool = False,
        rag_score: float | None = None,
    ):
        """Ancienne API — ajoute un message dans la console.

        Délègue à ``ConsolePage.add_message()``.
        """
        if hasattr(self.console_page, "add_message"):
            return self.console_page.add_message(sender, text, is_user, rag_score)
        return None

    def clear_chat(self) -> None:
        """Ancienne API — vide la console."""
        if hasattr(self.console_page, "clear_chat"):
            self.console_page.clear_chat()

    def update_last_assistant_rag(self, rag_score: float) -> None:
        """Ancienne API — met à jour le RAG sur la dernière bulle assistant."""
        if hasattr(self.console_page, "update_last_assistant_rag"):
            self.console_page.update_last_assistant_rag(rag_score)

    def set_sources(self, sources: list) -> None:
        """Ancienne API — définit les sources sur la console."""
        if hasattr(self.console_page, "set_sources"):
            self.console_page.set_sources(sources)

    def switch_page(self, index: int) -> None:
        """Ancienne API — change de page par index (compat V6)."""
        if 0 <= index < self._pages.count():
            self._pages.setCurrentIndex(index)


# ══════════════════════════════════════════════════════════════════════════
#  CLI (test)
# ══════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)

    win = CyberDashboard()
    win.show()

    sys.exit(app.exec())
