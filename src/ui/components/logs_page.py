"""
Logs Page — Lecture en temps réel de nuru.log avec détection de vétusté.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QPlainTextEdit, QPushButton, QComboBox)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from datetime import datetime, timezone
import html
import logging
from pathlib import Path


STALE_THRESHOLD_SECONDS = 3600  # 1 heure → considéré comme vétuste


class LogsPage(QWidget):
    def __init__(self, log_path=None, parent=None):
        super().__init__(parent)
        # Chemin absolu si relatif passé
        if log_path:
            self.log_path = Path(log_path)
        else:
            # Chemin absolu vers le fichier nuru.log
            self.log_path = Path(
                "/Users/leblancbahiga/Downloads/Assistant IA/logs/nuru.log"
            )
        self._last_pos = 0
        self._filter_level = "ALL"
        self._last_mtime = None  # timestamp de la dernière modif observée
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
        self.stat_file = QLabel("")
        self.stat_file.setStyleSheet("color: #6B7280; font-size: 11px;")
        self.stat_size = QLabel("0 KB")
        self.stat_size.setStyleSheet("color: #6B7280; font-size: 11px;")
        self.stat_age = QLabel("")
        self.stat_age.setStyleSheet("color: #6B7280; font-size: 11px;")
        sl.addWidget(self.stat_lines)
        sl.addStretch()
        sl.addWidget(self.stat_file)
        sl.addWidget(self.stat_size)
        sl.addWidget(self.stat_age)
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

    def _get_file_stat(self):
        """Retourne (taille_kb, mtime_datetime) ou (0, None) si fichier absent."""
        if not self.log_path.exists():
            return 0, None
        st = self.log_path.stat()
        return st.st_size / 1024, datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)

    def _format_age_label(self, mtime):
        """Formate un label de vétusté du fichier."""
        if mtime is None:
            return "⚠️ Fichier introuvable"
        now = datetime.now(timezone.utc)
        delta = now - mtime
        age_str = mtime.strftime("%d/%m %H:%M")
        if delta.total_seconds() > STALE_THRESHOLD_SECONDS:
            # Vétuste → afficher avec avertissement
            if delta.days > 0:
                return f"⚠️ {age_str} (vieux de {delta.days}j)"
            hours = int(delta.total_seconds() // 3600)
            return f"⚠️ {age_str} (vieux de {hours}h)"
        else:
            return f"✓ {age_str}"

    def _update_stats(self):
        """Met à jour tous les indicateurs de la barre de stats."""
        size_kb, mtime = self._get_file_stat()
        count = self.log_display.document().blockCount()

        self.stat_lines.setText(f"{count} lignes")
        self.stat_size.setText(f"{size_kb:.1f} KB" if size_kb else "0 KB")

        # Afficher le chemin et le statut de vétusté
        self.stat_file.setText(f"📂 {self.log_path}")
        age_label = self._format_age_label(mtime)
        self.stat_age.setText(age_label)

        # Colorer le label age selon la vétusté
        if mtime is None:
            self.stat_age.setStyleSheet("color: #EF4444; font-size: 11px;")
        elif (datetime.now(timezone.utc) - mtime).total_seconds() > STALE_THRESHOLD_SECONDS:
            self.stat_age.setStyleSheet("color: #F59E0B; font-size: 11px;")
        else:
            self.stat_age.setStyleSheet("color: #10B981; font-size: 11px;")

    def _load_all_content(self):
        """Lit tout le fichier depuis le début (full reload) sans seek."""
        if not self.log_path.exists():
            return
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                self._last_pos = f.tell()
            self.log_display.clear()
            for line in lines:
                self._append_line(line.rstrip())
            self._update_stats()
        except Exception:
            pass

    def _check_updates(self):
        if not self.isVisible():
            return
        try:
            if self.log_path.exists():
                # Vérifier si le fichier a changé depuis le dernier check
                current_mtime = self.log_path.stat().st_mtime
                file_changed = self._last_mtime is None or current_mtime != self._last_mtime
                self._last_mtime = current_mtime

                if file_changed:
                    # Lecture incrémentale depuis la dernière position
                    with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(self._last_pos)
                        new_lines = f.readlines()
                        self._last_pos = f.tell()

                    if new_lines:
                        for line in new_lines:
                            self._append_line(line.rstrip())

                    # Mise à jour des stats incluant l'âge
                    self._update_stats()
        except Exception:
            pass

    def _append_line(self, line):
        if self._filter_level != "ALL":
            if self._filter_level not in line.upper():
                return

        # Échapper HTML puis coloriser selon le niveau
        escaped = html.escape(line)
        if "ERROR" in line:
            colored = f'<span style="color: #EF4444;">{escaped}</span>'
        elif "WARNING" in line:
            colored = f'<span style="color: #F59E0B;">{escaped}</span>'
        elif "INFO" in line:
            colored = f'<span style="color: #10B981;">{escaped}</span>'
        elif "DEBUG" in line:
            colored = f'<span style="color: #6B7280;">{escaped}</span>'
        else:
            colored = f'<span style="color: #9CA3AF;">{escaped}</span>'

        self.log_display.appendHtml(colored)

        # Update line count (fast)
        count = self.log_display.document().blockCount()
        self.stat_lines.setText(f"{count} lignes")

        # Auto-scroll
        sb = self.log_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _full_reload(self):
        """Recharge intégralement le fichier depuis le début, même si inchangé."""
        self._last_pos = 0
        self._last_mtime = None  # force le rechargement
        self._load_all_content()

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
