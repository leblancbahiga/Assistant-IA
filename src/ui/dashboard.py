"""
NURU Cyber-Dashboard — macOS Native Dark Theme
Three-panel layout: Sidebar | Central Chat | Top-Right Metrics Overlay
"""
import sys
import os
import datetime
from pathlib import Path

import psutil
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QFrame, QProgressBar, QStackedWidget,
    QSizePolicy, QPlainTextEdit, QScrollArea, QTextEdit,
    QLineEdit, QSpacerItem, QSizePolicy as QSizePolicyEnum,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, Slot, Signal, QThread, QSize, QPoint, QPropertyAnimation, QRect, QEasingCurve
from PySide6.QtGui import QFont, QIcon, QColor, QPalette

# Setup path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from src.ui.components.metric_card import MetricCard
    from src.ui.components.circular_gauge import CircularGauge
    from src.ui.components.logo_widget import AnimatedLogo
    from src.ui.components.console_page import ConsolePage
    from src.ui.components.conversations_page import ConversationsPage
    from src.ui.components.sessions_page import SessionsPage
    from src.ui.components.memory_page import MemoryPage
    from src.ui.components.documents_page import DocumentsPage
    from src.ui.components.plugins_page import PluginsPage
    from src.ui.components.settings_page import SettingsPage
    from src.ui.components.logs_page import LogsPage
    from src.ui.components.api_docs_page import ApiDocsPage
    from src.ui.components.guides_page import GuidesPage
    from src.ui.components.prompts_page import PromptsPage
    from src.ui.components.v6_system_page import SystemPage
    from src.config import config
    from src.nuru_core import NuruCore
    from src.core.events import EventBus
    from src.ui.state.app_state import AppState
    from src.ui.state.actions import UIActions
    from src.ui.viewmodels.telemetry_vm import TelemetryViewModel
except ImportError as e:
    logger.error(f"Import error: {e}")
    raise

class MetricsOverlay(QFrame):
    _visible = True  # état de visibilité

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MetricsOverlay")
        self.setFixedWidth(340)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # ── Bouton de réduction ──
        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.addStretch()
        self.toggle_btn = QPushButton("—")
        self.toggle_btn.setObjectName("MinimizeBtn")
        self.toggle_btn.setFixedSize(24, 20)
        self.toggle_btn.clicked.connect(self._toggle_visibility)
        toggle_layout.addWidget(self.toggle_btn)
        layout.addLayout(toggle_layout)
        
        # Conteneur pour le contenu à masquer/afficher
        self.content_widget = QWidget()
        self.content_widget.setObjectName("MetricsContent")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(12)
        layout.addWidget(self.content_widget)
        
        # RAM
        self.ram_container = QFrame()
        self.ram_container.setObjectName("MetricsContainer")
        ram_layout = QHBoxLayout(self.ram_container)
        ram_layout.setContentsMargins(15, 8, 15, 8)
        
        self.ram_label = QLabel("SYS RAM | ...")
        self.ram_label.setObjectName("MetricsText")
        
        self.ram_bar = QProgressBar()
        self.ram_bar.setObjectName("RamBar")
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setFixedHeight(4)
        
        self.ram_pct = QLabel("0%")
        self.ram_pct.setObjectName("MetricsPct")
        
        ram_layout.addWidget(self.ram_label)
        ram_layout.addWidget(self.ram_bar, 1)
        ram_layout.addWidget(self.ram_pct)
        self.content_layout.addWidget(self.ram_container)
        
        # Modules
        self.mod_container = QFrame()
        self.mod_container.setObjectName("MetricsContainer")
        mod_layout = QVBoxLayout(self.mod_container)
        mod_layout.setContentsMargins(15, 12, 15, 12)
        
        header_row = QHBoxLayout()
        self.module_label = QLabel("MODULES | Actif")
        self.module_label.setObjectName("MetricsText")
        
        self.clear_btn = QPushButton("🗑 CLEAR")
        self.clear_btn.setObjectName("ClearBtn")
        self.clear_btn.setFixedSize(70, 24)
        
        header_row.addWidget(self.module_label)
        header_row.addStretch()
        header_row.addWidget(self.clear_btn)
        mod_layout.addLayout(header_row)
        
        self.circles_row = QHBoxLayout()
        self.circles_row.setSpacing(10)
        
        self.circles = []
        for i in range(4):
            # NURU V5 : vraies jauges circulaires au lieu de QFrame vides
            gauge = CircularGauge(size=40, thickness=3)
            if i == 0:
                gauge.progress_color = QColor("#39FF14")
                gauge.track_color = QColor("#333333")
            elif i == 1:
                gauge.progress_color = QColor("#FF00FF")
                gauge.track_color = QColor("#333333")
            elif i == 2:
                gauge.progress_color = QColor("#FFB000")
                gauge.track_color = QColor("#333333")
            else:
                gauge.progress_color = QColor("#00F2FF")
                gauge.track_color = QColor("#333333")
            
            cvbox = QVBoxLayout()
            cvbox.setContentsMargins(0, 0, 0, 0)
            cvbox.setSpacing(4)
            cvbox.addWidget(gauge, alignment=Qt.AlignCenter)
            
            label = QLabel(["LLM", "RAG", "MEM", "GPU"][i])
            label.setStyleSheet("color:#6b7280; font-size:8px;")
            label.setAlignment(Qt.AlignCenter)
            cvbox.addWidget(label)

            self.circles_row.addLayout(cvbox)
            self.circles.append(gauge)

        self.circles_row.addStretch()
        mod_layout.addLayout(self.circles_row)
        self.content_layout.addWidget(self.mod_container)

        # ── NURU V5 : Cartes de métriques (Vitesse, Score RAG) ──
        self.tok_card = MetricCard("VITESSE (Tok/s)", "0.0")
        self.tok_card.set_value_color("#39FF14")
        self.rag_card = MetricCard("SCORE RAG", "0.00")
        self.rag_card.set_value_color("#FF00FF")
        self.content_layout.addWidget(self.tok_card)
        self.content_layout.addWidget(self.rag_card)

    def update_metrics(self, ram_free_gb, ram_total_gb, module_status=""):
        ram_ratio = ram_free_gb / ram_total_gb if ram_total_gb > 0 else 0
        ram_used_pct = int((1 - ram_ratio) * 100)
        ram_color = "#00f2ff" if ram_ratio > 0.15 else "#ef4444"
        used_gb = ram_total_gb - ram_free_gb

        self.ram_label.setText(
            f"SYS RAM | <span style='color:{ram_color}'>{used_gb:.1f}G</span> / {ram_total_gb:.1f}G"
        )
        self.ram_bar.setValue(ram_used_pct)
        self.ram_pct.setText(f"{ram_used_pct}%")

        # NURU V5 : animer les jauges circulaires
        ram_pct_value = 1.0 - ram_ratio  # 0=libre, 1=plein
        if len(self.circles) >= 4:
            self.circles[0].set_value(0.65, "LLM")    # LLM simulé
            self.circles[1].set_value(0.30, "RAG")    # RAG
            self.circles[2].set_value(ram_pct_value, f"{ram_used_pct}%")  # MEM réelle
            self.circles[3].set_value(0.20, "GPU")    # GPU

        if module_status:
            status_color = "#10b981" if "Actif" in module_status else "#ff00ff"
            self.module_label.setText(
                f"MODULES | <span style='color:{status_color}'>{module_status}</span>"
            )

    def _toggle_visibility(self):
        """Réduit ou agrandit le panneau de métriques."""
        self._visible = not self._visible
        self.content_widget.setVisible(self._visible)
        self.toggle_btn.setText("□" if self._visible else "📊")
        if self._visible:
            self.setFixedWidth(340)
        else:
            self.setFixedWidth(40)
        # Re-positionner après changement de taille
        if self.parent():
            parent = self.parent()
            if hasattr(parent, '_reposition_overlay'):
                parent._reposition_overlay()

class TokenReceiver(QThread):
    token_received = Signal(str)
    finished = Signal()

    def __init__(self, core, query):
        super().__init__()
        self.core = core
        self.query = query

    def run(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def stream():
            try:
                async for token in self.core.process_query_v45(self.query):
                    self.token_received.emit(token)
            except Exception as e:
                logger.error(f"Stream error: {e}")
                self.token_received.emit(f"\n[Error: {e}]")
        
        loop.run_until_complete(stream())
        self.finished.emit()

class CyberDashboard(QMainWindow):
    def __init__(self, core: NuruCore):
        super().__init__()
        logger.info("Initializing CyberDashboard...")
        self.core = core
        self.app_state = AppState()
        self.active_threads = []
        # NURU V5 : ViewModel pour les métriques système
        self.telemetry_vm = TelemetryViewModel()
        
        # Window setup
        self.setWindowTitle("NURU")
        self.resize(1150, 800)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Build components
        self._build_sidebar()
        self._build_central_area()
        self._build_right_panel()  # V6 : colonne métriques + CoT
        
        self._wire_signals()
        self._init_timers()
        self.load_styles()

        # Message de bienvenue initial
        self.console_page.clear_chat()
        self.console_page.add_message("NURU", "Bonjour, comment puis-je vous aider en cette journée ?", is_user=False)

        self.stacked.setCurrentIndex(0)
        logger.info("CyberDashboard initialized.")

    def load_styles(self):
        style_path = Path(__file__).parent / "styles.qss"
        if style_path.exists():
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def mousePressEvent(self, event):
        # NURU V5 : ne pas capturer les clics sur les widgets enfants
        child = self.childAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and not child:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos') and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(260)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(20)
        
        # Header
        header = QHBoxLayout()
        self.logo = AnimatedLogo(size=40)
        header.addWidget(self.logo)
        
        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        app_name = QLabel("NURU")
        app_name.setObjectName("AppName")
        app_ver = QLabel("v6.0")
        app_ver.setObjectName("AppVersion")
        vbox.addWidget(app_name)
        vbox.addWidget(app_ver)
        header.addLayout(vbox)
        header.addStretch()
        layout.addLayout(header)
        
        self.new_chat_btn = QPushButton("+ Nouveau Chat")
        self.new_chat_btn.setObjectName("NewChatBtn")
        self.new_chat_btn.setFixedHeight(45)
        layout.addWidget(self.new_chat_btn)
        
        self.main_menu = QListWidget()
        self.main_menu.setObjectName("SidebarMenu")
        for icon, text in [("📚", "Base Documentaire"), ("⚙️", "Paramètres"), ("📊", "Système V6")]:
            item = QListWidgetItem(f"{icon}  {text}")
            item.setSizeHint(QSize(0, 40))
            self.main_menu.addItem(item)
        self.main_menu.itemClicked.connect(self._on_menu_clicked)
        layout.addWidget(self.main_menu)
        
        layout.addWidget(QLabel("RACCOURCIS"), 0, Qt.AlignLeft)
        raccourcis = [("⟨ ⟩", "Documentation API", 3), ("📖", "Guides Tutoriels", 4), 
                      ("✨", "Exemples de Prompts", 5), ("🕒", "Historique des sessions", 6)]
        for icon, text, idx in raccourcis:
            btn = QPushButton(f"{icon}  {text}")
            btn.setObjectName("ShortcutBtn")
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda ch, i=idx: self.switch_page(i))
            layout.addWidget(btn)
            
        layout.addStretch()
        
        pro_card = QFrame()
        pro_card.setObjectName("ProCard")
        pro_vbox = QVBoxLayout(pro_card)
        pro_vbox.addWidget(QLabel("🚀 NURU PRO"))
        pro_desc = QLabel("Débloquez des modules\navancés et optimisez vos\nperformances.")
        pro_desc.setStyleSheet("color:#64748b; font-size:11px;")
        pro_vbox.addWidget(pro_desc)
        pro_btn = QPushButton("Découvrir")
        pro_btn.setObjectName("ProBtn")
        pro_vbox.addWidget(pro_btn)
        layout.addWidget(pro_card)
        
        layout.addWidget(QLabel("© 2026 NURU AI"), 0, Qt.AlignCenter)
        self.main_layout.addWidget(sidebar)

    def _build_central_area(self):
        container = QFrame()
        container.setObjectName("CentralContainer")

        # Fond d'écran + overlay sombre pour lisibilité
        bg_path = Path(__file__).parent / "assets" / "fond.jpg"
        if bg_path.exists():
            container.setStyleSheet(f"""
                #CentralContainer {{
                    border-image: url({bg_path.as_posix()}) 0 0 0 0 stretch stretch;
                }}
            """)
            # Overlay semi-transparent par-dessus l'image
            overlay = QFrame(container)
            overlay.setStyleSheet("""
                background-color: rgba(13, 17, 23, 0.25);
            """)
            overlay.setGeometry(0, 0, container.width(), container.height())
            overlay.lower()

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        header = QFrame()
        header.setObjectName("ChatHeader")
        header.setFixedHeight(80)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(30, 0, 30, 0)
        
        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(4)
        chat_title = QLabel("Chat")
        chat_title.setObjectName("ChatTitle")
        title_vbox.addWidget(chat_title)
        
        status_frame = QFrame()
        status_frame.setObjectName("ConsoleStatusFrame")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 2, 10, 2)
        status_layout.addWidget(QLabel("🖥"))
        status_lbl = QLabel("CONSOLE NURU")
        status_lbl.setObjectName("ConsoleStatusLabel")
        status_layout.addWidget(status_lbl)
        status_dot = QLabel("●")
        status_dot.setStyleSheet("color:#10b981; font-size:10px;")
        status_layout.addWidget(status_dot)
        title_vbox.addWidget(status_frame, 0, Qt.AlignLeft)
        
        # NURU V6 : Badge de stratégie hybride
        self.strategy_badge = QLabel("🌀 LOCAL")
        self.strategy_badge.setObjectName("StrategyBadge")
        self.strategy_badge.setStyleSheet("""
            background-color: rgba(57, 255, 20, 0.1);
            border: 1px solid #39FF14;
            border-radius: 4px;
            color: #39FF14;
            font-size: 10px;
            padding: 2px 8px;
            font-weight: bold;
        """)
        title_vbox.addWidget(self.strategy_badge, 0, Qt.AlignLeft)
        
        h_layout.addLayout(title_vbox)
        h_layout.addStretch()
        layout.addWidget(header)
        
        self.stacked = QStackedWidget()
        self.console_page = ConsolePage()
        self.console_page.query_submitted.connect(self.handle_submit)
        self.stacked.addWidget(self.console_page)
        
        # Add other pages safely
        try: self.stacked.addWidget(DocumentsPage(self.core.rag, self.core.ingestion))
        except Exception as e: logger.error(f"Error loading DocumentsPage: {e}")
        
        try: self.stacked.addWidget(SettingsPage(config))
        except Exception as e: logger.error(f"Error loading SettingsPage: {e}")
        
        try: self.stacked.addWidget(ApiDocsPage())
        except Exception as e: logger.error(f"Error loading ApiDocsPage: {e}")
        
        try: self.stacked.addWidget(GuidesPage())
        except Exception as e: logger.error(f"Error loading GuidesPage: {e}")
        
        try: self.stacked.addWidget(PromptsPage())
        except Exception as e: logger.error(f"Error loading PromptsPage: {e}")
        
        try: self.stacked.addWidget(SessionsPage(self.core.memory))
        except Exception as e: logger.error(f"Error loading SessionsPage: {e}")
        
        # NURU V6 : Page Système (modules V6)
        try: self.stacked.addWidget(SystemPage(config=config, core=self.core))
        except Exception as e: logger.error(f"Error loading SystemPage: {e}")
        
        layout.addWidget(self.stacked, 1)
        self.main_layout.addWidget(container, 1)

    def _build_right_panel(self):
        """V6 : Colonne droite — métriques en temps réel + zone Chain of Thought.

        Design sobre : fond anthracite, accents bleu électrique, vert acide.
        """
        self.right_panel = QFrame()
        self.right_panel.setObjectName("RightPanel")
        self.right_panel.setFixedWidth(320)
        self.right_panel.setStyleSheet("""
            #RightPanel {
                background-color: #0D1117;
                border-left: 1px solid #1F2937;
                border-top-right-radius: 16px;
                border-bottom-right-radius: 16px;
            }
        """)

        layout = QVBoxLayout(self.right_panel)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(16)

        # ── Titre du panneau ──
        panel_title = QLabel("SYSTÈME")
        panel_title.setStyleSheet(
            "color: #6B7280; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(panel_title)

        # ── RAM ──
        ram_frame = QFrame()
        ram_frame.setStyleSheet("""
            background-color: #161B22;
            border: 1px solid #1F2937;
            border-radius: 8px; padding: 12px;
        """)
        ram_inner = QVBoxLayout(ram_frame)
        ram_inner.setSpacing(6)

        ram_header = QHBoxLayout()
        ram_lbl = QLabel("🖥 RAM")
        ram_lbl.setStyleSheet("color: #00A3FF; font-size: 11px; font-weight: bold;")
        self.ram_value = QLabel("-- / --")
        self.ram_value.setStyleSheet("color: #E5E7EB; font-size: 13px; font-weight: bold;")
        ram_header.addWidget(ram_lbl)
        ram_header.addStretch()
        ram_header.addWidget(self.ram_value)
        ram_inner.addLayout(ram_header)

        self.ram_bar = QProgressBar()
        self.ram_bar.setFixedHeight(4)
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1F2937; border: none; border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #39FF14, stop:1 #00A3FF);
                border-radius: 2px;
            }
        """)
        ram_inner.addWidget(self.ram_bar)

        self.ram_detail = QLabel("")
        self.ram_detail.setStyleSheet("color: #6B7280; font-size: 10px;")
        ram_inner.addWidget(self.ram_detail)
        layout.addWidget(ram_frame)

        # ── Cartes métriques ──
        metrics_grid = QHBoxLayout()
        metrics_grid.setSpacing(8)

        self.tok_card = self._make_metric_card("TOK/S", "0.0", "#00A3FF")
        self.rag_card = self._make_metric_card("RAG", "0.00", "#39FF14")
        metrics_grid.addWidget(self.tok_card)
        metrics_grid.addWidget(self.rag_card)
        layout.addLayout(metrics_grid)

        self.mode_card = self._make_metric_card("MODE", "local", "#FFB000")
        layout.addWidget(self.mode_card)

        # ── Séparateur ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1F2937;")
        layout.addWidget(sep)

        # ── Zone Chain of Thought ──
        cot_label = QLabel("🧠 RAISONNEMENT")
        cot_label.setStyleSheet(
            "color: #6B7280; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(cot_label)

        self.cot_text = QLabel("En attente d'une requête...")
        self.cot_text.setWordWrap(True)
        self.cot_text.setStyleSheet("""
            color: #9CA3AF; font-size: 11px; line-height: 1.5;
            background-color: #161B22;
            border: 1px solid #1F2937;
            border-radius: 8px; padding: 12px;
        """)
        layout.addWidget(self.cot_text, 1)

        # ── Info modèle ──
        self.model_info = QLabel("Phi-4-mini-4bit • Groq")
        self.model_info.setStyleSheet("color: #4B5563; font-size: 9px;")
        self.model_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.model_info)

        self.main_layout.addWidget(self.right_panel)

    def _make_metric_card(self, title: str, value: str, color: str) -> QFrame:
        """Crée une carte métrique compacte."""
        card = QFrame()
        card.setStyleSheet(f"""
            background-color: #161B22;
            border: 1px solid #1F2937;
            border-radius: 8px; padding: 10px;
        """)
        inner = QVBoxLayout(card)
        inner.setSpacing(4)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {color}; font-size: 9px; font-weight: bold;")
        val = QLabel(value)
        val.setStyleSheet(f"color: #E5E7EB; font-size: 16px; font-weight: bold;")
        val.setAlignment(Qt.AlignLeft)
        inner.addWidget(lbl)
        inner.addWidget(val)
        return card

    def set_cot(self, text: str):
        """V6 : Met à jour la zone Chain of Thought."""
        self.cot_text.setText(text)

    def clear_cot(self):
        self.cot_text.setText("En attente d'une requête...")

    def _on_menu_clicked(self, item):
        idx = self.main_menu.row(item)
        target = {0: 1, 1: 2, 2: 7}.get(idx, 0)
        self.switch_page(target)

    def resizeEvent(self, event):
        """Redimensionne l'overlay de fond avec la fenêtre."""
        super().resizeEvent(event)
        # Mettre à jour la taille de l'overlay sombre
        container = self.findChild(QFrame, "CentralContainer")
        if container:
            for child in container.findChildren(QFrame):
                if child.styleSheet() and "rgba(13, 17, 23" in child.styleSheet():
                    child.setGeometry(0, 0, container.width(), container.height())
                    break

    def switch_page(self, index: int):
        """V6 : Transition animée entre les pages du dashboard — fondu 350ms."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        current = self.stacked.currentWidget()
        if current:
            # Appliquer un effet d'opacité pour le fondu entrant
            opacity_effect = QGraphicsOpacityEffect()
            self.stacked.setGraphicsEffect(opacity_effect)

            self.fade_anim = QPropertyAnimation(opacity_effect, b"opacity")
            self.fade_anim.setDuration(350)
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)

            self.stacked.setCurrentIndex(index)
            self.fade_anim.start()

    def _wire_signals(self):
        self._bus = EventBus()
        self.new_chat_btn.clicked.connect(self._on_console_clear)
        self.console_page.clear_requested.connect(self._on_console_clear)

    def _init_timers(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_metrics)
        self._timer.start(1000)

    def _update_metrics(self):
        try:
            snapshot = self.telemetry_vm.snapshot()
            free_gb = snapshot.ram_free_mb / 1024.0
            total_gb = snapshot.ram_total_mb / 1024.0
            used_gb = total_gb - free_gb
            ram_pct = int((1 - free_gb / total_gb) * 100) if total_gb > 0 else 0
            ram_color = "#39FF14" if free_gb > 1.5 else "#FFB000" if free_gb > 0.5 else "#ef4444"

            self.ram_value.setText(
                f"<span style='color:{ram_color}'>{used_gb:.1f}G</span> / {total_gb:.1f}G"
            )
            self.ram_bar.setValue(ram_pct)
            self.ram_detail.setText(
                f"{ram_pct}% utilisé  •  {free_gb:.1f}G libre"
            )

            # Badge stratégie
            try:
                hybrid = getattr(config, 'hybrid_mode', 'local_only')
                labels = {"local_only": "local", "verify": "verify",
                          "plan": "plan", "rag": "archon"}
                mode = labels.get(hybrid, "local")
                self.mode_card.layout().itemAt(1).widget().setText(mode)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Metrics update fail: {e}")

    def handle_submit(self, query):
        self.console_page.add_message("VOUS", query, is_user=True)
        self.current_bubble = self.console_page.add_message("NURU", "", is_user=False)

        # NURU V5 : InferenceWorker via QThreadPool
        from src.core.inference_worker import InferenceWorker
        from PySide6.QtCore import QThreadPool
        worker = InferenceWorker(self.core, query)
        worker.signals.token_received.connect(self.current_bubble.append_text)
        worker.signals.finished.connect(self._on_generation_finished)
        worker.signals.error.connect(self._on_generation_error)
        QThreadPool.globalInstance().start(worker)

    def _on_generation_finished(self, full_text):
        logger.info("✅ Génération terminée")

    def _on_generation_error(self, error_msg):
        self.current_bubble.append_text(f"\n[Erreur: {error_msg}]")

    def _on_console_clear(self):
        self.console_page.clear_chat()
        self.console_page.add_message("NURU", "Bonjour, comment puis-je vous aider en cette journée ?", is_user=False)


if __name__ == "__main__":
    logger.info("Starting NURU application...")
    app = QApplication(sys.argv)
    
    try:
        logger.info("Initializing NuruCore...")
        core = NuruCore()
        logger.info("NuruCore initialized.")
        
        win = CyberDashboard(core)
        win.show()
        logger.info("Main window shown.")
        
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"Critical application error: {e}", exc_info=True)
        sys.exit(1)
