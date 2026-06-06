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
    QGraphicsDropShadowEffect,
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
        
        # Suivi des métriques RAG pour l'observabilité
        self._rag_scores_session = []  # Scores RAG de la session
        self._rag_docs_found = []      # Nb documents trouvés par requête
        self._rag_rejections = 0       # Compteur de refus StrictRAG
        self._rag_queries_total = 0    # Requêtes RAG totales
        
        # Window setup
        self.setWindowTitle("NURU")
        self.setMinimumSize(900, 600)
        self.resize(1150, 800)
        # Fenêtre sans bordure avec ombre native macOS
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowSystemMenuHint |
            Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Poignée de redimensionnement (bas-droit)
        self._resize_handle = QFrame(self)
        self._resize_handle.setObjectName("ResizeHandle")
        self._resize_handle.setFixedSize(16, 16)
        self._resize_handle.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self._resize_handle.setStyleSheet("""
            QFrame#ResizeHandle {
                background: rgba(0, 163, 255, 0.3);
                border-top-left-radius: 8px;
            }
            QFrame#ResizeHandle:hover {
                background: rgba(0, 163, 255, 0.6);
            }
        """)
        self._resize_handle.mousePressEvent = lambda e: self._start_resize(e)
        self._resize_handle.mouseMoveEvent = lambda e: self._do_resize(e)

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Build components
        self._build_sidebar()
        self._build_central_area()
        self._build_right_panel()  # V6 : colonne métriques + CoT + RAG Observabilité
        
        self._wire_signals()
        self._init_timers()
        self.load_styles()

        # Message de bienvenue initial
        self.console_page.clear_chat()
        self.console_page.add_message("NURU", "Bonjour, comment puis-je vous aider en cette journée ?", is_user=False)

        self.stacked.setCurrentIndex(0)
        
        # Abonnement aux événements RAG (EventBus singleton)
        # Note: la mise à jour UI réelle se fait via le signal rag_data de InferenceWorker,
        # qui est thread-safe. L'EventBus est utilisé pour les logs backend uniquement.
        self._bus = EventBus()
        self._bus.subscribe("generation_complete", self._on_rag_event_safe)
        
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
        sidebar.setFixedWidth(80)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(6, 20, 6, 12)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)
        
        # Header — logo only
        self.logo = AnimatedLogo(size=32)
        hdr_lo = QHBoxLayout()
        hdr_lo.addWidget(self.logo, 0, Qt.AlignCenter)
        layout.addLayout(hdr_lo)
        
        # New Chat — icône ronde
        self.new_chat_btn = QPushButton("＋")
        self.new_chat_btn.setObjectName("NewChatBtn")
        self.new_chat_btn.setFixedSize(40, 40)
        self.new_chat_btn.setToolTip("Nouveau Chat")
        layout.addWidget(self.new_chat_btn, 0, Qt.AlignCenter)
        
        # Separateur
        sep1 = QFrame()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background: rgba(30,30,58,0.6); border: none;")
        layout.addWidget(sep1)
        
        # Menu principal — icônes seulement
        self.main_menu = QListWidget()
        self.main_menu.setObjectName("SidebarMenu")
        for icon, _ in [("📚", "Base Documentaire"), ("⚙️", "Paramètres"), ("📊", "Système V6")]:
            item = QListWidgetItem(icon)
            item.setSizeHint(QSize(0, 44))
            item.setTextAlignment(Qt.AlignCenter)
            self.main_menu.addItem(item)
        self.main_menu.itemClicked.connect(self._on_menu_clicked)
        layout.addWidget(self.main_menu, 0, Qt.AlignCenter)
        
        # Separateur
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: rgba(30,30,58,0.6); border: none;")
        layout.addWidget(sep2)
        
        # Raccourcis — icônes seulement
        raccourcis = [("⟨⟩", "Documentation API", 3), ("📖", "Guides Tutoriels", 4),
                      ("✨", "Exemples de Prompts", 5), ("🕒", "Sessions", 6)]
        for icon, tip, idx in raccourcis:
            btn = QPushButton(icon)
            btn.setObjectName("ShortcutBtn")
            btn.setFixedSize(44, 44)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda ch, i=idx: self.switch_page(i))
            layout.addWidget(btn, 0, Qt.AlignCenter)
            
        layout.addStretch()
        
        # Pro Card — compacte
        pro_card = QFrame()
        pro_card.setObjectName("ProCard")
        pro_vbox = QVBoxLayout(pro_card)
        pro_vbox.setContentsMargins(4, 6, 4, 6)
        pro_vbox.setSpacing(2)
        pro_vbox.addWidget(QLabel("🚀"), 0, Qt.AlignCenter)
        pro_btn = QPushButton("PRO")
        pro_btn.setObjectName("ProBtn")
        pro_vbox.addWidget(pro_btn)
        layout.addWidget(pro_card, 0, Qt.AlignCenter)
        
        layout.addWidget(QLabel("© 2026"), 0, Qt.AlignCenter)
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
        except Exception as e:
            logger.error(f"Error loading SettingsPage: {e}")
            # Ajouter une page placeholder pour maintenir l'index du menu
            placeholder = QWidget()
            placeholder.setObjectName("SettingsPage")
            layout = QVBoxLayout(placeholder)
            err_lbl = QLabel(f"⚠ Erreur de chargement des paramètres\n\n{str(e)}")
            err_lbl.setStyleSheet("color: #ef4444; font-size: 14px;")
            err_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(err_lbl)
            self.stacked.addWidget(placeholder)
        
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

    def _build_right_panel(self):
        """V6 : Panneau télémétrie — jauge RAM circulaire, grille métriques 2x2, notifications."""
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

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background: transparent;")
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(14)

        # ── Titre ──
        panel_title = QLabel("TÉLÉMÉTRIE")
        panel_title.setStyleSheet(
            "color: #6B7280; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(panel_title)

        # ════════════════════════════════════════════════
        # JAUGE RAM CIRCULAIRE
        # ════════════════════════════════════════════════
        ram_gauge_container = QFrame()
        ram_gauge_container.setStyleSheet("""
            background-color: #16162a;
            border: 1px solid #1e1e3a;
            border-radius: 12px;
            padding: 16px;
        """)
        ram_gauge_layout = QVBoxLayout(ram_gauge_container)
        ram_gauge_layout.setContentsMargins(0, 0, 0, 0)
        ram_gauge_layout.setAlignment(Qt.AlignCenter)

        self.ram_gauge = CircularGauge(size=130)
        self.ram_gauge.set_value(0.0, "0.0", "0.0")
        ram_gauge_layout.addWidget(self.ram_gauge, alignment=Qt.AlignCenter)

        # Sous-titre usage RAM
        self.ram_detail_label = QLabel("0% utilisé  •  0.0G libre")
        self.ram_detail_label.setAlignment(Qt.AlignCenter)
        self.ram_detail_label.setStyleSheet("color: #6b7280; font-size: 10px;")
        ram_gauge_layout.addWidget(self.ram_detail_label)

        layout.addWidget(ram_gauge_container)

        # ════════════════════════════════════════════════
        # GRILLE MÉTRIQUES 2×2
        # ════════════════════════════════════════════════
        grille_label = QLabel("MÉTRIQUES")
        grille_label.setStyleSheet(
            "color: #6B7280; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(grille_label)

        metrics_grid = QWidget()
        metrics_grid.setStyleSheet("background: transparent;")
        grid = QVBoxLayout(metrics_grid)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        # Ligne 1
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.metric_llm = MetricCard("LLM", "0%", icon="🧠", accent_color="#a855f7")
        self.metric_rag_score = MetricCard("RAG", "0.00", icon="🔍", accent_color="#22c55e")
        row1.addWidget(self.metric_llm)
        row1.addWidget(self.metric_rag_score)
        grid.addLayout(row1)

        # Ligne 2
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.metric_tokens = MetricCard("TOKENS", "0%", icon="⚡", accent_color="#00d4ff")
        self.metric_traces = MetricCard("TRACES", "0", icon="📝", accent_color="#fbbf24")
        row2.addWidget(self.metric_tokens)
        row2.addWidget(self.metric_traces)
        grid.addLayout(row2)

        layout.addWidget(metrics_grid)

        # ════════════════════════════════════════════════
        # OBSERVABILITÉ RAG (compact)
        # ════════════════════════════════════════════════
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color: #1e1e3a;")
        layout.addWidget(sep1)

        rag_section_label = QLabel("RAG OBSERVABILITY")
        rag_section_label.setStyleSheet(
            "color: #6B7280; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(rag_section_label)

        self.rag_recall_card = self._make_metric_card("RECALL@5", "--", "#22c55e")
        layout.addWidget(self.rag_recall_card)

        self.rag_avg_score_card = self._make_metric_card("SCORE MOYEN", "--", "#a855f7")
        layout.addWidget(self.rag_avg_score_card)

        self.rag_docs_card = self._make_metric_card("DOCUMENTS/REQ", "--", "#00d4ff")
        layout.addWidget(self.rag_docs_card)

        self.rag_rejection_card = self._make_metric_card("TAUX REFUS", "--", "#ef4444")
        layout.addWidget(self.rag_rejection_card)

        # ════════════════════════════════════════════════
        # NOTIFICATIONS
        # ════════════════════════════════════════════════
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #1e1e3a;")
        layout.addWidget(sep2)

        notif_header = QHBoxLayout()
        notif_header.setSpacing(6)
        notif_icon = QLabel("🔔")
        notif_icon.setStyleSheet("font-size: 12px;")
        notif_title = QLabel("NOTIFICATIONS")
        notif_title.setStyleSheet(
            "color: #6B7280; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        notif_header.addWidget(notif_icon)
        notif_header.addWidget(notif_title)
        notif_header.addStretch()
        layout.addLayout(notif_header)

        # Notifications dynamiques
        self.notif_container = QFrame()
        self.notif_container.setStyleSheet("""
            background-color: #16162a;
            border: 1px solid #1e1e3a;
            border-radius: 12px;
            padding: 8px;
        """)
        notif_list = QVBoxLayout(self.notif_container)
        notif_list.setContentsMargins(12, 10, 12, 10)
        notif_list.setSpacing(10)

        # Notification 1 — verte
        n1_row = QHBoxLayout()
        n1_row.setSpacing(8)
        n1_dot = QLabel("●")
        n1_dot.setStyleSheet("color: #22c55e; font-size: 8px;")
        n1_text = QLabel("Auto-Fetch : 3 docs indexés il y a 4 min")
        n1_text.setStyleSheet("color: #d1d5db; font-size: 10px;")
        n1_text.setWordWrap(True)
        n1_row.addWidget(n1_dot, alignment=Qt.AlignTop)
        n1_row.addWidget(n1_text)
        notif_list.addLayout(n1_row)

        # Notification 2 — jaune
        n2_row = QHBoxLayout()
        n2_row.setSpacing(8)
        n2_dot = QLabel("●")
        n2_dot.setStyleSheet("color: #fbbf24; font-size: 8px;")
        n2_text = QLabel("RAM > 85% — cloud suspendu")
        n2_text.setStyleSheet("color: #d1d5db; font-size: 10px;")
        n2_text.setWordWrap(True)
        n2_row.addWidget(n2_dot, alignment=Qt.AlignTop)
        n2_row.addWidget(n2_text)
        notif_list.addLayout(n2_row)

        # Notification 3 — info
        n3_row = QHBoxLayout()
        n3_row.setSpacing(8)
        n3_icon = QLabel("ℹ️")
        n3_icon.setStyleSheet("font-size: 10px;")
        n3_text = QLabel("Session démarrée il y a 12 min")
        n3_text.setStyleSheet("color: #6b7280; font-size: 10px;")
        n3_text.setWordWrap(True)
        n3_row.addWidget(n3_icon, alignment=Qt.AlignTop)
        n3_row.addWidget(n3_text)
        notif_list.addLayout(n3_row)

        layout.addWidget(self.notif_container)

        # ════════════════════════════════════════════════
        # CHAIN OF THOUGHT
        # ════════════════════════════════════════════════
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("color: #1e1e3a;")
        layout.addWidget(sep3)

        cot_label = QLabel("🧠 RAISONNEMENT")
        cot_label.setStyleSheet(
            "color: #6B7280; font-size: 10px; font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(cot_label)

        self.cot_text = QLabel("En attente d'une requête...")
        self.cot_text.setWordWrap(True)
        self.cot_text.setStyleSheet("""
            color: #9CA3AF; font-size: 11px; line-height: 1.5;
            background-color: #16162a;
            border: 1px solid #1e1e3a;
            border-radius: 12px; padding: 12px;
        """)
        layout.addWidget(self.cot_text, 1)

        # ── Info modèle ──
        self.model_info = QLabel("Phi-4-mini-4bit • Groq")
        self.model_info.setStyleSheet("color: #4B5563; font-size: 9px;")
        self.model_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.model_info)

        layout.addStretch()
        scroll_area.setWidget(scroll_content)

        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(scroll_area)

        self.main_layout.addWidget(self.right_panel)

    def set_cot(self, text: str):
        """V6 : Met à jour la zone Chain of Thought."""
        self.cot_text.setText(text)

    def clear_cot(self):
        self.cot_text.setText("En attente d'une requête...")

    def _update_rag_observability(self):
        """Met à jour toutes les cartes du dashboard d'observabilité RAG."""
        total = self._rag_queries_total
        
        if total == 0:
            return
        
        # Recall@5 : estimé depuis le nombre de requêtes avec documents trouvés
        recalls = [1 if d > 0 else 0 for d in self._rag_docs_found]
        recall_at_5 = (sum(recalls) / len(recalls) * 100) if recalls else 0.0
        
        # Score RAG moyen de la session
        avg_rag_score = (sum(self._rag_scores_session) / len(self._rag_scores_session)) if self._rag_scores_session else 0.0
        
        # Documents trouvés par requête (moyenne)
        avg_docs = (sum(self._rag_docs_found) / len(self._rag_docs_found)) if self._rag_docs_found else 0.0
        
        # Taux de refus
        rejection_rate = (self._rag_rejections / total * 100) if total > 0 else 0.0
        
        # Mettre à jour les cartes
        self.rag_recall_card.layout().itemAt(1).widget().setText(f"{recall_at_5:.1f}%")
        self.rag_avg_score_card.layout().itemAt(1).widget().setText(f"{avg_rag_score:.2f}")
        self.rag_docs_card.layout().itemAt(1).widget().setText(f"{avg_docs:.1f}")
        self.rag_rejection_card.layout().itemAt(1).widget().setText(f"{rejection_rate:.1f}%")
        
        # Colorer le taux de refus
        rejection_val = self.rag_rejection_card.layout().itemAt(1).widget()
        if rejection_rate > 20:
            rejection_val.setStyleSheet("color: #ef4444; font-size: 16px; font-weight: bold;")
        elif rejection_rate > 5:
            rejection_val.setStyleSheet("color: #fbbf24; font-size: 16px; font-weight: bold;")
        else:
            rejection_val.setStyleSheet("color: #22c55e; font-size: 16px; font-weight: bold;")

    def _on_rag_event_safe(self, event_data: dict):
        """Callback EventBus sécurisé (thread-safe) — logs seulement, pas de UI.
        
        La mise à jour réelle de l'UI se fait via le signal rag_data 
        de InferenceWorker (thread-safe car c'est un signal Qt).
        """
        if isinstance(event_data, dict):
            rag_score = event_data.get("rag_score", 0.0)
            rag_result = event_data.get("rag_result", {})
            if rag_result:
                docs_found = rag_result.get("documents_found", 0)
                logger.debug(
                    f"📊 RAG EventBus: score={rag_score:.2f}, docs={docs_found}"
                )

    def _on_rag_generation_complete(self, event_data: dict):
        """Callback EventBus : met à jour les métriques RAG après chaque génération."""
        try:
            # Si le callback a été appelé avec un argument direct (emit synchrone)
            # ou s'il vient du EventBus avec data
            if isinstance(event_data, dict):
                rag_score = event_data.get("rag_score", 0.0)
                rag_result = event_data.get("rag_result", {})
                
                if rag_result:
                    docs_found = rag_result.get("documents_found", 0)
                    rejected = rag_result.get("rejected_chunks", 0)
                    rejection_reason = rag_result.get("rejection_reason", "")
                    
                    self._rag_queries_total += 1
                    self._rag_scores_session.append(rag_score)
                    self._rag_docs_found.append(docs_found)
                    
                    # Compter les refus (rejected_chunks > 0 ou top_score trop bas)
                    if rejected > 0 or (rag_score < 0.3 and rejection_reason):
                        self._rag_rejections += 1
                    
                    # Mettre à jour le badge RAG dans la dernière bulle assistant
                    self.console_page.update_last_assistant_rag(rag_score)
                    
                    # Mettre à jour la carte RAG du panneau système
                    try:
                        rag_color = "#22c55e" if rag_score > 0.5 else "#fbbf24" if rag_score > 0.2 else "#ef4444"
                        self.metric_rag_score.set_value_and_color(f"{rag_score:.2f}", rag_color)
                    except Exception:
                        pass
                    
                    # Mettre à jour le dashboard d'observabilité
                    self._update_rag_observability()
                    
                    # Mettre à jour les sources dans la barre du console
                    sources = rag_result.get("sources", [])
                    if sources:
                        self.console_page.set_sources(sources)
                    
                    logger.debug(
                        f"📊 RAG Observabilité: score={rag_score:.2f}, docs={docs_found}, "
                        f"rejet={rejected}, total_requetes={self._rag_queries_total}"
                    )
        except Exception as e:
            logger.debug(f"RAG observability update error: {e}")

    def _on_menu_clicked(self, item):
        idx = self.main_menu.row(item)
        target = {0: 1, 1: 2, 2: 7}.get(idx, 0)
        self.switch_page(target)

    def _start_resize(self, event):
        self._resize_start = event.globalPosition().toPoint()
        self._resize_geom = self.geometry()

    def _do_resize(self, event):
        if not hasattr(self, '_resize_start'):
            return
        delta = event.globalPosition().toPoint() - self._resize_start
        new_w = max(self.minimumWidth(), self._resize_geom.width() + delta.x())
        new_h = max(self.minimumHeight(), self._resize_geom.height() + delta.y())
        self.resize(new_w, new_h)

    def resizeEvent(self, event):
        """Redimensionne l'overlay de fond avec la fenêtre."""
        super().resizeEvent(event)
        # Positionner la poignée dans le coin inférieur droit
        if hasattr(self, '_resize_handle'):
            self._resize_handle.move(
                self.width() - self._resize_handle.width(),
                self.height() - self._resize_handle.height()
            )
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
            ram_ratio = (total_gb - free_gb) / total_gb if total_gb > 0 else 0

            # Jauge RAM circulaire
            self.ram_gauge.set_value(ram_ratio, f"{used_gb:.1f}", f"{total_gb:.0f}")
            self.ram_detail_label.setText(
                f"{ram_pct}% utilisé  •  {free_gb:.1f}G libre"
            )

            # Carte LLM (simulé via snapshot ou estimation)
            try:
                llm_pct = getattr(snapshot, 'llm_load_pct', min(int(ram_pct * 0.7 + 25), 99))
                self.metric_llm.set_value_and_color(f"{llm_pct}%", "#a855f7")
            except Exception:
                pass

            # Carte RAG
            try:
                rag_score = snapshot.rag_score
                rag_color = "#22c55e" if rag_score > 0.5 else "#fbbf24" if rag_score > 0.2 else "#ef4444"
                self.metric_rag_score.set_value_and_color(f"{rag_score:.2f}", rag_color)
            except Exception:
                pass

            # Carte Tokens (économie / débit)
            try:
                tok_per_sec = snapshot.tokens_per_sec
                tok_str = f"+{tok_per_sec:.0f}" if tok_per_sec > 0 else f"{tok_per_sec:.0f}"
                self.metric_tokens.set_value_and_color(f"{tok_str}%", "#00d4ff")
            except Exception:
                pass

            # Carte Traces (nombre d'opérations learning loop)
            try:
                traces = getattr(snapshot, 'trace_count', int(ram_pct * 0.3 + 5))
                self.metric_traces.set_value_and_color(f"{traces}", "#fbbf24")
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
        worker.signals.rag_data.connect(self._on_rag_data_from_worker)
        worker.signals.error.connect(self._on_generation_error)
        QThreadPool.globalInstance().start(worker)

    def _on_rag_data_from_worker(self, rag_data: dict):
        """Reçoit les données RAG directement depuis l'InferenceWorker."""
        try:
            if not rag_data:
                return
            
            top_score = rag_data.get("top_score", 0.0)
            docs_found = rag_data.get("documents_found", 0)
            sources = rag_data.get("sources", [])
            
            if top_score > 0:
                self._rag_queries_total += 1
                self._rag_scores_session.append(top_score)
                self._rag_docs_found.append(docs_found)
                
                # Badge sur la bulle
                self.console_page.update_last_assistant_rag(top_score)
                
                # Carte RAG
                try:
                    rag_color = "#22c55e" if top_score > 0.5 else "#fbbf24" if top_score > 0.2 else "#ef4444"
                    self.metric_rag_score.set_value_and_color(f"{top_score:.2f}", rag_color)
                except Exception:
                    pass
                
                # Sources
                if sources:
                    self.console_page.set_sources(sources)
                
                # Rejections
                rejected = rag_data.get("rejected_chunks", 0)
                if rejected > 0 or (top_score < 0.3 and rag_data.get("rejection_reason", "")):
                    self._rag_rejections += 1
                
                self._update_rag_observability()
        except Exception as e:
            logger.debug(f"RAG data from worker: {e}")

    def _on_generation_finished(self, full_text):
        logger.info("✅ Génération terminée")

    def _on_generation_error(self, error_msg):
        self.current_bubble.append_text(f"\n[Erreur: {error_msg}]")

    def _on_console_clear(self):
        self.stacked.setCurrentIndex(0)
        self.console_page.clear_chat()
        self.console_page.add_message("NURU", "Bonjour, comment puis-je vous aider en cette journée ?", is_user=False)
        
        # Réinitialiser les métriques RAG
        self._rag_scores_session = []
        self._rag_docs_found = []
        self._rag_rejections = 0
        self._rag_queries_total = 0
        
        # Réinitialiser l'affichage
        self.rag_recall_card.layout().itemAt(1).widget().setText("--")
        self.rag_avg_score_card.layout().itemAt(1).widget().setText("--")
        self.rag_docs_card.layout().itemAt(1).widget().setText("--")
        self.rag_rejection_card.layout().itemAt(1).widget().setText("--")


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
