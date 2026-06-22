"""NURU V12 — ConversationSurface (DM-1 "Deep Cyan").

Zone de chat avec bulles alignées :
- Utilisateur : droite, fond accent cyan transparent
- NURU : gauche, fond surface
- Markdown supporté pour les réponses NURU
- Streaming temps réel (token par token)
"""

import logging
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy,
    QHBoxLayout, QFrame, QTextBrowser,
)

from src.ui.tokens import Color, Typography, Radius, Spacing

logger = logging.getLogger(__name__)


class BubbleWidget(QFrame):
    """Bulle de chat — DM-1 : coins arrondis 12px, fond cyan ou surface."""

    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        self._is_user = is_user

        # DM-1 couleurs
        if is_user:
            bg = "rgba(0, 212, 255, 0.10)"
            text_color = Color.TEXT_PRIMARY
            radius = f"{Radius.LARGE}px {Radius.LARGE}px {Radius.SMALL}px {Radius.LARGE}px"
        else:
            bg = Color.BG_SURFACE1
            text_color = Color.TEXT_PRIMARY
            radius = f"{Radius.LARGE}px {Radius.LARGE}px {Radius.LARGE}px {Radius.SMALL}px"

        self.setStyleSheet(f"""
            BubbleWidget {{
                background-color: {bg};
                border-radius: {radius};
                padding: {Spacing.SM}px;
            }}
        """)
        self.setMaximumWidth(600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(4)

        if is_user:
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color: {text_color}; font-size: {Typography.SIZE_BODY}px;"
                f" font-family: {Typography.FAMILY_BODY}; background: transparent;"
            )
            layout.addWidget(label)
        else:
            self._browser = QTextBrowser()
            self._browser.setHtml(self._md_to_html(text))
            self._browser.setOpenExternalLinks(True)
            self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._browser.setStyleSheet(f"""
                QTextBrowser {{
                    background: transparent;
                    color: {text_color};
                    font-size: {Typography.SIZE_BODY}px;
                    font-family: {Typography.FAMILY_BODY};
                    border: none;
                    padding: 0;
                }}
                QTextBrowser a {{ color: {Color.CYAN}; }}
            """)
            self._browser.document().setDocumentMargin(0)
            self._browser.setMinimumHeight(20)
            doc = self._browser.document()
            doc.setTextWidth(self._browser.viewport().width() - 4)
            layout.addWidget(self._browser)

    def append_html(self, html_fragment: str):
        """Ajoute du HTML à la bulle existante (streaming)."""
        cursor = self._browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html_fragment)
        # Auto-scroll au contenu le plus récent
        scrollbar = self._browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _md_to_html(self, md: str) -> str:
        """Conversion markdown minimal en HTML."""
        import re
        html = md
        html = re.sub(
            r'```(\w*)\n(.*?)```',
            r'<pre style="background:#151B26;padding:8px;border-radius:6px;'
            r'font-family:JetBrains Mono;font-size:11px;overflow-x:auto;">\2</pre>',
            html, flags=re.DOTALL
        )
        html = re.sub(
            r'`([^`]+)`',
            r'<code style="background:#151B26;padding:1px 4px;border-radius:3px;'
            r'font-family:JetBrains Mono;font-size:11px;">\1</code>',
            html
        )
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
        html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        html = html.replace('\n', '<br>')
        return html


class ConversationSurface(QWidget):
    """Zone de conversation scrollable — DM-1.

    Alignement :
      - Messages utilisateur → droite
      - Messages NURU → gauche
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: {Color.BG_SURFACE1};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {Color.TEXT_MUTED};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(Spacing.SM)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll)

        # État de streaming
        self._streaming_bubble: BubbleWidget | None = None
        self._stream_buffer: list[str] = []
        self._stream_timer: QTimer | None = None

    # ── Messages normaux ──

    def add_message(self, text: str, is_user: bool = False):
        """Ajoute un message complet (non streamé)."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        bubble = BubbleWidget(text, is_user=is_user)

        if is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)

        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, container
        )

        QTimer.singleShot(50, self._scroll_to_bottom)

    # ── Streaming ──

    def start_stream(self) -> None:
        """Crée une bulle vide pour le streaming de la réponse NURU."""
        # Vider le buffer
        self._stream_buffer = []

        # Forcer l'affichage immédiat du chunk précédent s'il y en a un
        self._flush_stream_buffer()

        # Créer une bulle vide
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        self._streaming_bubble = BubbleWidget("", is_user=False)
        row.addWidget(self._streaming_bubble)
        row.addStretch()

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)

        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, container
        )

        QTimer.singleShot(50, self._scroll_to_bottom)

    def append_to_stream(self, chunk: str) -> None:
        """Ajoute un fragment de texte à la bulle de streaming.

        Utilise un buffer + timer pour grouper les tokens
        et éviter de repeindre trop souvent.
        """
        self._stream_buffer.append(chunk)

        # Déclencher le flush immédiatement (timer unique)
        if self._stream_timer is None or not self._stream_timer.isActive():
            self._stream_timer = QTimer()
            self._stream_timer.setSingleShot(True)
            self._stream_timer.timeout.connect(self._flush_stream_buffer)
            self._stream_timer.start(30)  # ms — batch tokens toutes les 30ms

    def _flush_stream_buffer(self) -> None:
        """Vide le buffer dans la bulle de streaming."""
        if not self._stream_buffer or self._streaming_bubble is None:
            return

        text = "".join(self._stream_buffer)
        self._stream_buffer = []

        # Échapper le HTML avant insertion
        safe = (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>"))
        self._streaming_bubble.append_html(safe)
        self._scroll_to_bottom()

    def end_stream(self) -> None:
        """Finalise la bulle de streaming."""
        # Vider le buffer restant
        self._flush_stream_buffer()
        self._streaming_bubble = None

        # Nettoyer le timer
        if self._stream_timer and self._stream_timer.isActive():
            self._stream_timer.stop()
        self._stream_timer = None

    # ── Utilitaires ──

    def _scroll_to_bottom(self):
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear(self):
        self.end_stream()
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
