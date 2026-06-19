"""
NURU V8+ — ChatBubble, AvatarWidget, MessageRow.

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
from src.ui.components.nuru_widgets import CitationBadge, ModeBadge
from src.ui.components.right_panel import CitationChip

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
    regenerate_requested = Signal()  # V11.1 P0-H — demande régénération
    edit_requested = Signal()        # V11.1 P0-H — demande édition user msg

    def __init__(
        self,
        text: str = "",
        role: str = "nuru",
        sources: list[tuple[str, int]] | None = None,
        show_actions: bool = True,
        confidence: float | None = None,
        mode: str = "",               # V11.1 P0-N — mode de routage (LOCAL/RAG/CLOUD/VERIFY/PLAN)
        model_name: str = "",         # V11.1 P0-N — nom du modèle (ex: "Groq llama")
        fact_status: str | None = None,  # V11.1 P0-O — "verified"/"issues"/"error"
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._role = role.lower()
        self._sources = sources or []
        self._show_actions = show_actions and self._role != "user"
        self._confidence = confidence
        self._full_text = text
        self._feedback_state: str = ""  # "up", "down", ""
        self._mode = mode.upper() if mode else ""      # V11.1 P0-N
        self._model_name = model_name                   # V11.1 P0-N
        self._fact_status = fact_status                 # V11.1 P0-O

        self.setObjectName(
            "BubbleNuru" if self._role in ("nuru", "assistant") else "BubbleUser"
        )
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
        self._text_label.linkActivated.connect(self._on_link_activated)  # V11.1 P0-M
        layout.addWidget(self._text_label)

        # ── 2a-bis. Thinking block (P1-M) — raisonnement repliable ──
        self._thinking_content = QLabel()
        self._thinking_content.setWordWrap(True)
        self._thinking_content.setTextFormat(Qt.RichText)
        self._thinking_content.setObjectName("ThinkingBlock")
        self._thinking_content.setVisible(False)
        layout.addWidget(self._thinking_content)

        self._thinking_btn = QPushButton("🤔 Afficher le raisonnement")
        self._thinking_btn.setObjectName("ThinkingToggleBtn")
        self._thinking_btn.setVisible(False)
        self._thinking_btn.setCursor(Qt.PointingHandCursor)
        self._thinking_btn.clicked.connect(self._toggle_thinking)
        layout.addWidget(self._thinking_btn)

        # ── 2b. Badges inline (confiance + citations) ──
        self._badges_layout = QHBoxLayout()
        self._badges_layout.setSpacing(4)
        self._badges_layout.setContentsMargins(0, 0, 0, 0)

        # Badge de confiance inline
        self._confidence_badge: QLabel | None = None
        if confidence is not None and self._role != "user":
            self._confidence_badge = self._build_confidence_badge(confidence)
            self._badges_layout.addWidget(self._confidence_badge)

        # Badge FactChecker status (P0-O)
        self._fact_badge: QLabel | None = None
        if self._fact_status and self._role != "user":
            self._fact_badge = self._build_fact_badge(self._fact_status)
            self._badges_layout.addWidget(self._fact_badge)

        # Badges de source (CitationChip)
        for path, page in self._sources:
            chip = CitationChip(path)
            chip.mousePressEvent = lambda e, p=path, pg=page: self.citation_clicked.emit(p, pg)
            chip.setCursor(Qt.PointingHandCursor)
            self._badges_layout.addWidget(chip)

        self._badges_layout.addStretch()
        layout.addLayout(self._badges_layout)

        # ── 2c. Ancien layout citations (conservé pour compat) ──
        self._citations_layout = QHBoxLayout()
        self._citations_layout.setSpacing(4)
        self._citations_layout.setContentsMargins(0, 0, 0, 0)
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
            self._btn_regen = QPushButton("🔄")
            self._btn_edit = QPushButton("✏️")

            for btn in (self._btn_up, self._btn_down, self._btn_copy, self._btn_regen, self._btn_edit):
                btn.setObjectName("BubbleAction")
                btn.setFixedSize(28, 28)
                btn.setCursor(Qt.PointingHandCursor)

            self._btn_up.setToolTip("Utile")
            self._btn_down.setToolTip("Pas utile")
            self._btn_copy.setToolTip("Copier le message")
            self._btn_regen.setToolTip("Régénérer la réponse")
            self._btn_edit.setToolTip("Éditer le message")

            self._btn_up.clicked.connect(self._on_feedback_up)
            self._btn_down.clicked.connect(self._on_feedback_down)
            self._btn_copy.clicked.connect(self._copy_text)
            self._btn_regen.clicked.connect(self.regenerate_requested.emit)
            self._btn_edit.clicked.connect(self.edit_requested.emit)

            actions_layout.addWidget(self._btn_up)
            actions_layout.addWidget(self._btn_down)
            actions_layout.addWidget(self._btn_copy)
            actions_layout.addWidget(self._btn_regen)
            # Le bouton edit apparaît aussi sur les bulles user (édition possible)
            actions_layout.addWidget(self._btn_edit)
            actions_layout.addStretch()
            layout.addLayout(actions_layout)

        # ── 2e. Mode footer (P0-N) — modèle + routeur, assistant seulement ──
        if self._role != "user" and self._mode:
            footer_layout = QHBoxLayout()
            footer_layout.setContentsMargins(0, 2, 0, 0)
            footer_layout.setSpacing(6)

            # Libellé du modèle
            if self._model_name:
                model_label = QLabel(self._model_name)
                model_label.setStyleSheet(
                    "color: #4A6080; font-size: 10px; background: transparent;"
                )
                footer_layout.addWidget(model_label)

            # Badge de routage
            self._mode_badge = ModeBadge(self._mode)
            footer_layout.addWidget(self._mode_badge)

            footer_layout.addStretch()
            layout.addLayout(footer_layout)

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

    def _build_confidence_badge(self, score: float) -> QLabel:
        """Construit un badge de confiance inline.

        Style :
        - high (>=0.5) : fond #081A0D, bordure #1A3A1F, texte #2A8A3A
        - low (<0.5)   : fond #1A0F05, bordure #3A2A0A, texte #9A7A2A
        """
        level = "high" if score >= 0.50 else ("mid" if score >= 0.40 else "low")
        pct = max(0, min(100, int(score * 100)))

        if score >= 0.5:
            bg = "#081A0D"
            border = "#1A3A1F"
            color = "#2A8A3A"
            level_text = "HAUTE"
        else:
            bg = "#1A0F05"
            border = "#3A2A0A"
            color = "#9A7A2A"
            level_text = "FAIBLE"

        display = f"● Confiance {level_text} · {pct}%"
        badge = QLabel(display)
        badge.setStyleSheet(
            f"background-color: {bg};"
            f" border: 0.5px solid {border};"
            f" border-radius: 10px;"
            f" color: {color};"
            f" font-size: 9px;"
            f" font-weight: bold;"
            f" padding: 2px 8px;"
        )
        return badge

    # ── 2e. Badge FactChecker (P0-O) ──

    def _build_fact_badge(self, status: str) -> QLabel:
        """Badge coloré indiquant le résultat du FactChecker.

        - verified (#22C55E vert) : tout supporté par les sources
        - issues (#F59E0B orange) : certaines affirmations non vérifiées
        - error (#EF4444 rouge)   : contradictions avec les sources
        """
        if status == "verified":
            dot, label = "●", "Vérifié"
            bg, border, color = "#0A1F0A", "#1A3F1A", "#22C55E"
        elif status == "issues":
            dot, label = "●", "Incertain"
            bg, border, color = "#1A1405", "#3A2E0A", "#F59E0B"
        elif status == "error":
            dot, label = "●", "Non vérifié"
            bg, border, color = "#1A0A0A", "#3A1A1A", "#EF4444"
        else:
            return QLabel()

        display = f"{dot} {label}"
        badge = QLabel(display)
        badge.setStyleSheet(
            f"background-color: {bg};"
            f" border: 0.5px solid {border};"
            f" border-radius: 10px;"
            f" color: {color};"
            f" font-size: 9px;"
            f" font-weight: bold;"
            f" padding: 2px 8px;"
        )
        return badge

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

    # ── 2h. Gestionnaire liens inline (P0-M) ──

    def _on_link_activated(self, url: str) -> None:
        """Gère les clics sur les liens dans le texte.

        citations:[N] → émet citation_clicked
        autres liens → ouvre dans le navigateur.
        """
        if url.startswith("citation:"):
            num = url.split("citation:")[1]
            self.citation_clicked.emit(f"[{num}]", 0)
        else:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))


    # ── 2g. API publique ──
    def set_text(self, text: str) -> None:
        """Met à jour le texte avec conversion Markdown → HTML."""
        self._full_text = text
        html = self._markdown_to_html(text)
        self._text_label.setText(html)

    def set_thinking(self, text: str) -> None:
        """Définit le texte de raisonnement et rend le bouton visible.

        Le contenu de raisonnement est initialement masqué.
        L'utilisateur peut cliquer sur le bouton pour l'afficher/masquer.
        """
        self._thinking_text = text
        html = self._markdown_to_html(text)
        self._thinking_content.setText(html)
        self._thinking_btn.setVisible(True)

    def _toggle_thinking(self) -> None:
        """Bascule l'affichage du bloc de raisonnement."""
        is_visible = self._thinking_content.isVisible()
        self._thinking_content.setVisible(not is_visible)
        if is_visible:
            self._thinking_btn.setText("🤔 Afficher le raisonnement")
        else:
            self._thinking_btn.setText("🤔 Masquer le raisonnement")

    def append_text(self, chunk: str) -> None:
        """Ajoute un fragment de texte (streaming)."""
        self._full_text += chunk
        html = self._markdown_to_html(self._full_text)
        self._text_label.setText(html)

    def set_sources(self, sources: list[tuple[str, int]]) -> None:
        """Remplace les citations affichées (badges inline)."""
        # Mettre à jour _sources
        self._sources = list(sources)

        # Nettoyer les anciens badges de source de _badges_layout
        # (conserver le badge de confiance et le stretch)
        items_to_remove = []
        for i in range(self._badges_layout.count()):
            item = self._badges_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, CitationChip) or (hasattr(w, '_source_path') and not hasattr(w, '_score')):
                    items_to_remove.append(w)
                elif isinstance(w, QLabel) and w != self._confidence_badge:
                    # Check if it's a source badge (has source_path attr or starts with 📄)
                    if hasattr(w, 'set_source') or hasattr(w, '_source_path'):
                        items_to_remove.append(w)

        for w in items_to_remove:
            self._badges_layout.removeWidget(w)
            w.deleteLater()

        # Ajouter les nouveaux badges
        for path, page in self._sources:
            chip = CitationChip(path)
            chip.mousePressEvent = lambda e, p=path, pg=page: self.citation_clicked.emit(p, pg)
            chip.setCursor(Qt.PointingHandCursor)
            # Insérer avant le stretch (dernier élément)
            self._badges_layout.insertWidget(self._badges_layout.count() - 1, chip)

    def set_confidence(self, score: float) -> None:
        """Met à jour le badge de confiance inline."""
        self._confidence = score
        if self._confidence_badge is not None:
            new_badge = self._build_confidence_badge(score)
            idx = self._badges_layout.indexOf(self._confidence_badge)
            if idx >= 0:
                self._badges_layout.insertWidget(idx, new_badge)
                self._badges_layout.removeWidget(self._confidence_badge)
                self._confidence_badge.deleteLater()
                self._confidence_badge = new_badge
        else:
            # Créer le badge s'il n'existe pas encore
            if self._role != "user":
                self._confidence_badge = self._build_confidence_badge(score)
                self._badges_layout.insertWidget(0, self._confidence_badge)

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
        """Convertit le Markdown simple en HTML, avec citations [N] cliquables."""
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
        # V11.1 P0-M : citations [N] → liens cliquables
        html = ChatBubble._linkify_citations(html)
        return f'<div style="line-height: 1.6;">{html}</div>'

    @staticmethod
    def _linkify_citations(html: str) -> str:
        """Convertit les marqueurs [N] en hyperliens cliquables.

        Exemple: ``[1]`` → ``<a href="citation:1" ...>[1]</a>``
        Ne lie que les crochets numériques non déjà dans un <a>.
        """
        def _replace(m: re.Match) -> str:
            num = m.group(1)
            return (
                f'<a href="citation:{num}" '
                f'style="color:#818cf8;text-decoration:none;'
                f'font-weight:600;border-bottom:1px dotted #6366f1;"'
                f' title="Source {num}">'
                f"[{num}]</a>"
            )
        # Remplacer [N] où N est un nombre, hors balises existantes
        return re.sub(r'(?![^<]*>)\[(\d+)\](?!<)', _replace, html)


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
    regenerate_requested = Signal(str)  # V11.1 P0-H — message_id
    edit_requested = Signal(str)        # V11.1 P0-H — message_id

    def __init__(
        self,
        text: str = "",
        role: str = "nuru",
        sources: list[tuple[str, int]] | None = None,
        show_actions: bool = True,
        confidence: float | None = None,
        mode: str = "",               # V11.1 P0-N
        model_name: str = "",         # V11.1 P0-N
        fact_status: str | None = None,  # V11.1 P0-O
        message_id: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._message_id = message_id or self._generate_id()
        self._role = role.lower()
        self._mode = mode.upper() if mode else ""       # V11.1 P0-N
        self._model_name = model_name                   # V11.1 P0-N
        self._fact_status = fact_status                 # V11.1 P0-O

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
            mode=self._mode,          # V11.1 P0-N
            model_name=self._model_name,  # V11.1 P0-N
            fact_status=self._fact_status,  # V11.1 P0-O
        )

        # Connexions des signaux
        self._bubble.feedback_positive.connect(self._on_feedback_positive)
        self._bubble.feedback_negative.connect(self._on_feedback_negative)
        self._bubble.citation_clicked.connect(self.citation_clicked.emit)
        # V11.1 (P0-H) — regenerate / edit propagés avec message_id
        self._bubble.regenerate_requested.connect(self._on_regenerate)
        self._bubble.edit_requested.connect(self._on_edit)

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

    # V11.1 (P0-H)
    def _on_regenerate(self) -> None:
        self.regenerate_requested.emit(self._message_id)

    def _on_edit(self) -> None:
        self.edit_requested.emit(self._message_id)
