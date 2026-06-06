"""
NURU V7 — ChatBubble, AvatarWidget, MessageRow.

Design Aether Dashboard / interface de chat minimaliste.

- AvatarWidget : cercle 26×26, initiale sur fond coloré
- ChatBubble : QFrame avec texte + citations (CitationBadge) + actions (👍👎📋)
- MessageRow : rangée complète avatar + bulle avec alignement selon le rôle

Signaux hiérarchiques :
  MessageRow.feedback_positive(message_id) / feedback_negative(message_id)
  MessageRow.citation_clicked(path, page)
  ChatBubble.feedback_positive / feedback_negative (sans ID)
  ChatBubble.citation_clicked(path, page)
"""
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QSizePolicy,
)
from src.ui.components.nuru_widgets import CitationBadge

# ── Constantes V7 ──────────────────────────────────────────────────────────

NURU_BG = "#1e2540"
NURU_FG = "#7f77dd"
USER_BG = "#1a2e20"
USER_FG = "#1d9e75"
BUBBLE_NURU_BG = "#16162a"
BUBBLE_NURU_BORDER = "rgba(127, 119, 221, 0.2)"
BUBBLE_USER_BG = "#1a1a2e"
BUBBLE_USER_BORDER = "rgba(29, 158, 117, 0.2)"
TEXT_COLOR = "#e2e8f0"
MUTED_COLOR = "#6b7280"
CONFIDENCE_COLORS: dict[str, str] = {
    "high": "#639922",
    "mid": "#ef9f27",
    "low": "#e24b4a",
}


# ── 1. AvatarWidget ───────────────────────────────────────────────────────


class AvatarWidget(QLabel):
    """Avatar circulaire 26×26 avec initiale sur fond coloré.

    - role="nuru" : ``N`` sur fond ``#1e2540``, texte ``#7f77dd``
    - role="user" : initiales sur fond ``#1a2e20``, texte ``#1d9e75``

    Le border-radius de 7px + fixedSize 26×26 donne un cercle.
    """

    def __init__(
        self,
        text: str = "N",
        role: str = "nuru",
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._role = role.lower()
        self.setFixedSize(26, 26)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(self._compute_style())

    def _compute_style(self) -> str:
        bg, fg = (USER_BG, USER_FG) if self._role == "user" else (NURU_BG, NURU_FG)
        return (
            f"background-color: {bg};"
            f"color: {fg};"
            "font-size: 11px;"
            "font-weight: bold;"
            "border-radius: 7px;"
        )

    def set_avatar_text(self, text: str) -> None:
        """Change le texte affiché (utile pour utilisateur)."""
        self.setText(text)


# ── 2. ChatBubble ─────────────────────────────────────────────────────────


class ChatBubble(QFrame):
    """Bulle de message unique pour le design V7.

    Paramètres
    ----------
    text : str
        Texte initial (Markdown simple supporté).
    role : {"nuru", "user"}
        Détermine le style visuel (couleur de fond, bordure, objectName).
    sources : list[tuple[str, int]] | None
        Liste de citations ``(chemin_fichier, page)`` affichées sous le texte.
    show_actions : bool
        Affiche les boutons 👍 👎 📋 (désactivé automatiquement pour user).
    confidence : float | None
        Score de confiance (0.0 → 1.0) ; affiché via une barre sous le texte.

    Signaux
    -------
    feedback_positive()
        Émis quand l'utilisateur clique 👍.
    feedback_negative()
        Émis quand l'utilisateur clique 👎.
    citation_clicked(str, int)
        Émis avec ``(source_path, page)`` quand un CitationBadge est cliqué.
    """

    feedback_positive = Signal()
    feedback_negative = Signal()
    citation_clicked = Signal(str, int)  # (source_path, page)

    def __init__(
        self,
        text: str = "",
        role: str = "nuru",
        sources: list[tuple[str, int]] | None = None,
        show_actions: bool = True,
        confidence: float | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._role = role.lower()
        self._sources = sources or []
        self._show_actions = show_actions and self._role != "user"
        self._confidence = confidence
        self._full_text = text
        self._feedback_state: str = ""  # "up", "down", ""

        self.setObjectName("BubbleNuru" if self._role == "nuru" else "BubbleUser")
        self.setStyleSheet(self._bubble_style())

        # ── Layout principal ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # ── 2a. Texte principal ──
        self._text_label = QLabel()
        self._text_label.setWordWrap(True)
        self._text_label.setTextFormat(Qt.RichText)
        self._text_label.setObjectName("BubbleText")
        self._text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self._text_label)

        # ── 2b. Barre de confiance (optionnelle, nuru seulement) ──
        self._confidence_widget: QWidget | None = None
        if confidence is not None and self._role != "user":
            self._confidence_widget = self._build_confidence_bar(confidence)
            layout.addWidget(self._confidence_widget)

        # ── 2c. Citations ──
        self._citations_layout = QHBoxLayout()
        self._citations_layout.setSpacing(4)
        self._citations_layout.setContentsMargins(0, 0, 0, 0)
        for path, page in self._sources:
            badge = CitationBadge(path, page)
            badge.clicked.connect(self._on_citation_clicked)
            self._citations_layout.addWidget(badge)
        self._citations_layout.addStretch()
        layout.addLayout(self._citations_layout)

        # ── 2d. Actions (👍 👎 📋) — nuru seulement ──
        if self._show_actions:
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(2)

            self._btn_up = QPushButton("👍")
            self._btn_down = QPushButton("👎")
            self._btn_copy = QPushButton("📋")

            for btn in (self._btn_up, self._btn_down, self._btn_copy):
                btn.setObjectName("BubbleAction")
                btn.setFixedSize(28, 28)
                btn.setCursor(Qt.PointingHandCursor)

            self._btn_up.setToolTip("Utile")
            self._btn_down.setToolTip("Pas utile")
            self._btn_copy.setToolTip("Copier le message")

            self._btn_up.clicked.connect(self._on_feedback_up)
            self._btn_down.clicked.connect(self._on_feedback_down)
            self._btn_copy.clicked.connect(self._copy_text)

            actions_layout.addWidget(self._btn_up)
            actions_layout.addWidget(self._btn_down)
            actions_layout.addWidget(self._btn_copy)
            actions_layout.addStretch()
            layout.addLayout(actions_layout)

        # Appliquer le texte initial
        self.set_text(text)

    # ── 2e. Style helpers ──

    def _bubble_style(self) -> str:
        if self._role == "user":
            bg, border = BUBBLE_USER_BG, BUBBLE_USER_BORDER
        else:
            bg, border = BUBBLE_NURU_BG, BUBBLE_NURU_BORDER
        return (
            f"#BubbleNuru, #BubbleUser {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            f"  border-radius: 12px;"
            f"}}"
        )

    def _action_btn_style(self) -> str:
        return (
            "QPushButton {"
            "  background-color: rgba(255,255,255,0.04);"
            "  color: #6B7280;"
            "  border: 1px solid rgba(255,255,255,0.08);"
            "  border-radius: 6px;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(127,119,221,0.15);"
            "  color: #7f77dd;"
            "  border: 1px solid rgba(127,119,221,0.3);"
            "}"
            "QPushButton:pressed {"
            "  background-color: rgba(127,119,221,0.25);"
            "}"
        )

    def _active_btn_style(self) -> str:
        return (
            "QPushButton {"
            "  background-color: rgba(127,119,221,0.2);"
            "  color: #7f77dd;"
            "  border: 1px solid rgba(127,119,221,0.4);"
            "  border-radius: 6px;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(127,119,221,0.3);"
            "}"
        )

    def _build_confidence_bar(self, score: float) -> QWidget:
        """Construit une mini barre de confiance (label + barre + pourcentage)."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel("Confiance")
        label.setObjectName("ConfidenceLabel")
        label.setFixedHeight(14)
        layout.addWidget(label)

        bar = QFrame()
        bar.setObjectName("ConfidenceBarBg")
        bar.setFixedHeight(4)
        bar.setFixedWidth(64)
        pct = max(0, min(100, int(score * 100)))
        level = "high" if score >= 0.75 else ("mid" if score >= 0.40 else "low")
        bar_color = CONFIDENCE_COLORS[level]
        # Utilise un QFrame fill via un sous-label
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        fill = QFrame()
        fill.setObjectName("ConfidenceFill")
        fill.setFixedHeight(4)
        fill.setMinimumWidth(0)
        fill.setMaximumWidth(64)
        fill.setFixedWidth(max(1, int(pct / 100 * 64)))
        bar_layout.addWidget(fill)
        bar_layout.addStretch()

        layout.addWidget(bar)

        value_label = QLabel(f"{pct}%")
        value_label.setObjectName("ConfidenceValue")
        layout.addWidget(value_label)
        layout.addStretch()

        return container

    # ── 2f. Feedback internes ──

    def _on_feedback_up(self) -> None:
        if self._feedback_state == "up":
            return
        self._feedback_state = "up"
        self._btn_up.setProperty("feedback", "up")
        self._btn_down.setProperty("feedback", "")
        self.style().unpolish(self._btn_up)
        self.style().polish(self._btn_up)
        self.style().unpolish(self._btn_down)
        self.style().polish(self._btn_down)
        self.feedback_positive.emit()

    def _on_feedback_down(self) -> None:
        if self._feedback_state == "down":
            return
        self._feedback_state = "down"
        self._btn_down.setProperty("feedback", "down")
        self._btn_up.setProperty("feedback", "")
        self.style().unpolish(self._btn_up)
        self.style().polish(self._btn_up)
        self.style().unpolish(self._btn_down)
        self.style().polish(self._btn_down)
        self.feedback_negative.emit()

    def _copy_text(self) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(self._full_text)
        self._btn_copy.setProperty("copied", "true")
        self.style().unpolish(self._btn_copy)
        self.style().polish(self._btn_copy)
        QTimer.singleShot(
            1500, lambda: (
                self._btn_copy.setProperty("copied", ""),
                self.style().unpolish(self._btn_copy),
                self.style().polish(self._btn_copy),
            )
        )

    def _on_citation_clicked(self, path: str, page: int) -> None:
        self.citation_clicked.emit(path, page)

    # ── 2g. API publique ──

    def set_text(self, text: str) -> None:
        """Met à jour le texte avec conversion Markdown → HTML."""
        self._full_text = text
        html = self._markdown_to_html(text)
        self._text_label.setText(html)

    def append_text(self, chunk: str) -> None:
        """Ajoute un fragment de texte (streaming)."""
        self._full_text += chunk
        html = self._markdown_to_html(self._full_text)
        self._text_label.setText(html)

    def set_sources(self, sources: list[tuple[str, int]]) -> None:
        """Remplace les citations affichées."""
        # Vider l'ancien layout
        while self._citations_layout.count():
            item = self._citations_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        # Remplir avec les nouvelles
        for path, page in sources:
            badge = CitationBadge(path, page)
            badge.clicked.connect(self._on_citation_clicked)
            self._citations_layout.addWidget(badge)
        self._citations_layout.addStretch()
        self._sources = list(sources)

    def set_confidence(self, score: float) -> None:
        """Met à jour la barre de confiance (recrée le widget)."""
        self._confidence = score
        if self._confidence_widget is not None:
            # Remplacer le widget de confiance
            idx = self.layout().indexOf(self._confidence_widget)
            if idx >= 0:
                new_widget = self._build_confidence_bar(score)
                self.layout().insertWidget(idx, new_widget)
                self._confidence_widget.deleteLater()
                self._confidence_widget = new_widget

    @property
    def role(self) -> str:
        return self._role

    @property
    def text(self) -> str:
        """Texte brut complet."""
        return self._full_text

    # ── 2h. Markdown → HTML ──

    @staticmethod
    def _markdown_to_html(text: str) -> str:
        """Convertit le Markdown simple en HTML.

        Supporte :
        - Gras ``**texte**``
        - Italique ``*texte*``
        - Code inline `` `code` ``
        - Sauts de ligne
        """
        if not text:
            return ""
        # Échapper HTML
        html = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        # Code inline `...`
        html = re.sub(
            r"`([^`]+)`",
            r'<code style="background:rgba(0,0,0,0.2);'
            r'padding:1px 4px;border-radius:3px;'
            r'font-family:monospace;font-size:12px;">\1</code>',
            html,
        )
        # Gras **...**
        html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)
        # Italique *...*
        html = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html)
        # Sauts de ligne
        html = html.replace("\n", "<br>")
        return f'<div style="line-height: 1.6;">{html}</div>'


# ── 3. MessageRow ─────────────────────────────────────────────────────────


class MessageRow(QWidget):
    """Rangée complète : avatar + bulle.

    Alignement selon le rôle :
    - ``role="nuru"`` → ``[Avatar] [Bubble] [stretch]``
    - ``role="user"`` → ``[stretch] [Bubble] [Avatar]``

    Signaux (avec ``message_id``)
    -----------------------------
    feedback_positive(message_id : str)
    feedback_negative(message_id : str)
    citation_clicked(source_path : str, page : int)
    """

    citation_clicked = Signal(str, int)
    feedback_positive = Signal(str)  # message_id
    feedback_negative = Signal(str)  # message_id

    def __init__(
        self,
        text: str = "",
        role: str = "nuru",
        sources: list[tuple[str, int]] | None = None,
        show_actions: bool = True,
        confidence: float | None = None,
        message_id: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._message_id = message_id or self._generate_id()
        self._role = role.lower()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)

        # Avatar
        avatar_text = self._avatar_text_for_role()
        self._avatar = AvatarWidget(avatar_text, self._role)

        # Bubble
        self._bubble = ChatBubble(
            text=text,
            role=role,
            sources=sources,
            show_actions=show_actions,
            confidence=confidence,
        )

        # Connexions des signaux
        self._bubble.feedback_positive.connect(self._on_feedback_positive)
        self._bubble.feedback_negative.connect(self._on_feedback_negative)
        self._bubble.citation_clicked.connect(self.citation_clicked.emit)

        if self._role == "user":
            layout.addStretch(1)
            layout.addWidget(self._bubble)
            layout.addWidget(self._avatar, 0, Qt.AlignTop)
        else:
            layout.addWidget(self._avatar, 0, Qt.AlignTop)
            layout.addWidget(self._bubble)
            layout.addStretch(1)

    def _avatar_text_for_role(self) -> str:
        if self._role in ("nuru", "assistant"):
            return "N"
        return "U"

    @staticmethod
    def _generate_id() -> str:
        from PySide6.QtCore import QDateTime

        return f"msg_{QDateTime.currentMSecsSinceEpoch()}"

    # ── API publique ──

    def bubble(self) -> ChatBubble:
        """Retourne la bulle interne."""
        return self._bubble

    def avatar(self) -> AvatarWidget:
        """Retourne le widget avatar."""
        return self._avatar

    @property
    def message_id(self) -> str:
        return self._message_id

    @property
    def role(self) -> str:
        return self._role

    # ── Proxies for streaming / backward compat ──

    def append_text(self, chunk: str) -> None:
        """Proxy : ajoute du texte à la bulle interne (streaming)."""
        self._bubble.append_text(chunk)

    def set_rag_score(self, score: float) -> None:
        """Proxy : met à jour la barre de confiance RAG."""
        self._bubble.set_confidence(score)

    def set_text(self, text: str) -> None:
        """Proxy : remplace le texte de la bulle."""
        self._bubble.set_text(text)

    # ── Relais de signaux ──

    def _on_feedback_positive(self) -> None:
        self.feedback_positive.emit(self._message_id)

    def _on_feedback_negative(self) -> None:
        self.feedback_negative.emit(self._message_id)
