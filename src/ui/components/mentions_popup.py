"""MentionsPopup — Popup de suggestions @mentions pour SmartTextEdit.

Propose une auto-complétion filtrée en temps réel quand l'utilisateur
tape ``@`` dans le SmartTextEdit. Supporte la navigation clavier
(↑/↓/Enter/Esc) et le filtrage progressif.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from PySide6.QtCore import QRect


MENTION_ITEMS: list[dict] = [
    # ── Documents ──
    {"label": "cv_lebanc.pdf", "type": "Document", "icon": "📄"},
    {"label": "rapport_v3.docx", "type": "Document", "icon": "📄"},
    {"label": "notes_reunion.md", "type": "Document", "icon": "📄"},
    # ── Mémoire ──
    {"label": "projet_nuru_arch", "type": "Mémoire", "icon": "🧠"},
    {"label": "config_prefs", "type": "Mémoire", "icon": "🧠"},
    {"label": "derniers_chats", "type": "Mémoire", "icon": "🧠"},
    # ── Web ──
    {"label": "recherche_recente", "type": "Web", "icon": "🌐"},
    {"label": "article_rAG", "type": "Web", "icon": "🌐"},
    {"label": "docs_api", "type": "Web", "icon": "🌐"},
]


class MentionsPopup(QFrame):
    """Popup overlay de suggestions @mentions.

    S'affiche au-dessus du SmartTextEdit parent quand l'utilisateur tape
    ``@``, se filtre en temps réel, et supporte la navigation clavier.

    Signaux
    -------
    selected(str) : émis quand l'utilisateur sélectionne un item (label)
    dismissed()   : émis quand le popup est fermé sans sélection
    """

    selected = Signal(str)
    dismissed = Signal()

    STYLE = """
    QFrame#MentionsPopup {
        background: #1A1A2E;
        border: 1px solid #2A2A4E;
        border-radius: 8px;
    }
    QListWidget {
        background: transparent;
        border: none;
        border-radius: 8px;
        outline: none;
    }
    QListWidget::item {
        padding: 8px 12px;
        min-height: 28px;
        font-size: 12px;
        color: #C0C0D0;
        border: none;
    }
    QListWidget::item:selected,
    QListWidget::item:hover {
        background: #2A2A4E;
    }
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MentionsPopup")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(self.STYLE)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # QListWidget pour les items
        self._list = QListWidget()
        self._list.setObjectName("MentionsList")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list.setCursor(Qt.PointingHandCursor)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        # Données brutes (pour filtrage)
        self._all_items: list[dict] = list(MENTION_ITEMS)

        # Dimensions
        self.setFixedWidth(280)
        self.setMaximumHeight(200)
        self.hide()

    # ── API publique ──

    def set_items(self, items: list[dict]) -> None:
        """Remplace la liste complète des suggestions disponibles.

        Chaque dict doit contenir : ``{"label": ..., "type": ..., "icon": ...}``.
        """
        self._all_items = list(items)
        self._rebuild(self._all_items)

    def filter(self, query: str) -> None:
        """Filtre les suggestions en fonction du texte partiel après ``@``.

        La recherche est insensible à la casse et s'applique sur le label
        ainsi que sur le type.
        """
        q = query.strip().lower()
        if not q:
            self._rebuild(self._all_items)
            return

        matched = [
            item
            for item in self._all_items
            if q in item["label"].lower() or q in item["type"].lower()
        ]
        self._rebuild(matched)

    def show_at(self, rect: QRect) -> None:
        """Positionne et affiche le popup au-dessus du rectangle donné.

        Le popup est placé de sorte que son bord inférieur soit aligné
        avec le haut du rectangle, avec un petit décalage.
        """
        parent_widget = self.parent()
        if not parent_widget:
            return

        # Convertir les coordonnées du rect (relatives au parent)
        # en coordonnées globales
        global_bottom_left = parent_widget.mapToGlobal(rect.bottomLeft())

        # Placer le popup au-dessus du curseur
        popup_x = global_bottom_left.x()
        popup_y = global_bottom_left.y() - self.height() - 4

        # Éviter de sortir de l'écran
        screen = self.screen()
        if screen:
            screen_rect = screen.availableGeometry()
            if popup_y < 0:
                popup_y = global_bottom_left.y() + 4  # en dessous
            if popup_x + self.width() > screen_rect.right():
                popup_x = screen_rect.right() - self.width() - 8
            if popup_x < 0:
                popup_x = 8

        self.move(popup_x, popup_y)
        self.show()
        self.raise_()

    def close_popup(self) -> None:
        """Ferme le popup et émet le signal ``dismissed``."""
        if self.isVisible():
            self.hide()
            self.dismissed.emit()

    def select_current(self) -> None:
        """Sélectionne l'item actuellement en surbrillance dans la liste."""
        item = self._list.currentItem()
        if item:
            self._on_item_clicked(item)

    def move_up(self) -> None:
        """Déplace la sélection vers le haut."""
        row = self._list.currentRow()
        if row > 0:
            self._list.setCurrentRow(row - 1)
        else:
            # Wrap to bottom
            self._list.setCurrentRow(self._list.count() - 1)

    def move_down(self) -> None:
        """Déplace la sélection vers le bas."""
        row = self._list.currentRow()
        if row < self._list.count() - 1:
            self._list.setCurrentRow(row + 1)
        else:
            # Wrap to top
            self._list.setCurrentRow(0)

    @property
    def is_open(self) -> bool:
        """``True`` si le popup est actuellement visible."""
        return self.isVisible()

    @property
    def has_items(self) -> bool:
        """``True`` si la liste contient au moins un item."""
        return self._list.count() > 0

    # ── Internes ──

    def _rebuild(self, items: list[dict]) -> None:
        """Reconstruit la QListWidget à partir d'une liste d'items filtrée."""
        self._list.clear()

        for item_data in items:
            label = item_data.get("label", "?")
            icon = item_data.get("icon", "")
            item_type = item_data.get("type", "")

            display_text = f"{icon} {label}" if icon else label
            if item_type:
                display_text += f"  — {item_type}"

            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.UserRole, label)
            self._list.addItem(list_item)

        # Cacher le popup si plus rien à afficher
        if self._list.count() == 0:
            self.hide()
        else:
            # Sélectionner le premier item par défaut
            self._list.setCurrentRow(0)
            if not self.isVisible():
                self.show()
                self.raise_()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Gère le clic sur un item : émet ``selected(label)`` puis ferme."""
        label = item.data(Qt.UserRole) or item.text()
        self.hide()
        self.selected.emit(label)
