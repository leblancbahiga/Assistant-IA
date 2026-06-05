"""
Logs Page — Lecture en temps réel de nuru.log.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QPlainTextEdit, QPushButton, QComboBox)
from PySide6.QtCore import Qt, QTimer, QFileSystemWatcher
from PySide6.QtGui import QFont, QTextCharFormat, QColor
from pathlib import Path


class LogsPage(QWidget):
    def __init__(self, log_path=None, parent=None):
        super().__init__(parent)
        self.log_path = log_path or Path("logs/nuru.log")
        self._last_pos = 0
        self._filter_level = "ALL"
        self.setup_ui()
        self._setup_watcher()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        header = QHBoxLayout()
        title = QLabel("📋  JOURNAUX")
        title.setObjectName("PageTitle")
        
        self.level_filter = QComboBox()
        self.level_filter.setObjectName("StyledCombo")
        self.level_filter.addItems(["ALL", "INFO", "WARNING", "ERROR", "DEBUG"])
        self.level_filter.currentTextChanged.connect(self._on_filter_changed)
        
        btn_clear = QPushButton("🗑  Effacer")
        btn_clear.setObjectName("GhostButton")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_display)
        
        btn_refresh = QPushButton("↻  Recharger")
        btn_refresh.setObjectName("GhostButton")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self._full_reload)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(QLabel("Filtre :"))
        header.addWidget(self.level_filter)
        header.addWidget(btn_refresh)
        header.addWidget(btn_clear)
        layout.addLayout(header)
        
        # Log stats
        stats = QFrame()
        stats.setObjectName("Panel")
        stats.setFixedHeight(45)
        sl = QHBoxLayout(stats)
        sl.setContentsMargins(15, 5, 15, 5)
        self.stat_lines = QLabel("0 lignes")
        self.stat_lines.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        self.stat_file = QLabel(f"📂 {self.log_path}")
        self.stat_file.setStyleSheet("color: #6B7280; font-size: 11px;")
        self.stat_size = QLabel("0 KB")
        self.stat_size.setStyleSheet("color: #6B7280; font-size: 11px;")
        sl.addWidget(self.stat_lines)
        sl.addStretch()
        sl.addWidget(self.stat_file)
        sl.addWidget(self.stat_size)
        layout.addWidget(stats)
        
        # Log display
        self.log_display = QPlainTextEdit()
        self.log_display.setObjectName("LogDisplay")
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("JetBrains Mono", 11))
        self.log_display.setStyleSheet("""
            QPlainTextEdit#LogDisplay {
                background-color: #0B0F19;
                color: #9CA3AF;
                border: 1px solid #1F2937;
                border-radius: 8px;
                padding: 10px;
                selection-background-color: rgba(0, 242, 255, 0.2);
            }
        """)
        layout.addWidget(self.log_display, stretch=1)
    
    def _setup_watcher(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._check_updates)
        self.timer.start(2000)
    
    def _check_updates(self):
        if not self.isVisible():
            return
        try:
            if self.log_path.exists():
                with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(self._last_pos)
                    new_lines = f.readlines()
                    self._last_pos = f.tell()
                
                if new_lines:
                    for line in new_lines:
                        self._append_line(line.rstrip())
                    
                    size_kb = self.log_path.stat().st_size / 1024
                    self.stat_size.setText(f"{size_kb:.1f} KB")
        except Exception:
            pass
    
    def _append_line(self, line):
        if self._filter_level != "ALL":
            if self._filter_level not in line.upper():
                return
        
        # Coloriser selon le niveau
        if "ERROR" in line:
            colored = f'<span style="color: #EF4444;">{line}</span>'
        elif "WARNING" in line:
            colored = f'<span style="color: #F59E0B;">{line}</span>'
        elif "INFO" in line:
            colored = f'<span style="color: #10B981;">{line}</span>'
        elif "DEBUG" in line:
            colored = f'<span style="color: #6B7280;">{line}</span>'
        else:
            colored = line
        
        self.log_display.appendPlainText(line)
        
        # Update line count
        count = self.log_display.document().blockCount()
        self.stat_lines.setText(f"{count} lignes")
        
        # Auto-scroll
        sb = self.log_display.verticalScrollBar()
        sb.setValue(sb.maximum())
    
    def _full_reload(self):
        self.log_display.clear()
        self._last_pos = 0
        self._check_updates()
    
    def _clear_display(self):
        self.log_display.clear()
        self.stat_lines.setText("0 lignes")
    
    def _on_filter_changed(self, level):
        self._filter_level = level
        self._full_reload()
    
    def showEvent(self, event):
        super().showEvent(event)
        if self.log_display.document().blockCount() <= 1:
            self._full_reload()
