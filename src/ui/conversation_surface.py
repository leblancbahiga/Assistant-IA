"""
NURU V12 — ConversationSurface (Z.ai design).

Zone de chat avec bulles alignées :
- Utilisateur : droite, fond accent cyan
- NURU : gauche, fond surface
- Markdown supporté pour les réponses NURU
"""

import logging

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QTextDocument, QAbstractTextDocumentLayout
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy,
    QHBoxLayout, QFrame, QTextBrowser,
)

from src.ui.tokens import Color, Typography, Radius, Spacing

logger = logging.getLogger(__name__)


class BubbleWidget(QFrame):
    """Bulle de chat unique — arrondie, avec alignement selon l'expéditeur."""

    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        self._is_user = is_user

        # Style
        bg = Color.CYAN + "25" if is_user else Color.BG_SURFACE
        text_color = "#FFFFFF" if is_user else Color.TEXT_PRIMARY
        radius = f"{Radius.LARGE}px"
        if is_user:
            radius = f"{Radius.LARGE}px {Radius.LARGE}px {Radius.SMALL}px {Radius.LARGE}px"
        else:
            radius = f"{Radius.LARGE}px {Radius.LARGE}px {Radius.LARGE}px {Radius.SMALL}px"

        self.setStyleSheet(f"""
            BubbleWidget {{
                background-color: {bg};
                border-radius: {radius};
                padding: {Spacing.SM}px;
            }}
        """)
        self.setMaximumWidth(600)

        # Contenu
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(4)

        if is_user:
            # Texte utilisateur simple
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {text_color}; font-size: {Typography.SIZE_BODY}px;"
                                f" font-family: {Typography.FAMILY_BODY}; background: transparent;")
            layout.addWidget(label)
        else:
            # Réponse NURU : markdown
            browser = QTextBrowser()
            browser.setHtml(self._md_to_html(text))
            browser.setOpenExternalLinks(True)
            browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            browser.setStyleSheet(f"""
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
            browser.document().setDocumentMargin(0)
            browser.setMinimumHeight(20)
            # Ajuster hauteur au contenu
            doc = browser.document()
            doc.setTextWidth(browser.viewport().width() - 4)
            layout.addWidget(browser)

    def _md_to_html(self, md: str) -> str:
        """Conversion markdown minimal en HTML pour QTextBrowser."""
        import re
        html = md
        # Code blocks
        html = re.sub(
            r'```(\w*)\n(.*?)```',
            r'<pre style="background:#151B26;padding:8px;border-radius:6px;'
            r'font-family:JetBrains Mono;font-size:11px;overflow-x:auto;">\2</pre>',
            html, flags=re.DOTALL
        )
        # Inline code
        html = re.sub(
            r'`([^`]+)`',
            r'<code style="background:#151B26;padding:1px 4px;border-radius:3px;'
            r'font-family:JetBrains Mono;font-size:11px;">\1</code>',
            html
        )
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
        # Italic
        html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
        # Links
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        # Newlines
        html = html.replace('\n', '<br>')
        return html


class ConversationSurface(QWidget):
    """
    Zone de conversation scrollable.

    Alignement :
      - Messages utilisateur → droite
      - Messages NURU → gauche
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # Scroll area
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
                background: {Color.BG_SURFACE};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {Color.TEXT_DISABLED};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        # Conteneur interne
        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(Spacing.SM)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll)

    def add_message(self, text: str, is_user: bool = False):
        """Ajoute une bulle et scroll en bas."""
        # Structure bulle alignée
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        bubble = BubbleWidget(text, is_user=is_user)

        if is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()

        # Container pour le layout
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)

        # Insérer avant le stretch
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, container
        )

        # Scroll en bas après rendu
        QTimer = __import__('PySide6.QtCore', fromlist=['QTimer']).QTimer
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear(self):
        """Vide la conversation."""
        while self._inner_layout.count() > 1:  # garder le stretch
            item = self._inner_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
