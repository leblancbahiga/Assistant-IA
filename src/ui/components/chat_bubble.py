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

from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QDateTime
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
from src.ui.components.markdown_renderer import MarkdownRenderer

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
    fact_clicked = Signal(str)       # P1-O — clic sur badge fact-check

    def __init__(
        self,
        text: str = "",
        role: str = "nuru",
        sources: list[tuple[str, int]] | None = None,
        show_actions: bool = True,
        confidence: float | None = None,
        mode: str = "",               # V11.1 P0-N — mode de routage (LOCAL/RAG/CLOUD/VERIFY/PLAN)
        model_name: str = "",         # V11.1 P0-N — nom du modèle (ex: "Groq llama")
        fact_status: str | None = None,  # V11.1 P0-O — "verified"/"issues"/"error"/"pending"
        thinking_tokens: int = 0,     # P1-M — nombre de tokens de raisonnement
        fact_sources: int = 0,        # P1-O — nombre de sources vérifiées
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
        self._thinking_tokens = thinking_tokens         # P1-M
        self._fact_sources = fact_sources               # P1-O
        self._thinking_expanded = False                 # P1-M — état du toggle
        self._thinking_timestamp = QDateTime.currentDateTime()  # P1-M — fraîcheur
        self._thinking_anim_running = False             # P1-M — garde anti-réentrance

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

        # ── 2a-bis. Thinking block (P1-M) — raisonnement repliable amélioré ──
        # Wrapper container for the entire thinking block
        self._thinking_block = QWidget()
        self._thinking_block.setObjectName("ThinkingBlockWrapper")
        self._thinking_block.setVisible(False)
        thinking_layout = QVBoxLayout(self._thinking_block)
        thinking_layout.setContentsMargins(0, 0, 0, 0)
        thinking_layout.setSpacing(0)

        # Header — clickable toggle with ▶/▼ icon, freshness, token count
        self._thinking_header = QPushButton()
        self._thinking_header.setObjectName("ThinkingToggleBtn")
        self._thinking_header.setCursor(Qt.PointingHandCursor)
        self._thinking_header.clicked.connect(self._toggle_thinking)
        self._thinking_header.setStyleSheet(
            "QPushButton#ThinkingToggleBtn {"
            "  background-color: #121620;"
            "  border: 1px solid #2A2A4E;"
            "  border-radius: 6px 6px 0 0;"
            "  color: #A855F7;"
            "  font-size: 11px;"
            "  font-weight: bold;"
            "  padding: 6px 10px;"
            "  text-align: left;"
            "}"
            "QPushButton#ThinkingToggleBtn:hover {"
            "  background-color: #1A1E2E;"
            "  border: 1px solid #A855F7;"
            "}"
        )
        thinking_layout.addWidget(self._thinking_header)

        # Content area with animated height (slides open/closed)
        self._thinking_content_container = QWidget()
        self._thinking_content_container.setObjectName("ThinkingContentContainer")
        self._thinking_content_container.setMaximumHeight(0)
        _cc_layout = QVBoxLayout(self._thinking_content_container)
        _cc_layout.setContentsMargins(0, 0, 0, 0)
        _cc_layout.setSpacing(0)

        self._thinking_content = QLabel()
        self._thinking_content.setWordWrap(True)
        self._thinking_content.setTextFormat(Qt.RichText)
        self._thinking_content.setObjectName("ThinkingContent")
        # Style cyberpunk : fond #0D1117, bordure gauche 3px #A855F7, padding
        self._thinking_content.setStyleSheet(
            "QLabel#ThinkingContent {"
            "  background-color: #0D1117;"
            "  border-left: 3px solid #A855F7;"
            "  border-right: 1px solid #2A2A4E;"
            "  border-bottom: 1px solid #2A2A4E;"
            "  border-radius: 0 0 6px 6px;"
            "  color: #C0D0E0;"
            "  font-size: 12px;"
            "  padding: 8px 10px;"
            "}"
        )
        _cc_layout.addWidget(self._thinking_content)
        thinking_layout.addWidget(self._thinking_content_container)
        layout.addWidget(self._thinking_block)

        # Animation : dépliage/repliage fluide via maximumHeight
        self._thinking_animation = QPropertyAnimation(
            self._thinking_content_container, b"maximumHeight"
        )
        self._thinking_animation.setDuration(300)
        self._thinking_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._thinking_animation.finished.connect(self._on_thinking_anim_finished)

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

    # ── 2e. Badge FactChecker (P1-O) ──

    def _build_fact_badge(self, status: str) -> QLabel:
        """Badge coloré indiquant le résultat du FactChecker.

        Amélioré P1-O :
        - Icônes unicode : ✅/⚠️/❌/⏳
        - Couleurs cyberpunk NURU
        - Nombre de sources vérifiées
        - Cliquable (émet fact_clicked(status))
        - Tooltip descriptif
        """
        # Définir les constantes selon le statut
        status_data = {
            "verified": {
                "icon": "✅",
                "label": "Vérifié",
                "bg": "#0A2A10",
                "border": "#1A4A1A",
                "color": "#4ADE80",
                "tooltip": "✅ Vérifié — Toutes les affirmations sont supportées par les sources",
                "tooltip_src": "{} sources concordantes",
            },
            "issues": {
                "icon": "⚠️",
                "label": "Problèmes",
                "bg": "#2A1A0A",
                "border": "#4A3A1A",
                "color": "#FBBF24",
                "tooltip": "⚠️ Problèmes — Certaines affirmations n'ont pas pu être vérifiées",
                "tooltip_src": "{} incohérences détectées",
            },
            "error": {
                "icon": "❌",
                "label": "Erreur",
                "bg": "#2A0A0A",
                "border": "#4A1A1A",
                "color": "#F87171",
                "tooltip": "❌ Erreur — Contradictions détectées avec les sources",
                "tooltip_src": "{} contradictions avec les sources",
            },
            "pending": {
                "icon": "⏳",
                "label": "Vérification...",
                "bg": "#0A1A2A",
                "border": "#1A3A4A",
                "color": "#60A5FA",
                "tooltip": "⏳ Vérification en cours...",
                "tooltip_src": None,
            },
        }

        data = status_data.get(status)
        if data is None:
            return QLabel()

        # Construire l'affichage : icône + label + nombre de sources
        if self._fact_sources > 0 and data["tooltip_src"]:
            display = f"{data['icon']} {data['label']} · {self._fact_sources}"
            tooltip = f"{data['tooltip']}\n{data['tooltip_src'].format(self._fact_sources)}"
        else:
            display = f"{data['icon']} {data['label']}"
            tooltip = data["tooltip"]

        badge = QLabel(display)
        badge.setToolTip(tooltip)
        badge.setStyleSheet(
            f"background-color: {data['bg']};"
            f" border: 0.5px solid {data['border']};"
            f" border-radius: 10px;"
            f" color: {data['color']};"
            f" font-size: 9px;"
            f" font-weight: bold;"
            f" padding: 2px 8px;"
        )

        # Rendre cliquable — émet fact_clicked(status) au clic
        badge.setCursor(Qt.PointingHandCursor)
        badge.mousePressEvent = lambda e, s=status: self._on_fact_badge_clicked(e, s)

        return badge

    def _on_fact_badge_clicked(self, event, status: str) -> None:
        """Gère le clic sur un badge fact-check."""
        self.fact_clicked.emit(status)

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

        clean = MarkdownRenderer.strip_markdown(self._full_text)
        QGuiApplication.clipboard().setText(clean)
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

    def set_thinking(self, text: str, thinking_tokens: int = 0) -> None:
        """Définit le texte de raisonnement et rend le bloc visible.

        Le contenu est initialement masqué (replié).
        L'utilisateur peut cliquer sur l'en-tête pour déplier/replier.

        Parameters
        ----------
        text : str
            Contenu du raisonnement (Markdown supporté).
        thinking_tokens : int
            Nombre de tokens de raisonnement (0 = caché).
        """
        self._thinking_text = text
        self._thinking_tokens = thinking_tokens or self._thinking_tokens
        self._thinking_timestamp = QDateTime.currentDateTime()
        html = self._markdown_to_html(text)
        self._thinking_content.setText(html)
        self._thinking_block.setVisible(True)
        self._thinking_expanded = False
        self._thinking_content_container.setMaximumHeight(0)
        self._update_thinking_header_text()

    # ── P1-M : Animation et helpers du thinking block ──

    def _toggle_thinking(self) -> None:
        """Bascule l'affichage du bloc de raisonnement avec animation."""
        if self._thinking_anim_running:
            return
        self._thinking_anim_running = True
        self._thinking_expanded = not self._thinking_expanded

        anim = self._thinking_animation
        anim.stop()

        if self._thinking_expanded:
            # Mesurer la hauteur naturelle du contenu
            self._thinking_content_container.setMaximumHeight(16777215)
            self._thinking_content_container.adjustSize()
            natural = self._thinking_content_container.minimumSizeHint().height()
            if natural <= 0:
                natural = self._thinking_content_container.sizeHint().height()
            if natural <= 0:
                natural = 200  # fallback
            # Réinitialiser à 0 pour l'animation départ → arrivée
            self._thinking_content_container.setMaximumHeight(0)
            self._thinking_content_container.updateGeometry()
            anim.setStartValue(0)
            anim.setEndValue(natural)
        else:
            current = self._thinking_content_container.height()
            target = 0
            if current > 0:
                anim.setStartValue(current)
            else:
                anim.setStartValue(200)
            anim.setEndValue(target)

        anim.start()
        self._update_thinking_header_text()

    def _on_thinking_anim_finished(self) -> None:
        """Callback de fin d'animation."""
        self._thinking_anim_running = False
        if not self._thinking_expanded:
            self._thinking_content_container.setMaximumHeight(0)
        # else: la hauteur naturelle est déjà appliquée par l'animation

    def _update_thinking_header_text(self) -> None:
        """Met à jour le texte de l'en-tête avec icône, fraîcheur et tokens."""
        icon = "▼" if self._thinking_expanded else "▶"
        freshness = self._get_freshness_label()
        tokens = f" · {self._thinking_tokens} tokens" if self._thinking_tokens else ""
        self._thinking_header.setText(f"{icon} Raisonnement · {freshness}{tokens}")

    def _get_freshness_label(self) -> str:
        """Retourne un libellé de fraîcheur basé sur le timestamp."""
        secs = self._thinking_timestamp.secsTo(QDateTime.currentDateTime())
        return "récent" if secs < 30 else "plus ancien"

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
        """Convertit le Markdown en HTML via ``MarkdownRenderer``.

        Si la bibliothèque ``markdown`` est absente, fallback vers l'ancien
        convertisseur regex (``_fallback_html``) pour ne rien casser.
        """
        return MarkdownRenderer.render(text)

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
    fact_clicked = Signal(str)          # P1-O — clic sur badge fact-check

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
        thinking_tokens: int = 0,     # P1-M
        fact_sources: int = 0,        # P1-O
        message_id: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._message_id = message_id or self._generate_id()
        self._role = role.lower()
        self._mode = mode.upper() if mode else ""       # V11.1 P0-N
        self._model_name = model_name                   # V11.1 P0-N
        self._fact_status = fact_status                 # V11.1 P0-O
        self._thinking_tokens = thinking_tokens         # P1-M
        self._fact_sources = fact_sources               # P1-O

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
            mode=self._mode,                     # V11.1 P0-N
            model_name=self._model_name,          # V11.1 P0-N
            fact_status=self._fact_status,        # V11.1 P0-O
            thinking_tokens=self._thinking_tokens,  # P1-M
            fact_sources=self._fact_sources,       # P1-O
        )

        # Connexions des signaux
        self._bubble.feedback_positive.connect(self._on_feedback_positive)
        self._bubble.feedback_negative.connect(self._on_feedback_negative)
        self._bubble.citation_clicked.connect(self.citation_clicked.emit)
        # V11.1 (P0-H) — regenerate / edit propagés avec message_id
        self._bubble.regenerate_requested.connect(self._on_regenerate)
        self._bubble.edit_requested.connect(self._on_edit)
        # P1-O — clic sur badge fact-check propagé
        self._bubble.fact_clicked.connect(self.fact_clicked.emit)

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

    def set_thinking(self, text: str, thinking_tokens: int = 0) -> None:
        """Proxy : définit le raisonnement de la bulle."""
        self._bubble.set_thinking(text, thinking_tokens)

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
