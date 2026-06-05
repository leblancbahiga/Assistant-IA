"""
NURU V6 — System Page : État en temps réel des modules V6.

Affiche :
- TokenJuice : ratio de compression, stats
- Learning Loop : traces collectées, mining, suggestions
- Nuru_Brain : fichiers dans le wiki, taille
- Auto-Fetch : état, dernier scan
- Stratégie hybride : mode actif + changement à la volée
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QPushButton, QComboBox,
    QCheckBox, QProgressBar, QSizePolicy, QGridLayout,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


class SystemModuleCard(QFrame):
    """Carte d'état pour un module V6."""
    
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
        icon_lbl.setStyleSheet(f"font-size: 20px;")
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


class V6ControlPanel(QFrame):
    """Panneau de contrôle des modules V6."""
    
    toggled = Signal(str, bool)  # module_name, enabled
    
    def __init__(self, parent=None):
        super().__init__(parent)
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
        
        title = QLabel("⚙️ Contrôle des Modules V6")
        title.setStyleSheet("color: #FF00FF; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)
        
        self.toggles = {}
        modules = [
            ("🧃 TokenJuice", "token_juice"),
            ("📝 Learning Loop", "learning"),
            ("🌲 Nuru_Brain", "nuru_brain"),
            ("📥 Auto-Fetch", "auto_fetch"),
            ("🔀 Stratégie Hybride", "hybrid"),
        ]
        
        for label, name in modules:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #E0E7FF; font-size: 12px;")
            cb = QCheckBox()
            cb.setChecked(True)
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
            row.addWidget(cb)
            layout.addLayout(row)
        
        # Sélecteur de stratégie hybride
        strategy_row = QHBoxLayout()
        strategy_lbl = QLabel("Mode hybride:")
        strategy_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["local_only", "verify", "plan", "rag"])
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
        strategy_row.addWidget(strategy_lbl)
        strategy_row.addWidget(self.strategy_combo)
        strategy_row.addStretch()
        layout.addLayout(strategy_row)


class SystemPage(QWidget):
    """Page d'état des modules V6."""
    
    def __init__(self, config=None, core=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.core = core
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
        title = QLabel("📊 Modules NURU V6")
        title.setStyleSheet("""
            font-size: 22px; font-weight: bold; color: #39FF14;
            letter-spacing: 2px;
        """)
        layout.addWidget(title)
        
        subtitle = QLabel("État en temps réel des nouveaux modules")
        subtitle.setStyleSheet("color: #6b7280; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(subtitle)
        
        # Grille de cartes
        grid = QHBoxLayout()
        grid.setSpacing(16)
        
        # TokenJuice
        self.tj_card = SystemModuleCard("TokenJuice", "🧃", "#FF00FF")
        self.tj_card.add_metric("Compressions", "—", "#39FF14")
        self.tj_card.add_metric("Ratio", "—", "#FFB000")
        grid.addWidget(self.tj_card)
        
        # Learning Loop
        self.learn_card = SystemModuleCard("Learning Loop", "📝", "#39FF14")
        self.learn_card.add_metric("Traces", "—", "#39FF14")
        self.learn_card.add_metric("Échecs", "—", "#FFB000")
        grid.addWidget(self.learn_card)
        
        # Nuru_Brain
        self.brain_card = SystemModuleCard("Nuru_Brain", "🌲", "#FFB000")
        self.brain_card.add_metric("Fichiers", "—", "#39FF14")
        self.brain_card.add_metric("Dernière sync", "—", "#A78BFA")
        grid.addWidget(self.brain_card)
        
        # Auto-Fetch
        self.fetch_card = SystemModuleCard("Auto-Fetch", "📥", "#00F2FF")
        self.fetch_card.add_metric("Sources surveillées", "—", "#39FF14")
        self.fetch_card.add_metric("Dernier scan", "—", "#A78BFA")
        grid.addWidget(self.fetch_card)
        
        layout.addLayout(grid)
        
        # Panneau de contrôle
        self.control_panel = V6ControlPanel()
        self.control_panel.toggled.connect(self._on_module_toggle)
        layout.addWidget(self.control_panel)
        
        # Label du mode actif
        self.mode_label = QLabel("Mode actuel : Archon (RAG local → Cloud synthèse)")
        self.mode_label.setStyleSheet("""
            color: #FFB000; font-size: 12px; padding: 8px;
            background-color: rgba(255, 176, 0, 0.05);
            border: 1px solid rgba(255, 176, 0, 0.2);
            border-radius: 8px;
        """)
        layout.addWidget(self.mode_label)
        
        layout.addStretch()
    
    def _refresh(self):
        """Met à jour les métriques depuis les modules."""
        try:
            from src.token_juice import TokenJuice
            juice = TokenJuice()
            stats = juice.stats
            
            self.tj_card.set_status(stats["compressions"] > 0)
            self._safe_set_metric(self.tj_card, 0, str(stats["compressions"]))
            ratio = stats.get("compression_ratio", 0)
            self._safe_set_metric(self.tj_card, 1, f"{ratio*100:.0f}%")
        except Exception as e:
            logger.debug(f"SystemPage refresh TJ: {e}")
        
        try:
            if self.core and hasattr(self.core, 'orchestrator'):
                tc = self.core.orchestrator.trace_collector
                count = tc.count()
                self.learn_card.set_status(count > 0)
                self._safe_set_metric(self.learn_card, 0, str(count))
                failed = len(tc.get_failed(limit=1))
                self._safe_set_metric(self.learn_card, 1, str(failed))
        except Exception as e:
            logger.debug(f"SystemPage refresh Learn: {e}")
        
        try:
            from src.nuru_brain import WikiWriter
            wiki = WikiWriter()
            stats = wiki.get_stats()
            self.brain_card.set_status(stats["files"] > 0)
            self._safe_set_metric(self.brain_card, 0, str(stats["files"]))
        except Exception as e:
            logger.debug(f"SystemPage refresh Brain: {e}")
        
        try:
            from src.auto_fetch import AutoFetcher
            af = AutoFetcher(enabled=True)
            stats = af.get_stats()
            self.fetch_card.set_status(stats["enabled"])
            self._safe_set_metric(self.fetch_card, 0, str(stats["sources"]))
            tracked = stats["tracked_files"]
            self._safe_set_metric(self.fetch_card, 1, f"{tracked} fichiers")
        except Exception as e:
            logger.debug(f"SystemPage refresh Fetch: {e}")
    
    def _safe_set_metric(self, card, index: int, value: str):
        """Met à jour une métrique d'une carte de façon sécurisée."""
        try:
            layout = card.metrics_layout
            item = layout.itemAt(index)
            if item and item.layout():
                row = item.layout()
                if row.count() >= 2:
                    val_lbl = row.itemAt(1).widget()
                    if val_lbl:
                        val_lbl.setText(value)
        except Exception:
            pass
    
    def _on_module_toggle(self, name: str, enabled: bool):
        logger.info(f"Module {name} → {'ON' if enabled else 'OFF'}")
        # La modification réelle de config se ferait via le settings panel
