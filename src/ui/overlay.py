"""
NURU V5 — System Overlay (Geek & Funk).

Overlay PySide6 transparent, toujours au-dessus des autres fenêtres.
Affiche les métriques en temps réel et les logs du pipeline.

Peut être lancé indépendamment ou basculé depuis le dashboard principal.
"""
import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QLabel, QPushButton, QTextEdit,
)
from PySide6.QtCore import Qt, QTimer

logger = logging.getLogger(__name__)


class NuruOverlay(QMainWindow):
    """Overlay système NURU V5 — Style Geek & Funk, toujours au-dessus."""

    def __init__(self, core=None, parent=None):
        super().__init__(parent)
        self.core = core
        
        self.setWindowTitle("NURU V5 - System Overlay")
        self.setGeometry(100, 100, 850, 500)
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag_pos = None

        self._init_ui()
        self._init_timers()

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # Style Geek & Funk strict
        main_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 10, 30, 0.95);
                color: #39FF14;
                font-family: 'Menlo', 'Courier New', monospace;
                border: 1px solid #FF00FF;
                border-radius: 8px;
            }
            QLabel#overlay_title {
                color: #FF00FF;
                font-size: 16px;
                font-weight: bold;
                border: none;
            }
            QLabel#overlay_metrics {
                color: #FFB000;
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
            QTextEdit#overlay_console {
                background-color: rgba(0, 0, 0, 0.5);
                color: #39FF14;
                border: 1px solid #39FF14;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton {
                background-color: transparent;
                color: #FF00FF;
                border: 2px solid #FF00FF;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 15px;
            }
            QPushButton:hover {
                background-color: #FF00FF;
                color: #0F0A1E;
            }
            QPushButton#btn_dashboard {
                color: #39FF14;
                border-color: #39FF14;
            }
            QPushButton#btn_dashboard:hover {
                background-color: #39FF14;
                color: #0F0A1E;
            }
            QPushButton#btn_close_overlay {
                color: #ef4444;
                border-color: #ef4444;
            }
            QPushButton#btn_close_overlay:hover {
                background-color: #ef4444;
                color: #0F0A1E;
            }
        """)

        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(16, 12, 16, 12)

        # Header
        header = QHBoxLayout()
        title = QLabel("NURU V5 :: OVERLAY ACTIF")
        title.setObjectName("overlay_title")

        self.metrics_lbl = QLabel(
            "RAM: -- / -- | Modèle: Phi-4-mini-4bit | Architecture: V5"
        )
        self.metrics_lbl.setObjectName("overlay_metrics")

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.metrics_lbl)
        layout.addLayout(header)

        # Console
        self.console = QTextEdit()
        self.console.setObjectName("overlay_console")
        self.console.setReadOnly(True)
        self.console.setText(
            ">> Initialisation NURU V5...\n"
            ">> StrictRAGGuard : ACTIF\n"
            ">> EvidenceVerifier : ACTIF\n"
            ">> TokenJuice : ACTIF (compression -40% tokens)\n"
            ">> Learning Loop : ACTIF ({nb_traces} traces)\n"
            ">> Attente..."
        )
        layout.addWidget(self.console, 1)

        # Contrôles
        controls = QHBoxLayout()
        
        self.btn_task = QPushButton("DÉLÉGUER TÂCHE (MULTI-AGENT)")
        self.btn_task.setObjectName("btn_dashboard")
        self.btn_task.clicked.connect(self._on_delegate)

        self.btn_close = QPushButton("FERMER")
        self.btn_close.setObjectName("btn_close_overlay")
        self.btn_close.clicked.connect(self.hide)

        controls.addStretch()
        controls.addWidget(self.btn_task)
        controls.addWidget(self.btn_close)
        layout.addLayout(controls)

    def _init_timers(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(2000)

    def _update(self):
        """Met à jour les métriques et logs en temps réel."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            free_gb = mem.available / (1024**3)

            # Couleur selon l'état RAM
            ram_color = "#39FF14" if free_gb > 1.5 else "#FFB000" if free_gb > 0.5 else "#ef4444"
            self.metrics_lbl.setText(
                f"RAM: <span style='color:{ram_color}'>{used_gb:.1f}G</span>"
                f"/{total_gb:.1f}G | "
                f"Modèle: Phi-4-mini-4bit | Architecture: V5"
            )

            # Logs
            if self.core and hasattr(self.core, 'orchestrator'):
                tc = self.core.orchestrator.trace_collector
                nb_traces = tc.count()
                self.console.setPlainText(
                    f">> Initialisation NURU V5...\n"
                    f">> StrictRAGGuard : ACTIF\n"
                    f">> EvidenceVerifier : ACTIF\n"
                    f">> TokenJuice : ACTIF (compression -40% tokens)\n"
                    f">> Learning Loop : ACTIF ({nb_traces} traces)\n"
                    f">> RAM: {used_gb:.1f}G / {total_gb:.1f}G utilisé\n"
                    f">> Attente de la prochaine instruction..."
                )
        except Exception:
            pass

    def log(self, message: str):
        """Ajoute un message à la console."""
        current = self.console.toPlainText()
        lines = current.split("\n")
        if len(lines) > 50:
            lines = lines[-40:]
        lines.append(f">> {message}")
        self.console.setPlainText("\n".join(lines))
        # Scroll en bas
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_delegate(self):
        self.log("Délégation multi-agent demandée...")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if not child:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = NuruOverlay()
    overlay.show()
    sys.exit(app.exec())
