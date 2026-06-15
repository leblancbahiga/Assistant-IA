"""
NURU V10 — FeedbackPage : historique et statistiques des retours utilisateur.

Utilise FeedbackCollector pour afficher :
  - Statistiques globales (thumbs up/down, corrections, ratings 1‑5)
  - Flux des retours récents avec détail
  - Graphiques simples au fil du temps
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QStyle, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)

try:
    from src.learning.feedback import FeedbackCollector
except ImportError:
    FeedbackCollector = None


# ── Widgets réutilisables ─────────────────────────────────────────────────


class StatCard(QFrame):
    """Carte de statistique unique (titre, valeur, icône)."""

    def __init__(self, title: str, value: str, icon: str = "📊",
                 color: str = "#60a5fa", parent=None):
        super().__init__(parent)
        self._color = color
        self.setObjectName("StatCard")
        self.setStyleSheet(f"""
            StatCard {{
                background: rgba(30, 40, 60, 0.8);
                border: 1px solid {color}40;
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(QLabel(f"<span style='font-size:18px'>{icon}</span>"))
        top.addStretch()
        layout.addLayout(top)
        self._value_label = QLabel(
            f"<span style='font-size:26px;font-weight:700;color:{color}'>{value}</span>")
        layout.addWidget(self._value_label)
        layout.addWidget(QLabel(
            f"<span style='color:#8899b0;font-size:12px'>{title}</span>"))


class FeedbackRow(QFrame):
    """Ligne de feedback individuel dans le flux."""

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("FeedbackRow")
        ts = entry.get("timestamp", 0)
        dt = datetime.fromtimestamp(ts).strftime("%d/%m %H:%M") if ts else "?"
        ftype = entry.get("feedback_type", "?")
        value = entry.get("value", "")
        query = entry.get("query", "")[:80]

        icons = {"thumbs_up": "👍", "thumbs_down": "👎",
                 "correction": "✏️", "rating": "⭐"}
        icon = icons.get(ftype, "💬")

        self.setStyleSheet("""
            FeedbackRow {
                background: rgba(20, 30, 50, 0.6);
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 12px;
                margin: 2px 0;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(QLabel(f"<span style='font-size:16px'>{icon}</span>"))
        layout.addWidget(QLabel(
            f"<span style='color:#94a3b8;font-size:11px'>{dt}</span>"))
        layout.addWidget(QLabel(
            f"<span style='color:#e2e8f0;font-size:12px'>{query}</span>"), stretch=1)
        if ftype == "rating":
            layout.addWidget(QLabel(
                f"<span style='color:#fbbf24;font-size:13px'>{'★' * int(float(value))}</span>"))
        elif ftype == "correction":
            layout.addWidget(QLabel(
                f"<span style='color:#34d399;font-size:11px'>✏️ {value[:40]}</span>"))


# ── FeedbackPage principale ────────────────────────────────────────────────

class FeedbackPage(QWidget):
    """Page de visualisation des retours utilisateur."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collector: Optional[FeedbackCollector] = None
        # Ensure the data directory exists
        try:
            (Path.home() / ".nuru").mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Impossible de créer ~/.nuru/: %s", e)
        try:
            db_path = str(Path.home() / ".nuru" / "feedback.db")
            self._collector = FeedbackCollector(db_path=db_path)
        except Exception as e:
            logger.warning("FeedbackCollector non disponible: %s", e)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Titre
        title = QLabel("💬 Feedback — Retours utilisateur")
        title.setStyleSheet("font-size:22px;font-weight:700;color:#e2e8f0")
        layout.addWidget(title)

        # ── Stats ──
        self._stats_grid = QHBoxLayout()
        self._stats_grid.setSpacing(12)

        self._card_up = StatCard("👍 Thumbs Up", "—", "👍", "#34d399")
        self._card_down = StatCard("👎 Thumbs Down", "—", "👎", "#f87171")
        self._card_corrections = StatCard("✏️ Corrections", "—", "✏️", "#60a5fa")
        self._card_ratings = StatCard("⭐ Notes", "—", "⭐", "#fbbf24")

        self._stats_grid.addWidget(self._card_up)
        self._stats_grid.addWidget(self._card_down)
        self._stats_grid.addWidget(self._card_corrections)
        self._stats_grid.addWidget(self._card_ratings)
        layout.addLayout(self._stats_grid)

        # ── Flux récent ──
        layout.addWidget(QLabel(
            "<span style='color:#94a3b8;font-size:13px;font-weight:600'>"
            "Flux récent</span>"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent; border:none")
        self._feed_widget = QWidget()
        self._feed_layout = QVBoxLayout(self._feed_widget)
        self._feed_layout.setSpacing(4)
        self._feed_layout.setContentsMargins(0, 0, 0, 0)
        self._feed_layout.addStretch()
        scroll.setWidget(self._feed_widget)
        layout.addWidget(scroll, stretch=1)

        # ── Refresh ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = QPushButton("🔄 Rafraîchir")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: #334155; color: #e2e8f0;
                border: 1px solid #475569; border-radius: 6px;
                padding: 8px 20px; font-size: 13px;
            }
            QPushButton:hover { background: #475569; }
        """)
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self._refresh()

        # Auto-refresh toutes les 10s
        self._feedback_timer = QTimer(self)
        self._feedback_timer.timeout.connect(self._refresh)
        self._feedback_timer.start(10000)

    def set_data(self, data: dict) -> None:
        """API V9 : reçoit stats + recent du dashboard (alternative au collector interne)."""
        stats = data.get("stats", {})
        recent = data.get("recent", [])
        up = stats.get("thumbs_up", 0)
        down = stats.get("thumbs_down", 0)
        corr = stats.get("corrections", 0)
        rating_count = stats.get("rating_count", 0)
        rating_avg = stats.get("rating_avg", 0.0)
        self._update_card(self._card_up, str(up))
        self._update_card(self._card_down, str(down))
        self._update_card(self._card_corrections, str(corr))
        avg_text = f"{rating_avg:.1f}★" if rating_count > 0 else f"{rating_count}"
        self._update_card(self._card_ratings, avg_text)

        self._clear_feed()
        for entry in recent:
            row = FeedbackRow(entry)
            self._feed_layout.insertWidget(self._feed_layout.count() - 1, row)
        if not recent:
            label = QLabel("Aucun feedback enregistré. Le feedback est collecté "
               "automatiquement pendant vos conversations.")
            label.setStyleSheet("color:#64748b;font-size:13px;padding:20px")
            label.setAlignment(Qt.AlignCenter)
            self._feed_layout.insertWidget(0, label)

    def _refresh(self):
        """Rafraîchit stats + flux depuis FeedbackCollector."""
        if not self._collector:
            # Clear stats cards
            self._update_card(self._card_up, "—")
            self._update_card(self._card_down, "—")
            self._update_card(self._card_corrections, "—")
            self._update_card(self._card_ratings, "—")
            # Show explanation in the feed
            self._clear_feed()
            msg = QLabel(
                "⚠️ Collecteur de feedback non disponible\n\n"
                "Le module FeedbackCollector n'a pas pu être chargé ou la base "
                "de données n'a pas pu être ouverte. Vérifiez que la dépendance "
                "src.learning.feedback est correctement installée et que le "
                "répertoire ~/.nuru/ est accessible."
            )
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(
                "color:#f87171;font-size:13px;padding:30px;"
                "background:rgba(248,113,113,0.08);border-radius:8px;"
            )
            self._feed_layout.insertWidget(0, msg)
            return

        try:
            stats = self._collector.get_stats()
        except Exception as e:
            logger.warning("Feedback stats error: %s", e)
            stats = {}

        up = stats.get("thumbs_up", 0)
        down = stats.get("thumbs_down", 0)
        corr = stats.get("corrections", 0)
        rating_count = stats.get("rating_count", 0)
        rating_avg = stats.get("rating_avg", 0.0)

        self._update_card(self._card_up, str(up))
        self._update_card(self._card_down, str(down))
        self._update_card(self._card_corrections, str(corr))
        avg_text = f"{rating_avg:.1f}★" if rating_count > 0 else f"{rating_count}"
        self._update_card(self._card_ratings, avg_text)

        # Flux récent
        self._clear_feed()
        try:
            recent = self._collector.get_recent(limit=50)
        except Exception as e:
            logger.warning("Feedback recent error: %s", e)
            recent = []

        for entry in recent:
            row = FeedbackRow(entry)
            self._feed_layout.insertWidget(self._feed_layout.count() - 1, row)

        if not recent:
            label = QLabel("Aucun feedback enregistré. Le feedback est collecté "
               "automatiquement pendant vos conversations.")
            label.setStyleSheet("color:#64748b;font-size:13px;padding:20px")
            label.setAlignment(Qt.AlignCenter)
            self._feed_layout.insertWidget(0, label)

    @staticmethod
    def _update_card(card: StatCard, value: str):
        """Met à jour la valeur d'une StatCard."""
        card._value_label.setText(
            f"<span style='font-size:26px;font-weight:700;color:{card._color}'>{value}</span>")

    def _clear_feed(self):
        """Vide le flux (garde le stretch final)."""
        while self._feed_layout.count() > 1:
            item = self._feed_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
