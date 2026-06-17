"""
NURU V8+ — Console Page : ChatHeader, MessagesArea, InputArea, ConsolePage.

Design Aether Dashboard V7 :
- ChatHeader : titre, ModeBadge x2, ConfidenceWidget, bouton Nouveau Chat
- MessagesArea : zone scrollable, TypingIndicator (3 points animés), messages via MessageRow
- SmartTextEdit : Entrée = envoi, Shift+Entrée = nouvelle ligne
- InputArea : micro, attach, strict mode, send, SmartTextEdit
- ConsolePage : assemble le tout, backward compatible avec CyberDashboard
"""

from typing import Optional

import logging

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from .nuru_widgets import ConfidenceWidget, ModeBadge, TypingIndicator
from .chat_bubble import MessageRow, ChatBubble


# ── 1. ChatHeader ────────────────────────────────────────────────────────


class ChatHeader(QWidget):
    """Header du chat : titre, model switcher, modes, confiance, bouton Nouveau Chat.

    Signaux
    -------
    new_chat_clicked : émis quand l'utilisateur clique sur le bouton "+"
    model_changed(str) : émis quand l'utilisateur choisit un modèle dans le
        combobox (V11.1 P0-E)
    """

    new_chat_clicked = Signal()
    model_changed = Signal(str)  # V11.1 P0-E — nouveau modèle sélectionné

    MODELS = [
        "phi-4-mini (local)",
        "llama-3.3-70b (groq)",
        "deepseek-chat",
        "openrouter-auto",
    ]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ChatHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(12)

        # ── Titre ──
        self._title_label = QLabel("Nouvelle conversation")
        self._title_label.setObjectName("ChatHeaderTitle")
        layout.addWidget(self._title_label)

        # ── Model Switcher (P0-E) ──
        self._model_combo = QComboBox()
        self._model_combo.setObjectName("ModelSwitcher")
        self._model_combo.addItems(self.MODELS)
        self._model_combo.setCurrentIndex(0)
        self._model_combo.setFixedWidth(200)
        self._model_combo.setToolTip("Modèle actif")
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        layout.addWidget(self._model_combo)

        layout.addSpacing(8)

        # ── ModeBadge primaire ──
        self._mode_primary = ModeBadge("LOCAL")
        layout.addWidget(self._mode_primary)

        # ── ModeBadge secondaire ──
        self._mode_secondary = ModeBadge("RAG")
        layout.addWidget(self._mode_secondary)

        layout.addSpacing(8)

        # ── ConfidenceWidget ──
        self._confidence = ConfidenceWidget()
        layout.addWidget(self._confidence)

        layout.addStretch()

        # ── Bouton Nouveau Chat ──
        self._btn_new = QPushButton("＋")
        self._btn_new.setObjectName("NewChatHeaderBtn")
        self._btn_new.setFixedSize(36, 36)
        self._btn_new.setCursor(Qt.PointingHandCursor)
        self._btn_new.setToolTip("Nouveau Chat")
        self._btn_new.clicked.connect(self.new_chat_clicked.emit)
        layout.addWidget(self._btn_new)

    # ── API publique ──

    def set_title(self, title: str) -> None:
        """Change le titre du header."""
        self._title_label.setText(title)

    def set_modes(self, primary: str, secondary: str) -> None:
        """Change les badges de mode (LOCAL, RAG, CLOUD, VERIFY, PLAN)."""
        self._mode_primary.set_mode(primary)
        self._mode_secondary.set_mode(secondary)

    def set_confidence(self, score: float) -> None:
        """Met à jour la barre de confiance (0.0 → 1.0)."""
        self._confidence.set_score(score)

    def set_model(self, model_name: str) -> None:
        """V11.1 P0-E — Sélectionne un modèle dans le combobox."""
        idx = self._model_combo.findText(model_name)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)

    @property
    def current_model(self) -> str:
        """V11.1 P0-E — Modèle actuellement sélectionné."""
        return self._model_combo.currentText()

    def reset(self) -> None:
        """Réinitialise le header à l'état par défaut."""
        self._title_label.setText("Nouvelle conversation")
        self._mode_primary.set_mode("LOCAL")
        self._mode_secondary.set_mode("RAG")
        self._confidence.set_score(0.0)

    # ── Internes ──

    def _on_model_changed(self, model_name: str) -> None:
        """Relaye le changement de modèle."""
        self.model_changed.emit(model_name)


# ── 2. MessagesArea ──────────────────────────────────────────────────────


class MessagesArea(QScrollArea):
    """Zone de messages scrollable avec TypingIndicator.

    Signaux
    -------
    citation_clicked(str, int)    : (source_path, page)
    feedback_positive(str)        : message texte
    feedback_negative(str)        : message texte
    regenerate_requested(str)     : message_id assistant (V11.1 P0-H)
    edit_requested(str)           : message_id user ou assistant (V11.1 P0-H)
    """

    citation_clicked = Signal(str, int)
    feedback_positive = Signal(str)
    feedback_negative = Signal(str)
    # V11.1 (P0-H)
    regenerate_requested = Signal(str)  # message_id assistant
    edit_requested = Signal(str)        # message_id user ou assistant

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("MessagesArea")

        # Conteneur interne (P0-K : objectName pour max-width chat R3)
        self._container = QWidget()
        self._container.setObjectName("ChatContent")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(20, 10, 20, 10)
        self._layout.setSpacing(12)
        self._layout.setAlignment(Qt.AlignTop)

        # Stretch en bas pour pousser les messages vers le haut
        self._stretch = QWidget()
        self._stretch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._layout.addWidget(self._stretch)

        self.setWidget(self._container)

        # TypingIndicator (caché par défaut)
        self._typing = TypingIndicator(self._container)
        self._typing.setVisible(False)
        # On l'ajoute dans le layout après le stretch, mais on le gère manuellement

        # Dernière bulle assistant (pour backward compat et mise à jour RAG)
        self._last_assistant_row: MessageRow | None = None

        # Compteur de messages ajoutés (debug doublage)
        self._message_add_count: int = 0

        # Dernier texte utilisateur ajouté (pour détection de doublage)
        self._last_user_text: str = ""

    # ── API publique ──

    def add_message(
        self,
        text: str,
        role: str = "user",
        sources: list | None = None,
        confidence: float | None = None,
        mode: str = "",               # V11.1 P0-N
        model_name: str = "",         # V11.1 P0-N
    ) -> MessageRow:
        """Ajoute un message dans la zone de chat.

        Paramètres
        ----------
        text : str
            Contenu du message.
        role : str
            "user" ou "assistant".
        sources : list, optional
            Liste de noms de fichiers sources.
        confidence : float, optional
            Score de confiance RAG (0.0 → 1.0).

        Retourne
        --------
        MessageRow
            Le widget message ajouté (API compatible ChatBubble).
        """
        logger.debug("MessagesArea.add_message: role=%s, text_len=%d, visible=%s, total=%d",
                     role, len(text), self._typing.isVisible(), self._message_add_count)

        # Détection de doublage : comparer avec le dernier message utilisateur
        if role == "user" and self._last_user_text and self._last_user_text == text:
            logger.warning("DUPLICATE USER MESSAGE DETECTED: text=%s (count=%d)",
                           text[:60], self._message_add_count)

        self._message_add_count += 1
        row = MessageRow(
            text=text,
            role=role,
            sources=sources,
            confidence=confidence,
            mode=mode,                # V11.1 P0-N
            model_name=model_name,    # V11.1 P0-N
            parent=self._container,
        )

        # Connecter les signaux de feedback (assistant seulement)
        if role != "user":
            row.feedback_positive.connect(self._on_feedback_positive)
            row.feedback_negative.connect(self._on_feedback_negative)
        # V11.1 (P0-H) — regenerate / edit propagés vers ConsolePage
        row.regenerate_requested.connect(self.regenerate_requested.emit)
        row.edit_requested.connect(self.edit_requested.emit)

        if role != "user":
            self._last_assistant_row = row
        else:
            self._last_user_text = text

        # Insérer avant le stretch (avant-dernière position)
        idx = self._layout.count() - 1  # just before stretch
        # Si le typing indicator est visible, insérer avant lui aussi
        if self._typing.isVisible():
            idx = self._layout.count() - 2  # before typing + stretch
            if idx < 0:
                idx = 0

        self._layout.insertWidget(idx, row)
        self._scroll_to_bottom()
        return row

    def show_typing(self) -> None:
        """Affiche l'indicateur de frappe animé (3 points)."""
        if not self._typing.isVisible():
            # Insérer le typing indicator avant le stretch
            idx = self._layout.count() - 1  # just before stretch
            if idx < 0:
                idx = 0
            self._layout.insertWidget(idx, self._typing)
            self._typing.start()
            self._typing.setVisible(True)
            self._scroll_to_bottom()

    def hide_typing(self) -> None:
        """Cache l'indicateur de frappe."""
        self._typing.stop()
        self._typing.setVisible(False)

    def clear(self) -> None:
        """Supprime tous les messages de la zone."""
        # Supprimer tous les widgets sauf le stretch et le typing
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w and w is not self._stretch and w is not self._typing:
                w.deleteLater()
            elif w is self._stretch:
                # Remettre le stretch à la fin
                self._layout.addWidget(self._stretch)
                break
        self._last_assistant_row = None
        self._last_user_text = ""
        self._message_add_count = 0

    # ── Internes ──

    def _on_feedback_positive(self, message_id: str) -> None:
        """Relaye le feedback positif des bulles assistant."""
        self.feedback_positive.emit(message_id)

    def _on_feedback_negative(self, message_id: str) -> None:
        """Relaye le feedback négatif des bulles assistant."""
        self.feedback_negative.emit(message_id)

    def _scroll_to_bottom(self) -> None:
        """Défile automatiquement vers le bas."""
        QTimer.singleShot(50, self._do_scroll)

    def _do_scroll(self) -> None:
        sb = self.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())


# ── 3. SmartTextEdit ──────────────────────────────────────────────────────


class SmartTextEdit(QTextEdit):
    """QTextEdit intelligent : Entrée envoie, Shift+Entrée = nouvelle ligne.

    Signaux
    -------
    send_triggered : émis quand l'utilisateur appuie sur Entrée (sans Shift).
    """

    send_triggered = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SmartTextEdit")
        self.setAcceptRichText(False)
        self.setPlaceholderText("Posez une question sur vos documents...")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMinimumHeight(44)
        self.setMaximumHeight(120)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
            self.send_triggered.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


# ── 4. InputArea ─────────────────────────────────────────────────────────


class InputArea(QWidget):
    """Barre de saisie du chat : micro, attach, strict mode, send, SmartTextEdit.

    Signaux
    -------
    send_clicked(str)     : texte saisi
    strict_toggled(bool)  : état du mode strict
    voice_toggled()       : demande d'activation micro
    """

    send_clicked = Signal(str)
    strict_toggled = Signal(bool)
    voice_toggled = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InputArea")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 12)
        layout.setSpacing(4)

        # ── Conteneur principal ──
        input_frame = QFrame()
        input_frame.setObjectName("InputFrameV7")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(6)

        # ── Micro ──
        self._btn_mic = QPushButton("🎙")
        self._btn_mic.setObjectName("MicButton")
        self._btn_mic.setFixedSize(34, 34)
        self._btn_mic.setCursor(Qt.PointingHandCursor)
        self._btn_mic.setToolTip("Mode vocal")
        self._btn_mic.setCheckable(True)
        self._btn_mic.clicked.connect(self.voice_toggled.emit)
        input_layout.addWidget(self._btn_mic)

        # ── Attach ──
        self._btn_attach = QPushButton("📎")
        self._btn_attach.setObjectName("AttachButton")
        self._btn_attach.setFixedSize(34, 34)
        self._btn_attach.setCursor(Qt.PointingHandCursor)
        self._btn_attach.setToolTip("Joindre un fichier")
        input_layout.addWidget(self._btn_attach)

        # ── SmartTextEdit ──
        self._text_edit = SmartTextEdit()
        self._text_edit.send_triggered.connect(self._on_send)
        input_layout.addWidget(self._text_edit, stretch=1)

        # ── Strict mode (checkable) ──
        self._btn_strict = QPushButton("🛡")
        self._btn_strict.setObjectName("StrictButton")
        self._btn_strict.setFixedSize(34, 34)
        self._btn_strict.setCursor(Qt.PointingHandCursor)
        self._btn_strict.setCheckable(True)
        self._btn_strict.setToolTip("Mode Strict (RAG uniquement)")
        self._btn_strict.toggled.connect(self.strict_toggled.emit)
        input_layout.addWidget(self._btn_strict)

        # ── Send ──
        self._btn_send = QPushButton("↑")
        self._btn_send.setObjectName("SendButtonV7")
        self._btn_send.setFixedSize(34, 34)
        self._btn_send.setCursor(Qt.PointingHandCursor)
        self._btn_send.setToolTip("Envoyer")
        self._btn_send.clicked.connect(self._on_send)
        input_layout.addWidget(self._btn_send)

        layout.addWidget(input_frame)

        # ── Hint ──
        self._hint = QLabel("Entrée = Envoyer  •  Shift+Entrée = Nouvelle ligne")
        self._hint.setObjectName("InputHint")
        self._hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._hint)

        # ── Listening label (micro actif) ──
        self._listening_label = QLabel(
            "🎙 NURU écoute... (cliquez 🔴 pour arrêter, auto-stop 15s)"
        )
        self._listening_label.setObjectName("ListeningLabel")
        self._listening_label.setAlignment(Qt.AlignCenter)
        self._listening_label.setVisible(False)
        layout.addWidget(self._listening_label)

    # ── API publique ──

    def set_enabled(self, enabled: bool) -> None:
        """Active / désactive la saisie et le bouton send."""
        self._text_edit.setEnabled(enabled)
        self._btn_send.setEnabled(enabled)

    def is_strict(self) -> bool:
        """Retourne l'état actuel du mode strict."""
        return self._btn_strict.isChecked()

    def set_mic_active(self, active: bool) -> None:
        """Met à jour l'état visuel du micro."""
        self._btn_mic.setChecked(active)
        self._btn_mic.setText("🔴" if active else "🎙")
        self._btn_mic.setToolTip("Arrêter l'écoute" if active else "Mode vocal")

    def set_listening_visible(self, visible: bool) -> None:
        """Affiche ou cache l'indicateur d'écoute vocale."""
        self._listening_label.setVisible(visible)

    def clear_input(self) -> None:
        """Vide le champ de saisie."""
        self._text_edit.clear()

    def set_placeholder(self, text: str) -> None:
        """Change le placeholder du champ de saisie."""
        self._text_edit.setPlaceholderText(text)

    def set_strict(self, strict: bool) -> None:
        """Set strict mode programmatically."""
        self._btn_strict.setChecked(strict)

    # ── Internes ──

    def _on_send(self) -> None:
        text = self._text_edit.toPlainText().strip()
        if text:
            self._text_edit.clear()
            self.send_clicked.emit(text)


# ── 5. ConsolePage ────────────────────────────────────────────────────────


class ConsolePage(QWidget):
    """Page principale du chat. Assemble ChatHeader + MessagesArea + InputArea.

    Signaux (V7)
    ------------
    query_submitted(str, bool)  : (query, strict_mode)
    citation_clicked(str, int)  : (source_path, page)
    feedback_positive(str)      : message texte
    feedback_negative(str)      : message texte
    new_chat                    : nouvelle conversation demandée

    Signaux legacy (backward compat CyberDashboard)
    -----------------------------------------------
    clear_requested   : demande de nettoyage du chat
    web_search_toggled(bool) : état de la recherche web
    voice_toggled     : déclenchement du mode vocal
    feedback_received(str, str, str) : (vote, message, query)
    """

    # V7 signals
    query_submitted = Signal(str, bool)
    citation_clicked = Signal(str, int)
    feedback_positive = Signal(str)
    feedback_negative = Signal(str)
    # V11.1 (P0-H)
    regenerate_requested = Signal(str)  # message_id assistant
    edit_requested = Signal(str)        # message_id user ou assistant
    # V11.1 JOUR 3 (P0-J)
    session_loaded = Signal(str)        # session_id restaurée depuis sidebar
    # V11.1 P0-E
    model_changed = Signal(str)         # nouveau modèle sélectionné
    new_chat = Signal()

    # Legacy signals (backward compat)
    clear_requested = Signal()
    web_search_toggled = Signal(bool)
    voice_toggled = Signal()
    feedback_received = Signal(str, str, str)  # (vote, message, query)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ConsolePage")

        # État interne
        self._last_query: str = ""
        self._web_search_enabled: bool = False
        self._sources: list = []
        self._session_store = None  # V11.1 JOUR 3 — injecté via set_session_store()

        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── ChatHeader ──
        self.header = ChatHeader()
        layout.addWidget(self.header)

        # ── MessagesArea (prend tout l'espace) ──
        self.messages = MessagesArea()
        layout.addWidget(self.messages, stretch=1)

        # ── InputArea ──
        self.input_area = InputArea()
        layout.addWidget(self.input_area)

    def _wire_signals(self) -> None:
        # Header → new_chat
        self.header.new_chat_clicked.connect(self._on_new_chat)

        # InputArea → query
        self.input_area.send_clicked.connect(self._on_query)
        self.input_area.strict_toggled.connect(self.web_search_toggled.emit)
        self.input_area.voice_toggled.connect(self.voice_toggled.emit)

        # MessagesArea → feedback / citations
        self.messages.feedback_positive.connect(
            lambda msg: self.feedback_positive.emit(msg)
        )
        self.messages.feedback_negative.connect(
            lambda msg: self.feedback_negative.emit(msg)
        )
        self.messages.feedback_positive.connect(
            lambda msg: self.feedback_received.emit("up", msg, self._last_query)
        )
        self.messages.feedback_negative.connect(
            lambda msg: self.feedback_received.emit("down", msg, self._last_query)
        )

        # V11.1 (P0-H) — regenerate / edit depuis MessagesArea
        self.messages.regenerate_requested.connect(self.regenerate_requested.emit)
        self.messages.edit_requested.connect(self.edit_requested.emit)

        # V11.1 P0-E — model_changed depuis ChatHeader
        self.header.model_changed.connect(self.model_changed.emit)

    # ── API publique V7 ──

    def on_response_received(
        self,
        text: str,
        sources: list | None = None,
        confidence: float | None = None,
        mode_primary: str | None = None,
        mode_secondary: str | None = None,
    ) -> None:
        """Reçoit une réponse complète de l'assistant.

        Paramètres
        ----------
        text : str
            Texte de la réponse.
        sources : list, optional
            Liste de noms de fichiers sources.
        confidence : float, optional
            Score de confiance (0.0 → 1.0).
        mode_primary : str, optional
            Mode principal (LOCAL, RAG, CLOUD, ...).
        mode_secondary : str, optional
            Mode secondaire.
        """
        self.messages.hide_typing()
        self.messages.add_message(
            text=text,
            role="assistant",
            sources=sources or [],
            confidence=confidence,
            mode=mode_primary or "",            # V11.1 P0-N
            model_name=mode_secondary or "",    # V11.1 P0-N — fallback: affiché comme nom
        )
        # Mettre à jour le header
        if mode_primary is not None and mode_secondary is not None:
            self.header.set_modes(mode_primary, mode_secondary)
        if confidence is not None:
            self.header.set_confidence(confidence)

    def on_response_error(self, error_msg: str) -> None:
        """Affiche une erreur dans une bulle assistant."""
        self.messages.hide_typing()
        self.messages.add_message(
            text=f"⚠️ {error_msg}",
            role="assistant",
        )

    # ── Legacy API (backward compat CyberDashboard) — V11.1 P0-F réduite ──

    def clear_chat(self) -> None:
        """Supprime tous les messages (V6 compat, appelé par _on_new_chat)."""
        self.messages.clear()
        self.header.reset()
        self.clear_requested.emit()

    # ── V11.1 JOUR 3 (P0-J) — Restauration de session depuis sidebar ────

    def load_session(self, session_id: str, *, title: str = "") -> None:
        """Charge une session existante dans la zone de messages.

        Vide le chat actuel, lit les messages depuis ``SessionStore``,
        les re-rend dans l'ordre chronologique, et met à jour le titre
        du header.

        Paramètres
        ----------
        session_id : str
            Identifiant de la session à restaurer.
        title : str, optional
            Titre à afficher dans le header. Si vide, on garde
            "Nouvelle conversation" comme défaut visuel.

        Notes
        -----
        - Le ``session_store`` doit être fourni via ``set_session_store()``
          avant l'appel. Si None, on émet un warning et on vide l'écran.
        - Les messages sont rendus tels que stockés (user/assistant).
          Pas de streaming, pas de re-génération.
        - Émet ``session_loaded(session_id)`` pour que le dashboard
          puisse switcher d'onglet (→ "console") et mettre à jour
          ``self._session_id``.
        """
        # 1. Reset UI
        self.messages.clear()
        self.header.reset()
        if title:
            self.header.set_title(title)

        # 2. Récupération du store
        store = self._session_store
        if store is None:
            logger.warning(
                "ConsolePage.load_session: aucun SessionStore injecté. "
                "Appeler set_session_store() d'abord. (session_id=%s)",
                session_id,
            )
            self.session_loaded.emit(session_id)
            return

        # 3. Lecture des messages
        try:
            session = store.get_or_create(session_id)
        except Exception as e:  # pragma: no cover — défense
            logger.error("ConsolePage.load_session: échec get_or_create: %s", e)
            self.messages.add_message(
                text=f"⚠️ Erreur chargement session: {e}",
                role="assistant",
            )
            self.session_loaded.emit(session_id)
            return

        # 4. Re-rendu des messages (ordre chronologique)
        rendered = 0
        for msg in session.messages:
            try:
                self.messages.add_message(
                    text=msg.content or "",
                    role=msg.role if msg.role in ("user", "assistant") else "assistant",
                )
                rendered += 1
            except Exception as e:  # pragma: no cover — défense
                logger.error(
                    "ConsolePage.load_session: skip message (id=%d): %s",
                    rendered,
                    e,
                )

        logger.info(
            "ConsolePage.load_session: session_id=%s titre=%r → %d/%d messages rendus",
            session_id[:8] if session_id else "",
            title,
            rendered,
            len(session.messages),
        )
        self.messages._scroll_to_bottom()
        self.session_loaded.emit(session_id)

    def set_session_store(self, store) -> None:
        """V11.1 JOUR 3 — Injecte le SessionStore utilisé par ``load_session``.

        Le store peut être ``None`` en cas de DB indisponible ; dans ce
        cas ``load_session`` logguera un warning et affichera un chat vide.
        """
        self._session_store = store

    # ── Internes ──

    def _on_new_chat(self) -> None:
        self.clear_chat()
        self.new_chat.emit()

    def _on_query(self, text: str) -> None:
        self._last_query = text
        # Ajouter le message utilisateur
        self.messages.add_message(text=text, role="user")
        # Afficher l'indicateur de frappe
        self.messages.show_typing()
        # Émettre le signal V7 (query + strict_mode)
        self.query_submitted.emit(text, self.input_area.is_strict())
