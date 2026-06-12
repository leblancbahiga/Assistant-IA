"""
NURU V8+ — NavSidebar + CyberDashboard V7 (Aether Dashboard).

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

from PySide6.QtCore import Qt, QTimer, Signal, QSize, QThreadPool
from PySide6.QtGui import QFont

# ── Path setup ────────────────────────────────────────────────────────────
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

# ── InferenceWorker (thread-safe LLM) ──
try:
    from src.core.inference_worker import InferenceWorker
    HAS_WORKER = True
except ImportError:
    InferenceWorker = None
    HAS_WORKER = False
    logger.warning("InferenceWorker non disponible")
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

# ── Conditional imports ──────────────────────────────────────────────────
try:
    from src.ui.components.right_panel import RightPanelDiagnostic
    from src.ui.components.console_page import ConsolePage
except ImportError as e:
    logger.warning("Import partiel (composants UI) : %s", e)
    ConsolePage = None
    RightPanelDiagnostic = None

# ── ViewModels ──────────────────────────────────────────────────────────
try:
    from src.ui.viewmodels.rag_diagnostic_vm import RAGDiagnosticViewModel
except ImportError:
    RAGDiagnosticViewModel = None

# ── Page components ─────────────────────────────────────────────────────
try:
    from src.ui.components.sessions_page import SessionsPage
except ImportError:
    SessionsPage = None
try:
    from src.ui.components.documents_page import DocumentsPage
except ImportError:
    DocumentsPage = None
try:
    from src.ui.components.memory_page import MemoryPage
except ImportError:
    MemoryPage = None
try:
    from src.ui.components.logs_page import LogsPage
except ImportError:
    LogsPage = None
try:
    from src.ui.components.settings_page import SettingsPage
except ImportError:
    SettingsPage = None
try:
    from src.ui.components.v6_system_page import SystemPage
except ImportError:
    SystemPage = None
try:
    from src.ui.components.diagnostics_page import DiagnosticsPage
except ImportError:
    DiagnosticsPage = None

# ── V9 Component imports ────────────────────────────────────────────────
try:
    from src.ui.components.agent_status import AgentStatusWidget
except ImportError:
    AgentStatusWidget = None
try:
    from src.ui.components.memory_explorer import MemoryExplorer
except ImportError:
    MemoryExplorer = None
try:
    from src.ui.components.feedback_bar import FeedbackBar
except ImportError:
    FeedbackBar = None
try:
    from src.ui.components.task_list import TaskListWidget
except ImportError:
    TaskListWidget = None

# ── V10 Component imports ────────────────────────────────────────────────
try:
    from src.ui.components.stats_page import StatsPage
except ImportError:
    StatsPage = None
try:
    from src.ui.components.tool_tester import ToolTester
except ImportError:
    ToolTester = None


# ══════════════════════════════════════════════════════════════════════════
#  CONSTANTES
# ══════════════════════════════════════════════════════════════════════════

NAV_GROUPS = [
    {
        "label": "Principal",
        "items": [
            ("💬 Console", "console"),
            ("🕒 Sessions", "sessions"),
            ("📊 Diagnostics", "diagnostics"),
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
        "label": "NURU V9",
        "items": [
            ("🤖 Agent", "agent"),
            ("🧠 Mémoire V9", "memory_v9"),
            ("📋 Tâches", "tasks"),
            ("💬 Feedback", "feedback"),
        ],
    },
    {
        "label": "Système",
        "items": [
            ("⚙️ État V10", "v6_system"),
            ("⚙️ Paramètres", "settings"),
            ("📋 Logs", "logs"),
        ],
    },
    {
        "label": "NURU V10",
        "items": [
            ("📈 Stats V10", "stats_v10"),
            ("🔧 Outils V10", "tools_v10"),
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
    "diagnostics":("📊 Diagnostics",    "Analyse des performances RAG et diagnostic des requêtes."),
    "stats_v10":   ("📈 Stats V10",      "Statistiques temps réel et coûts de NURU V10."),
    "tools_v10":   ("🔧 Outils V10",     "Test des outils de génération et de recherche."),
}


# ══════════════════════════════════════════════════════════════════════════
#  RecentDocuments (Module 2)
# ══════════════════════════════════════════════════════════════════════════


class RecentDocuments(QWidget):
    """Liste des documents récents dans la sidebar.

    Chaque doc : icône + nom + dot de statut (indexed=#1E6B3A, partial=#6B4E1E).
    Données mock pour l'instant.
    """

    DOC_MOCK = [
        ("📄", "CV_Leblanc_2024.pdf", True),
        ("📄", "Rapport_Lubero.pdf", True),
        ("📄", "PUA-CI_Avenant.docx", False),   # partial
        ("📄", "Rendements_riz.xlsx", True),
    ]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RecentDocuments")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        label = QLabel("Documents récents")
        label.setObjectName("NavSectionLabel")
        layout.addWidget(label)

        for icon_char, name, indexed in self.DOC_MOCK:
            item = QWidget()
            item.setObjectName("RecentDocItem")
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(8, 3, 8, 3)
            item_layout.setSpacing(6)

            icon = QLabel(icon_char)
            icon.setStyleSheet("font-size: 13px; background: transparent;")
            item_layout.addWidget(icon)

            name_label = QLabel(name)
            name_label.setStyleSheet(
                "font-size: 10px; color: #3D5266; background: transparent;"
            )
            item_layout.addWidget(name_label, stretch=1)

            dot = QLabel()
            dot.setFixedSize(5, 5)
            dot.setObjectName("DocDot")
            if indexed:
                dot.setProperty("indexed", "true")
                dot.setProperty("partial", "false")
            else:
                dot.setProperty("indexed", "false")
                dot.setProperty("partial", "true")
            dot.setStyleSheet(
                f"background-color: {'#1E6B3A' if indexed else '#6B4E1E'};"
                " border-radius: 3px; min-width: 5px; max-width: 5px;"
                " min-height: 5px; max-height: 5px;"
            )
            item_layout.addWidget(dot)

            layout.addWidget(item)


# ══════════════════════════════════════════════════════════════════════════
#  CloudStatusBadge (Module 2)
# ══════════════════════════════════════════════════════════════════════════


class CloudStatusBadge(QWidget):
    """Badge en bas de la sidebar — dot vert + texte Cloud."""

    def __init__(self, model_name: str = "phi-4-mini-4bit", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CloudStatusBadge")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(6)

        dot = QLabel()
        dot.setObjectName("CloudStatusDot")
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(
            "min-width: 6px; max-width: 6px; min-height: 6px;"
            " max-height: 6px; border-radius: 3px; background-color: #2A9A4A;"
        )
        layout.addWidget(dot)

        self._text = QLabel(f"Cloud · {model_name}")
        self._text.setObjectName("CloudStatusText")
        layout.addWidget(self._text)
        layout.addStretch()

    def set_model(self, model_name: str) -> None:
        self._text.setText(f"Cloud · {model_name}")


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
        header_layout.addWidget(logo_label)

        name_label = QLabel("NURU")
        name_label.setObjectName("LogoLabel")
        header_layout.addWidget(name_label)

        header_layout.addStretch()

        badge = QLabel("V10")
        badge.setObjectName("VersionBadge")
        header_layout.addWidget(badge)

        layout.addWidget(header)

        # ── Groupes de navigation ──
        for group in NAV_GROUPS:
            # Section label
            section = QLabel(group["label"])
            section.setObjectName("NavSectionLabel")
            layout.addWidget(section)

            for label_text, slug in group["items"]:
                btn = QPushButton(label_text)
                btn.setObjectName("NavButton")
                btn.setProperty("slug", slug)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setCheckable(True)
                btn.clicked.connect(lambda _checked=False, s=slug: self._on_nav_click(s))
                layout.addWidget(btn)
                self._buttons[slug] = btn

        layout.addStretch()

        # ── Documents récents (Module 2) ──
        self._recent_docs = RecentDocuments()
        layout.addWidget(self._recent_docs)

        # ── Cloud Status Badge (Module 2) ──
        self._cloud_badge = CloudStatusBadge()
        layout.addWidget(self._cloud_badge)

        # ── Footer : Info modèle ──
        self._model_label = QLabel("Modèle: ...  •  En attente")
        self._model_label.setObjectName("ModelInfoFooter")
        self._model_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._model_label)

    def set_model_info(self, model: str, status: str, queries: int = 0) -> None:
        """Met à jour les infos modèle dans le footer."""
        self._model_label.setText(f"{model}  •  {status}")

    def set_cloud_model(self, model_name: str) -> None:
        """Met à jour le CloudStatusBadge."""
        self._cloud_badge.set_model(model_name)

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

        # ── titre ──
        self._title_label = QLabel(title)
        self._title_label.setObjectName("PageTitle")
        self._title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_label)

        if description:
            # ── sous-titre ──
            self._desc_label = QLabel(description)
            self._desc_label.setObjectName("PageSubtitle")
            self._desc_label.setAlignment(Qt.AlignCenter)
            self._desc_label.setWordWrap(True)
            layout.addWidget(self._desc_label)

        layout.addStretch()


# ══════════════════════════════════════════════════════════════════════════
#  CyberDashboard (V7)
# ══════════════════════════════════════════════════════════════════════════


class CyberDashboard(QMainWindow):
    """Fenêtre principale NURU V8+ — three-panel Aether Dashboard.

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

    def __init__(self, core=None):
        super().__init__()
        self._core = core
        logger.info("CyberDashboard V10 — initialisation...")

        # ── État interne ──
        self._rag_scores_session: list[float] = []
        self._rag_docs_found: list[int] = []
        self._rag_rejections: int = 0
        self._rag_queries_total: int = 0
        self._rag_sources_diversity: list[int] = []
        self._current_bubble = None
        self._current_query = ""
        self._current_strict = False
        self._is_processing = False
        self._total_tokens_received = 0
        self._token_timestamps: list[float] = []
        self._last_llm_update = 0.0

        self._build_window()
        self._build_ui()
        self._wire_signals()
        self._init_timers()
        self.load_styles()
        self._wire_page_dependencies()

        # Message de bienvenue
        self.console_page.clear_chat()
        self.console_page.messages.add_message(
            text="Bonjour, je suis NURU V8+. Comment puis-je vous aider ?",
            role="assistant",
        )

        self._pages.setCurrentIndex(0)
        self._sidebar.set_active("console")

        # Initialiser les infos du footer sidebar
        model_name = "phi-4-mini-4bit"
        try:
            from src.config import config
            model_name = config.local_model.split("/")[-1]
        except Exception:
            pass
        self._sidebar.set_model_info(model_name, "Prêt")

        logger.info("CyberDashboard V10 — prêt.")

    # ══════════════════════════════════════════════════════════════════════
    #  BUILD
    # ══════════════════════════════════════════════════════════════════════

    def _build_window(self) -> None:
        """Configure les propriétés de la fenêtre."""
        self.setWindowTitle("NURU V10")
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

        # Pages réelles (index 1..7)
        self._placeholder_map: dict[str, QWidget] = {}
        for slug, (title, desc) in PLACEHOLDER_PAGES.items():
            # Mapping slug → classe réelle
            if slug == "sessions":
                cls = SessionsPage
            elif slug == "documents":
                cls = DocumentsPage
            elif slug == "memory":
                cls = MemoryPage
            elif slug == "logs":
                cls = LogsPage
            elif slug == "settings":
                cls = SettingsPage
            elif slug == "v6_system":
                cls = SystemPage
            elif slug == "diagnostics":
                cls = DiagnosticsPage
            else:
                cls = None  # nuru_brain, stats_v10, tools_v10 → placeholder / V10/V9

            if cls is not None:
                try:
                    if slug == "v6_system":
                        page = cls(config=None, core=self._core, parent=self)
                    else:
                        page = cls(parent=self)
                except Exception as e:
                    logger.warning("Page %s non disponible: %s — fallback placeholder", slug, e)
                    page = PlaceholderPage(title, desc)
            else:
                page = PlaceholderPage(title, desc)
            self._pages.addWidget(page)
            self._placeholder_map[slug] = page

        # ── V9 Pages ──
        self._v9_pages: dict[str, QWidget] = {}
        v9_entries = [
            ("agent",     "Agent",     "Supervision de l'agent ReAct en temps réel", AgentStatusWidget),
            ("memory_v9", "Mémoire V9", "Explorateur des 6 types de mémoire", MemoryExplorer),
            ("tasks",     "Tâches",    "Tâches en cours, terminées et interrompues", TaskListWidget),
            ("feedback",  "Feedback",  "Historique des retours utilisateur", None),
        ]
        for slug, title, desc, cls in v9_entries:
            if cls is not None:
                try:
                    page = cls(parent=self)
                except Exception as e:
                    logger.warning("Page V9 %s non disponible: %s — fallback placeholder", slug, e)
                    page = PlaceholderPage(title, desc)
            else:
                page = PlaceholderPage(title, desc)
            self._pages.addWidget(page)
            self._v9_pages[slug] = page

        # ── V10 Pages ──
        self._v10_pages: dict[str, QWidget] = {}
        v10_entries = [
            ("stats_v10", "Stats V10", "Statistiques temps réel", StatsPage),
            ("tools_v10", "Outils V10", "Test des outils", ToolTester),
        ]
        for slug, title, desc, cls in v10_entries:
            if cls is not None:
                try:
                    page = cls(parent=self)
                except Exception as e:
                    logger.warning("Page V10 %s non disponible: %s — fallback placeholder", slug, e)
                    page = PlaceholderPage(title, desc)
            else:
                page = PlaceholderPage(title, desc)
            self._pages.addWidget(page)
            self._v10_pages[slug] = page

        self._main_layout.addWidget(self._pages, stretch=1)

        # ── V9 Backends (modules réels) ──
        self._v9_memory_manager = None
        self._v9_feedback_collector = None
        self._v9_orchestrator = None

        try:
            from src.memory.manager import MemoryManager
            db_path = Path.home() / ".nuru" / "memory_v9.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._v9_memory_manager = MemoryManager(db_path=str(db_path))
            logger.info("MemoryManager V9 initialisé")
        except Exception as e:
            logger.warning("MemoryManager V9 non disponible: %s", e)

        try:
            from src.learning.feedback import FeedbackCollector
            self._v9_feedback_collector = FeedbackCollector()
            logger.info("FeedbackCollector initialisé")
        except Exception as e:
            logger.warning("FeedbackCollector non disponible: %s", e)

        try:
            from src.agent.orchestrator import AgentOrchestrator
            self._v9_orchestrator = AgentOrchestrator(
                memory_manager=self._v9_memory_manager,
            )
            logger.info("AgentOrchestrator initialisé")
        except Exception as e:
            logger.warning("AgentOrchestrator non disponible: %s", e)

        # ── 3. Right Panel — Diagnostic RAG ──
        if RightPanelDiagnostic is not None:
            self._metrics = RightPanelDiagnostic()
        else:
            self._metrics = QWidget()
            self._metrics.setObjectName("RightPanelDiagnostic")
            self._metrics.setFixedWidth(300)
            layout = QVBoxLayout(self._metrics)
            layout.addWidget(QLabel("Diagnostic non disponible"))
        self._main_layout.addWidget(self._metrics)

        # ── 4. RAGDiagnosticViewModel ──
        self._rag_diagnostic_vm: RAGDiagnosticViewModel | None = None
        if RAGDiagnosticViewModel is not None:
            self._rag_diagnostic_vm = RAGDiagnosticViewModel()
            self._rag_diagnostic_vm.updated.connect(self._on_rag_vm_updated)

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

        # Timer V9 (mise à jour des pages V9)
        self._v9_timer = QTimer(self)
        self._v9_timer.setInterval(5000)  # 5 s
        self._v9_timer.timeout.connect(self._update_v9_pages)
        self._v9_timer.start()

    # ══════════════════════════════════════════════════════════════════════
    #  V9 PAGES — DATA LOADING
    # ══════════════════════════════════════════════════════════════════════

    def _load_v9_page_data(self, slug: str, page: QWidget) -> None:
        """Charge les données réelles dans une page V9 au moment de la navigation."""
        try:
            if slug == "memory_v9" and self._v9_memory_manager and hasattr(page, "set_data"):
                data = {
                    "episodic": [
                        {"text": h, "timestamp": ""}
                        for h in (self._v9_memory_manager.get_recent_history() or [])
                    ],
                    "semantic": [
                        {"text": s, "timestamp": ""}
                        for s in (self._v9_memory_manager.get_full_context().get("semantic", []) if hasattr(self._v9_memory_manager, 'get_full_context') else [])
                    ],
                    "user": [
                        {"key": k, "value": v}
                        for k, v in self._v9_memory_manager.get_user_profile().items()
                    ] if isinstance(self._v9_memory_manager.get_user_profile(), dict) else [],
                    "error": [
                        {"text": e, "timestamp": ""}
                        for e in (self._v9_memory_manager.check_errors() or [])
                    ],
                }
                page.set_data(data)

            elif slug == "tasks" and hasattr(page, "set_tasks"):
                import json
                import sqlite3 as _sqlite3
                db_path = Path.home() / ".nuru" / "task_states.db"
                if db_path.exists():
                    conn = _sqlite3.connect(str(db_path))
                    rows = conn.execute(
                        "SELECT task_id, state, status, created_at FROM task_states ORDER BY created_at DESC LIMIT 20"
                    ).fetchall()
                    conn.close()
                    tasks = []
                    for r in rows:
                        try:
                            state_data = json.loads(r[1]) if r[1] else {}
                        except Exception:
                            state_data = {}
                        tasks.append({
                            "id": r[0],
                            "description": state_data.get("current_goal", r[0]),
                            "status": r[2],
                            "created": r[3],
                        })
                    page.set_tasks(tasks)

            elif slug == "feedback" and self._v9_feedback_collector and hasattr(page, "set_data"):
                stats = self._v9_feedback_collector.get_stats()
                recent = self._v9_feedback_collector.get_recent()
                page.set_data({"stats": stats, "recent": recent})

        except Exception as e:
            logger.debug("Erreur chargement page V9 %s: %s", slug, e)

    def _update_v9_pages(self) -> None:
        """Met à jour les pages V9 avec les données réelles (appelé par timer)."""
        current_widget = self._pages.currentWidget()
        if current_widget is None:
            return

        # Identifier la page active
        for slug, page in self._v9_pages.items():
            if page is current_widget:
                self._load_v9_page_data(slug, page)
                break

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
        # Pages V9
        if slug in self._v9_pages:
            page = self._v9_pages[slug]
            # Charger les données immédiatement
            self._load_v9_page_data(slug, page)
            self._pages.setCurrentWidget(page)
            return

        # Pages V10
        if slug in self._v10_pages:
            page = self._v10_pages[slug]
            self._pages.setCurrentWidget(page)
            return

        if slug == "console":
            self._pages.setCurrentIndex(0)
            return

        page = self._placeholder_map.get(slug)
        if page:
            idx = self._pages.indexOf(page)
            if idx >= 0:
                self._pages.setCurrentIndex(idx)

    def _wire_page_dependencies(self) -> None:
        """Connecte les sources de données aux pages qui en ont besoin.

        Si le core est disponible, utilise ses références.
        Sinon, crée les instances directement (MemoryStore, RAGEngine).
        """
        session_page = self._placeholder_map.get("sessions")
        doc_page = self._placeholder_map.get("documents")
        memory_page = self._placeholder_map.get("memory")

        # Récupérer ou créer les sources de données
        memory_store = None
        rag_engine = None
        ingestion = None

        if self._core is not None:
            # NuruCore utilise memory / rag (pas memory_store / rag_engine)
            memory_store = getattr(self._core, "memory_store", None) or getattr(self._core, "memory", None)
            rag_engine = getattr(self._core, "rag_engine", None) or getattr(self._core, "rag", None)
            ingestion = getattr(self._core, "ingestion", None)
            if memory_store is not None:
                logger.info("MemoryStore fourni par NuruCore")
            if rag_engine is not None:
                logger.info("RAGEngine fourni par NuruCore")
            if ingestion is not None:
                logger.info("IngestionEngine fourni par NuruCore")
        else:
            # Mode autonome : créer les instances directement
            try:
                from src.memory_store import MemoryStore
                memory_store = MemoryStore()
                logger.info("MemoryStore créé (mode autonome)")
            except Exception as e:
                logger.warning("MemoryStore non disponible: %s", e)
            try:
                from src.rag_engine import RAGEngine
                rag_engine = RAGEngine()
                logger.info("RAGEngine créé (mode autonome)")
            except Exception as e:
                logger.warning("RAGEngine non disponible: %s", e)
            try:
                from src.ingestion import IngestionEngine
                ingestion = IngestionEngine()
                logger.info("IngestionEngine créé (mode autonome)")
            except Exception as e:
                logger.warning("IngestionEngine non disponible: %s", e)

        # SessionsPage ← memory_store
        if session_page is not None:
            session_page.memory_store = memory_store
            if memory_store is not None:
                try:
                    session_page.load_sessions()
                except Exception as e:
                    logger.debug("load_sessions: %s", e)

        # DocumentsPage ← rag_engine + ingestion
        if doc_page is not None:
            doc_page.rag_engine = rag_engine
            doc_page.ingestion = ingestion
            if rag_engine is not None:
                try:
                    doc_page.load_documents()
                except Exception as e:
                    logger.debug("load_documents: %s", e)

        # MemoryPage ← memory_store
        if memory_page is not None:
            memory_page.memory_store = memory_store
            if memory_store is not None and hasattr(memory_page, "load_data"):
                try:
                    memory_page.load_data()
                except Exception as e:
                    logger.debug("load_data: %s", e)

        # V9 MemoryExplorer ← V9 MemoryManager
        v9_memory_page = self._v9_pages.get("memory_v9")
        if v9_memory_page is not None and self._v9_memory_manager is not None:
            if hasattr(v9_memory_page, "set_manager"):
                try:
                    v9_memory_page.set_manager(self._v9_memory_manager)
                except Exception:
                    pass

        # Charger les données V9 au démarrage
        for slug in list(self._v9_pages):
            page = self._v9_pages.get(slug)
            if page is not None:
                self._load_v9_page_data(slug, page)

    def _on_query(self, text: str, strict_mode: bool) -> None:
        """Traite une requête utilisateur en temps réel.

        Avec debounce : ignore les doubles clics.
        Si ``self._core`` est défini, utilise ``InferenceWorker`` (thread pool)
        pour un streaming non-bloquant. Sinon, mode démo.
        """
        logger.info("Requête reçue : text=%s, strict=%s", text[:60], strict_mode)

        # ── Debounce : ignorer si déjà en cours ──
        if self._is_processing:
            logger.info("Requête ignorée (déjà en cours de traitement)")
            return
        self._is_processing = True

        # Réinitialiser les compteurs de tokens
        self._total_tokens_received = 0
        self._token_timestamps.clear()
        self._last_llm_update = 0.0

        if self._core is not None and HAS_WORKER:
            # ── Mode réel : InferenceWorker ──
            self._current_query = text
            self._current_strict = strict_mode

            # Ajouter le message utilisateur + bulle assistant vide
            self.console_page.messages.add_message(text=text, role="user")
            self.console_page.messages.show_typing()

            # Créer et lancer le worker
            worker = InferenceWorker(self._core, text)
            worker.signals.token_received.connect(self._on_token)
            worker.signals.rag_data.connect(self._on_rag_data)
            worker.signals.finished.connect(self._on_generation_finished)
            worker.signals.error.connect(self._on_generation_error)
            QThreadPool.globalInstance().start(worker)
        else:
            # ── Mode démo / fallback ──
            self.console_page.messages.show_typing()
            QTimer.singleShot(800, lambda: self._demo_response(text))

    def _on_token(self, token: str) -> None:
        """Reçoit un token du stream LLM."""
        import time as _time

        now = _time.time()
        self._total_tokens_received += 1
        self._token_timestamps.append(now)

        if not hasattr(self, "_current_bubble") or self._current_bubble is None:
            self.console_page.messages.hide_typing()
            row = self.console_page.messages.add_message(text="", role="assistant")
            self._current_bubble = row

        self._current_bubble.append_text(token)

        # Scroll to bottom à chaque token
        self.console_page.messages._scroll_to_bottom()

        # Mettre à jour la métrique LLM toutes les 500ms
        if now - self._last_llm_update > 0.5:
            cutoff = now - 3.0
            recent = [t for t in self._token_timestamps if t > cutoff]
            window = min(3.0, now - cutoff)
            tok_s = len(recent) / window if window > 0 else 0.0
            if hasattr(self._metrics, "set_llm"):
                self._metrics.set_llm(tok_s, self._total_tokens_received)
            self._last_llm_update = now

    def _on_rag_vm_updated(self) -> None:
        """Callback quand RAGDiagnosticViewModel est mis à jour.

        Route les données vers RightPanelDiagnostic.
        """
        if hasattr(self._metrics, "update_from_diagnostics_viewmodel"):
            self._metrics.update_from_diagnostics_viewmodel()

    def _on_rag_data(self, rag_data: dict) -> None:
        """Reçoit les métadonnées RAG après génération."""
        try:
            if not rag_data:
                return
            top_score = rag_data.get("top_score", 0.0)
            docs_found = rag_data.get("documents_found", 0)
            sources = rag_data.get("sources", [])

            if top_score > 0:
                self._rag_queries_total += 1
                self._rag_scores_session.append(top_score)
                if docs_found:
                    self._rag_docs_found.append(docs_found)

                # Mettre à jour la barre de confiance sur la bulle
                if hasattr(self, "_current_bubble") and self._current_bubble:
                    self._current_bubble.set_rag_score(top_score)

                # Mettre à jour le header de confiance
                self.console_page.header.set_confidence(top_score)

                # Stratégie active dans le MetricsPanel
                if hasattr(self._metrics, "set_strategy"):
                    strict_label = "STRICT" if getattr(self, "_current_strict", False) else "HYBRID"
                    self._metrics.set_strategy(strict_label, "phi-4-mini-4bit")

                # Feeder le RAGDiagnosticViewModel
                if self._rag_diagnostic_vm is not None:
                    try:
                        from src.rag.diagnostics import RAGDiagnostic

                        diag = RAGDiagnostic(query=getattr(self, "_current_query", ""))
                        diag.set_confidence(
                            rag_data.get("confidence_label", "MOYENNE"),
                            rag_data.get("documents_found", 0),
                        )
                        # Ajouter les stratégies depuis le dict
                        strategies = rag_data.get("strategies", [])
                        for s in strategies:
                            if isinstance(s, dict):
                                diag.log_strategy(
                                    s.get("name", "?"),
                                    s.get("found", 0),
                                    s.get("top_score", 0.0),
                                    s.get("hit", False),
                                    s.get("timing_ms", 0.0),
                                )
                        diag.set_verdict(rag_data.get("verdict", ""))
                        self._rag_diagnostic_vm.update_from_diagnostic(diag)
                    except Exception as e:
                        logger.debug("RAGDiagnosticViewModel update: %s", e)
        except Exception as e:
            logger.debug("RAG data callback: %s", e)

    def _on_generation_finished(self, full_response: str) -> None:
        """Fin de génération."""
        self.console_page.messages.hide_typing()
        self._is_processing = False

        # Mettre à jour métrique LLM finale
        if self._total_tokens_received > 0 and self._token_timestamps:
            import time as _time
            elapsed = _time.time() - self._token_timestamps[0]
            tok_s = self._total_tokens_received / elapsed if elapsed > 0 else 0.0
            if hasattr(self._metrics, "set_llm"):
                self._metrics.set_llm(tok_s, self._total_tokens_received,
                                      f"{tok_s:.1f} tok/s" if tok_s > 0 else "Terminé")

        # Scroll final
        self.console_page.messages._scroll_to_bottom()
        self._current_bubble = None
        logger.info("Génération terminée (%d chars, %d tokens)", len(full_response), self._total_tokens_received)

    def _on_generation_error(self, error_msg: str) -> None:
        """Erreur de génération."""
        self.console_page.messages.hide_typing()
        self._is_processing = False
        if hasattr(self, "_current_bubble") and self._current_bubble:
            self._current_bubble.append_text(f"\n\n[Erreur: {error_msg}]")
        self._current_bubble = None
        logger.error("Erreur génération: %s", error_msg)

    def _demo_response(self, query: str) -> None:
        """Réponse simulée en mode démo."""
        self.console_page.messages.hide_typing()
        responses = {
            "bonjour": "Bonjour ! Je suis NURU V8+. Comment puis-je vous aider ?",
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
        self._current_bubble = None
        self._current_query = ""
        self._current_strict = False
        self._is_processing = False
        self._total_tokens_received = 0
        self._token_timestamps.clear()
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
        """Met à jour les métriques système (RAM, LLM, RAG) toutes les secondes.

        Module 3 : draine l'EventBus et route chaque event vers RightPanelDiagnostic.
        """
        import time as _time
        try:
            now = _time.time()

            # ── 0. EventBus drain (Module 3) ──
            if hasattr(self._metrics, "update_from_events"):
                self._metrics.update_from_events()

            # 1. RAM système
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024**3)
            used_gb = mem.used / (1024**3)
            ram_pct = mem.percent

            if hasattr(self._metrics, "set_ram"):
                self._metrics.set_ram(ram_pct, f"{used_gb:.1f}", f"{total_gb:.0f}")

            # 2. Stratégie active depuis config
            model_name = "phi-4-mini-4bit"
            try:
                from src.config import config
                model_name = config.local_model.split("/")[-1]
            except Exception:
                pass
            rag_mode = "STRICT" if getattr(self, "_current_strict", False) else "HYBRID"
            if hasattr(self._metrics, "set_strategy"):
                self._metrics.set_strategy(rag_mode, model_name)

            # 3. Score RAG moyen (uniquement si requêtes traitées)
            if hasattr(self._metrics, "set_rag_score"):
                if self._rag_scores_session:
                    avg_rag = sum(self._rag_scores_session) / len(self._rag_scores_session)
                    self._metrics.set_rag_score(avg_rag)
                elif not self._is_processing:
                    # Reset à zéro si pas de requête active
                    self._metrics.set_rag_score(0.0)

            # 4. Mise à jour du footer sidebar + cloud badge
            if hasattr(self._sidebar, "set_model_info"):
                queries = len(self._rag_scores_session)
                status = "Actif" if self._is_processing else "En attente"
                self._sidebar.set_model_info(model_name, status, queries)

            # 5. Métrique LLM temps réel ou reset
            if hasattr(self._metrics, "set_llm"):
                if self._is_processing and self._total_tokens_received > 0:
                    cutoff = now - 3.0
                    recent = [t for t in self._token_timestamps if t > cutoff]
                    window = min(3.0, now - self._token_timestamps[0]) if self._token_timestamps else 1.0
                    tok_s = len(recent) / window if window > 0 else 0.0
                    self._metrics.set_llm(tok_s, self._total_tokens_received)
                else:
                    # Reset quand la génération est terminée
                    self._metrics.set_llm(0.0, 0, "0 tok/s")

            # 6. Traces depuis le core
            if self._core is not None and hasattr(self._metrics, "set_traces"):
                try:
                    if hasattr(self._core, "orchestrator") and \
                       hasattr(self._core.orchestrator, "trace_collector"):
                        tc = self._core.orchestrator.trace_collector
                        traces = tc.count() if hasattr(tc, "count") else 0
                        self._metrics.set_traces(traces)
                except Exception:
                    pass

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

    # Tentative d'initialisation du backend NuruCore
    core = None
    try:
        from src.nuru_core import NuruCore
        core = NuruCore()
        logger.info("✅ NuruCore initialisé — mode réel")
    except Exception as e:
        logger.warning(f"NuruCore non disponible: {e} — mode démo")

    win = CyberDashboard(core=core)
    win.show()

    sys.exit(app.exec())
