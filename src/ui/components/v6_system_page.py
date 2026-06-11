"""
NURU V10 — System Page : État en temps réel des modules V10.

Modules affichés :
- 🧠 Mémoire V9 : EpisodicMemory, SemanticMemory, UserMemory, ErrorMemory, MemoryRetriever, ConsolidationWorker
- 🤖 Agent Loop : AgentOrchestrator, TaskPlanner, TaskExecutor, TaskVerifier, ErrorRecovery, ResumeManager
- 📊 Feedback : FeedbackCollector, PerformanceTracker, StrategyOptimizer, SelfEvaluator
- 🧠 Raisonnement : ReflexionEngine, SelfConsistency, ConfidenceCalibrator
- 🔧 Outils : ToolRegistry, ToolExecutor, DocumentGenerator (Word/PDF/PPTX/XLSX)
- 🔍 Web Research : WebResearcher, SearchOptimizer
- 📈 Dashboard V9 : AgentStatusWidget, MemoryExplorer, FeedbackBar, TaskListWidget
"""
import importlib
import logging
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QPushButton, QComboBox,
    QCheckBox, QProgressBar, QSizePolicy, QGridLayout,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)

# ── V10 Module Registry ──────────────────────────────────────────
V10_MODULES = [
    {
        "category": "🧠 Mémoire V9",
        "color": "#A78BFA",
        "modules": [
            {"name": "EpisodicMemory", "import": "src.memory.episodic_memory", "desc": "Mémoire épisodique — souvenirs datés et contextuels"},
            {"name": "SemanticMemory", "import": "src.memory.semantic_memory", "desc": "Mémoire sémantique — connaissances structurées"},
            {"name": "UserMemory", "import": "src.memory.user_memory", "desc": "Mémoire utilisateur — préférences et profile"},
            {"name": "ErrorMemory", "import": "src.memory.error_memory", "desc": "Mémoire d'erreurs — patterns d'échec et correctifs"},
            {"name": "MemoryRetriever", "import": "src.memory.retriever", "desc": "Retrieval mémoire — recherche multi-sources"},
            {"name": "ConsolidationWorker", "import": "src.memory.consolidation", "desc": "Consolidation — archivage et nettoyage mémoire"},
        ],
    },
    {
        "category": "🤖 Agent Loop",
        "color": "#39FF14",
        "modules": [
            {"name": "AgentOrchestrator", "import": "src.agent.orchestrator", "desc": "Orchestrateur — pilotage de la boucle agent"},
            {"name": "TaskPlanner", "import": "src.agent.planner", "desc": "Planificateur — décomposition en sous-tâches"},
            {"name": "TaskExecutor", "import": "src.agent.executor", "desc": "Exécuteur — exécution des étapes planifiées"},
            {"name": "TaskVerifier", "import": "src.agent.verifier", "desc": "Vérificateur — validation des résultats"},
            {"name": "ErrorRecovery", "import": "src.agent.error_recovery", "desc": "Récupération — retry et fallback intelligent"},
            {"name": "ResumeManager", "import": "src.agent.resume", "desc": "Reprise — sauvegarde/restauration d'état"},
        ],
    },
    {
        "category": "📊 Feedback",
        "color": "#FF00FF",
        "modules": [
            {"name": "FeedbackCollector", "import": "src.feedback.collector", "desc": "Collecte — feedback utilisateur et auto-évaluation"},
            {"name": "PerformanceTracker", "import": "src.feedback.tracker", "desc": "Suivi perf — métriques de qualité temps réel"},
            {"name": "StrategyOptimizer", "import": "src.feedback.optimizer", "desc": "Optimisation — ajustement dynamique des stratégies"},
            {"name": "SelfEvaluator", "import": "src.feedback.evaluator", "desc": "Auto-évaluation — scoring de la réponse"},
        ],
    },
    {
        "category": "🧠 Raisonnement",
        "color": "#FFB000",
        "modules": [
            {"name": "ReflexionEngine", "import": "src.reasoning.reflexion", "desc": "Réflexion — boucle de rétroaction sur les réponses"},
            {"name": "SelfConsistency", "import": "src.reasoning.consistency", "desc": "Cohérence — vérification interne des réponses"},
            {"name": "ConfidenceCalibrator", "import": "src.reasoning.confidence", "desc": "Confiance — calibrage du niveau de certitude"},
        ],
    },
    {
        "category": "🔧 Outils",
        "color": "#00F2FF",
        "modules": [
            {"name": "ToolRegistry", "import": "src.tools.registry", "desc": "Registre — catalogue d'outils disponibles"},
            {"name": "ToolExecutor", "import": "src.tools.executor", "desc": "Exécuteur — appel et gestion des outils"},
            {"name": "DocumentGenerator", "import": "src.tools.doc_generator", "desc": "Générateur docs — Word, PDF, PPTX, XLSX"},
        ],
    },
    {
        "category": "🔍 Web Research",
        "color": "#E0E7FF",
        "modules": [
            {"name": "WebResearcher", "import": "src.research.web_researcher", "desc": "Recherche web — requêtes et extraction"},
            {"name": "SearchOptimizer", "import": "src.research.search_optimizer", "desc": "Optimisation — reformulation et scoring"},
        ],
    },
    {
        "category": "📈 Dashboard V9",
        "color": "#39FF14",
        "modules": [
            {"name": "AgentStatusWidget", "import": "src.ui.dashboard.agent_status", "desc": "Widget état agent — statut et progression"},
            {"name": "MemoryExplorer", "import": "src.ui.dashboard.memory_explorer", "desc": "Explorateur mémoire — visualisation mémoire"},
            {"name": "FeedbackBar", "import": "src.ui.dashboard.feedback_bar", "desc": "Barre feedback — score et tendance"},
            {"name": "TaskListWidget", "import": "src.ui.dashboard.task_list", "desc": "Liste tâches — historique et suivi"},
        ],
    },
]


def _estimate_module_size(module_name: str) -> str:
    """Estime la taille d'un module Python (fichier .py) en Ko/Mo."""
    # Chercher le fichier .py correspondant dans le projet
    try:
        # Conversion basique du nom de module en chemin
        parts = module_name.split(".")
        # On cherche dans src/ principalement
        src_root = Path(__file__).resolve().parent.parent.parent  # src/
        candidate = src_root / Path(*parts).with_suffix(".py")
        if candidate.exists():
            size_bytes = candidate.stat().st_size
            if size_bytes >= 1_048_576:
                return f"{size_bytes / 1_048_576:.1f} Mo"
            else:
                return f"{size_bytes / 1024:.0f} Ko"
    except Exception:
        pass
    return "~1 Ko"


class SystemModuleCard(QFrame):
    """Carte d'état pour un module V10."""

    def __init__(self, title: str, icon: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setStyleSheet(f"""
            #MetricCard {{
                background-color: rgba(0, 0, 0, 0.6);
                border: 2px solid {color};
                border-radius: 8px;
                padding: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 20px;")
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"""
            color: {color}; font-weight: bold; font-size: 13px;
        """)
        self.status_lbl = QLabel("●")
        self.status_lbl.setStyleSheet("color: #6b7280; font-size: 14px;")
        header.addWidget(icon_lbl)
        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(self.status_lbl)
        layout.addLayout(header)

        # Corps des métriques
        self.metrics_container = QWidget()
        self.metrics_layout = QVBoxLayout(self.metrics_container)
        self.metrics_layout.setSpacing(4)
        self.metrics_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.metrics_container)

    def set_status(self, active: bool):
        color = "#39FF14" if active else "#ef4444"
        text = "ACTIF" if active else "INACTIF"
        self.status_lbl.setStyleSheet(f"color: {color}; font-size: 14px;")
        self.status_lbl.setText(f"● {text}")

    def add_metric(self, label: str, value: str, color: str = "#A78BFA"):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        val = QLabel(value)
        val.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(val)
        self.metrics_layout.addLayout(row)


class V10ControlPanel(QFrame):
    """Panneau de contrôle des modules V10 avec persistance immédiate."""

    toggled = Signal(str, bool)  # module_name, enabled

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.setObjectName("MetricCard")
        self.setStyleSheet("""
            #MetricCard {
                background-color: rgba(0, 0, 0, 0.6);
                border: 2px solid #FF00FF;
                border-radius: 8px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("⚙️ Contrôle des Modules V10")
        title.setStyleSheet("color: #FF00FF; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        self.toggles = {}
        self.status_icons = {}
        modules = [
            ("🧠 Mémoire V9", "memory"),
            ("🤖 Agent Loop", "agent"),
            ("📊 Feedback", "feedback"),
            ("🧠 Raisonnement", "reasoning"),
            ("🔧 Outils", "tools"),
            ("🔍 Web Research", "web_research"),
            ("📈 Dashboard V9", "dashboard"),
        ]

        for label, name in modules:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel(label)
            lbl.setStyleSheet("color: #E0E7FF; font-size: 12px;")

            # Indicateur visuel d'état réel
            status_icon = QLabel("✅")
            status_icon.setStyleSheet("font-size: 14px;")
            self.status_icons[name] = status_icon

            cb = QCheckBox()
            initial = self._get_module_state(name)
            cb.setChecked(initial)
            self._update_status_icon(name, initial)
            cb.setStyleSheet("""
                QCheckBox::indicator {
                    width: 16px; height: 16px;
                    border: 2px solid #39FF14;
                    border-radius: 3px;
                    background: transparent;
                }
                QCheckBox::indicator:checked {
                    background-color: #39FF14;
                }
            """)
            cb.toggled.connect(lambda checked, n=name: self.toggled.emit(n, checked))
            self.toggles[name] = cb

            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(status_icon)
            row.addSpacing(4)
            row.addWidget(cb)
            layout.addLayout(row)

        # Sélecteur de mode hybride
        strategy_row = QHBoxLayout()
        strategy_lbl = QLabel("Mode hybride:")
        strategy_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["cloud_first", "local_first", "offline_only"])
        if config and hasattr(config, 'hybrid_mode'):
            idx = self.strategy_combo.findText(config.hybrid_mode)
            if idx >= 0:
                self.strategy_combo.setCurrentIndex(idx)
        self.strategy_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(0, 0, 0, 0.4);
                border: 1px solid #FF00FF;
                border-radius: 4px;
                color: #E0E7FF;
                padding: 4px 8px;
                font-size: 11px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        self.strategy_combo.currentTextChanged.connect(self._on_strategy_changed)

        strategy_row.addWidget(strategy_lbl)
        strategy_row.addWidget(self.strategy_combo)
        strategy_row.addStretch()
        layout.addLayout(strategy_row)

    def _get_module_state(self, name: str) -> bool:
        """Lit l'état d'un module depuis la config."""
        if self.config is None:
            return False
        attr = getattr(self.config, 'MODULE_ATTR_MAP', {}).get(name)
        if attr and hasattr(self.config, attr):
            return getattr(self.config, attr)
        return False

    def _update_status_icon(self, name: str, enabled: bool):
        """Met à jour l'icône d'état visuel."""
        icon = self.status_icons.get(name)
        if icon:
            icon.setText("✅" if enabled else "❌")

    def update_from_config(self):
        """Synchronise tous les toggles avec la config (après changement externe)."""
        for name, cb in self.toggles.items():
            state = self._get_module_state(name)
            cb.setChecked(state)
            self._update_status_icon(name, state)

    def _on_strategy_changed(self, text: str):
        """Persiste le changement de mode hybride dans la config."""
        if self.config and hasattr(self.config, 'set_hybrid_mode'):
            self.config.set_hybrid_mode(text)
            logger.info(f"Mode hybride changé → {text}")


class SystemPage(QWidget):
    """Page d'état des modules V10."""

    def __init__(self, config=None, core=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.core = core
        self._module_cards = {}
        self._setup_ui()

        # Timer de rafraîchissement
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(2000)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(16)

        # Titre
        title = QLabel("📊 NURU V10 — État du Système")
        title.setStyleSheet("""
            font-size: 22px; font-weight: bold; color: #39FF14;
            letter-spacing: 2px;
        """)
        layout.addWidget(title)

        subtitle = QLabel("État en temps réel des modules Sprints 1–8")
        subtitle.setStyleSheet("color: #6b7280; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        # Scroll area pour la grille de modules
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none; background: transparent;")
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")

        # Grille de modules V10
        grid = QGridLayout(scroll_widget)
        grid.setSpacing(12)

        col = 0
        row = 0
        for cat_info in V10_MODULES:
            category = cat_info["category"]
            color = cat_info["color"]

            # Carte catégorie
            cat_card = SystemModuleCard(category, category.split()[0], color)
            # Vérifier si au moins un module est importable
            any_active = False
            for mod in cat_info["modules"]:
                try:
                    importlib.import_module(mod["import"])
                    cat_card.add_metric(
                        f"✅ {mod['name']}",
                        _estimate_module_size(mod["import"]),
                        "#39FF14"
                    )
                    any_active = True
                except Exception:
                    cat_card.add_metric(
                        f"❌ {mod['name']}",
                        _estimate_module_size(mod["import"]),
                        "#ef4444"
                    )
            cat_card.set_status(any_active)
            # Nombre de sous-modules
            active_count = sum(1 for m in cat_info["modules"] if _is_importable(m["import"]))
            cat_card.add_metric(
                "Sous-modules",
                f"{active_count}/{len(cat_info['modules'])}",
                "#FFB000"
            )

            grid.addWidget(cat_card, row, col)
            self._module_cards[category] = cat_card

            col += 1
            if col >= 2:
                col = 0
                row += 1

        layout.addWidget(scroll_widget)

        # Panneau de contrôle
        self.control_panel = V10ControlPanel(config=self.config)
        self.control_panel.toggled.connect(self._on_module_toggle)
        layout.addWidget(self.control_panel)

        # Label du mode actif
        self.mode_label = QLabel("Mode actuel : cloud_first (RAG local → Cloud synthèse)")
        self.mode_label.setStyleSheet("""
            color: #FFB000; font-size: 12px; padding: 8px;
            background-color: rgba(255, 176, 0, 0.05);
            border: 1px solid rgba(255, 176, 0, 0.2);
            border-radius: 8px;
        """)
        layout.addWidget(self.mode_label)

        layout.addStretch()

    def _refresh(self):
        """Met à jour les statuts des modules depuis les imports réels."""
        try:
            for cat_info in V10_MODULES:
                category = cat_info["category"]
                card = self._module_cards.get(category)
                if not card:
                    continue

                any_active = False
                for mod in cat_info["modules"]:
                    importable = _is_importable(mod["import"])
                    if importable:
                        any_active = True
                card.set_status(any_active)
        except Exception as e:
            logger.debug(f"SystemPage V10 refresh: {e}")

    def _on_module_toggle(self, name: str, enabled: bool):
        """Persiste le changement d'état d'un module V10 dans settings.yaml."""
        logger.info(f"Module {name} → {'ON' if enabled else 'OFF'}")

        if self.config and hasattr(self.config, 'set_module_enabled'):
            success = self.config.set_module_enabled(name, enabled)
            if success:
                self.control_panel._update_status_icon(name, enabled)
                logger.info(f"Module {name} persistant → {'✅' if enabled else '❌'}")
            else:
                logger.error(f"Échec de la persistance pour {name}")
                cb = self.control_panel.toggles.get(name)
                if cb:
                    cb.setChecked(not enabled)


def _is_importable(module_path: str) -> bool:
    """Vérifie si un module Python est importable."""
    try:
        importlib.import_module(module_path)
        return True
    except Exception:
        return False
