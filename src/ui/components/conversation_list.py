# V11.1 (P0-J) — ConversationList : composant atomique de la sidebar
# Affiche les 10 dernières sessions stockées via SessionStore (V10.3f).
# Source : recommandation R2 §6.1 #1 + R4 §10.6 (réduction clics).
"""ConversationList — Liste cliquable des dernières sessions de chat.

Lecture seule basée sur ``SessionStore.list_sessions()``. Émet un signal
``session_selected(session_id)`` quand l'utilisateur clique sur une entrée.
Fournit aussi un bouton "Nouvelle conversation" qui émet
``new_conversation_requested()``.

Le composant est conçu comme un ``QWidget`` autonome :
- Aucune dépendance sur ``CyberDashboard`` (testable en isolation).
- Constructor ``parent`` standard Qt.
- Si ``session_store`` est None, affiche un état vide non-bloquant.

Exemple
-------
    from src.session.store import SessionStore
    from src.ui.components.conversation_list import ConversationList

    store = SessionStore()
    widget = ConversationList(session_store=store)
    widget.new_conversation_requested.connect(my_handler)
    widget.session_selected.connect(my_load_handler)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src.session.store import SessionStore

logger = logging.getLogger(__name__)


def _format_relative_date(timestamp: float) -> str:
    """Formate un timestamp en date relative courte FR (ex: 'il y a 2j').

    Stratégie volontairement simple : bucketed par jour, sans locale compliquée.
    Évite l'import de ``babel`` ou ``humanize`` (deps externes inutiles).
    """
    if not timestamp:
        return ""
    try:
        delta = datetime.now().timestamp() - float(timestamp)
    except (TypeError, ValueError):
        return ""
    if delta < 0:
        return "à l'instant"
    if delta < 60:  # <1min
        return "à l'instant"
    if delta < 3600:  # <1h
        return f"il y a {int(delta // 60)}min"
    if delta < 86400:  # <24h
        return f"il y a {int(delta // 3600)}h"
    if delta < 604800:  # <7j
        return f"il y a {int(delta // 86400)}j"
    # >7j : date absolue JJ/MM
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%d/%m")
    except (TypeError, ValueError, OSError):
        return ""


class ConversationList(QFrame):
    """Widget affichant les N dernières conversations issues de SessionStore.

    Signals
    --------
    new_conversation_requested()
        Émis lors du clic sur le bouton + (nouvelle discussion).
    session_selected(str)
        Émis lors du clic sur une session. Le payload est ``session_id``.
    """

    new_conversation_requested = Signal()
    session_selected = Signal(str)

    MAX_DISPLAYED = 10  # cohérent avec RecentDocuments

    def __init__(
        self,
        session_store: "SessionStore | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ConversationList")

        self._store = session_store
        self._build_ui()
        self.refresh()

    # ── UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Header : libellé + bouton "+"
        header = QHBoxLayout()
        header.setSpacing(4)

        title = QLabel("Discussions récentes")
        title.setObjectName("ConvListTitle")
        header.addWidget(title)
        header.addStretch()

        self._new_btn = QPushButton("＋")
        self._new_btn.setObjectName("NewConvBtn")
        self._new_btn.setToolTip("Nouvelle conversation")
        self._new_btn.setCursor(Qt.PointingHandCursor)
        self._new_btn.setFixedSize(22, 22)
        self._new_btn.clicked.connect(self.new_conversation_requested.emit)
        header.addWidget(self._new_btn)
        layout.addLayout(header)

        # Liste
        self._list = QListWidget()
        self._list.setObjectName("ConvListItems")
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setSpacing(2)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list, stretch=1)

        # État vide (caché par défaut)
        self._empty_label = QLabel("Aucune discussion")
        self._empty_label.setObjectName("ConvListEmpty")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

    # ── API publique ────────────────────────────────────────────────────

    def set_session_store(self, store: "SessionStore") -> None:
        """Réinjecte un store dynamiquement (utile après init lazy)."""
        self._store = store
        self.refresh()

    def refresh(self) -> None:
        """Recharge depuis le store et repeuple la liste."""
        self._list.clear()

        if self._store is None:
            self._list.hide()
            self._empty_label.setText("Store de sessions indisponible")
            self._empty_label.show()
            return

        try:
            sessions = self._store.list_sessions(limit=self.MAX_DISPLAYED)
        except Exception as e:  # pragma: no cover - safety
            logger.warning("ConversationList.refresh: échec list_sessions: %s", e)
            sessions = []

        if not sessions:
            self._list.hide()
            self._empty_label.setText("Aucune discussion")
            self._empty_label.show()
            return

        self._empty_label.hide()
        self._list.show()

        for session in sessions:
            self._add_session_item(session)

    def select_session(self, session_id: str) -> None:
        """Sélectionne programmatiquement une session dans la liste."""
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.data(Qt.UserRole) == session_id:
                self._list.setCurrentItem(it)
                return

    # ── Privé ───────────────────────────────────────────────────────────

    def _add_session_item(self, session: dict) -> None:
        title = session.get("title") or session.get("id", "")[:8] or "Sans titre"
        msg_count = session.get("message_count", 0)
        rel_date = _format_relative_date(session.get("updated_at", 0))
        session_id = session.get("id", "")

        # Libellé affiché : "Titre (N msgs · date)"
        meta = []
        if msg_count:
            meta.append(f"{msg_count} msg{'s' if msg_count > 1 else ''}")
        if rel_date:
            meta.append(rel_date)
        if meta:
            label = f"{title}  ·  {' · '.join(meta)}"
        else:
            label = title

        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, session_id)
        item.setToolTip(title)
        self._list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        session_id = item.data(Qt.UserRole)
        if session_id:
            logger.debug("ConversationList: session sélectionnée: %s", session_id[:8])
            self.session_selected.emit(str(session_id))
