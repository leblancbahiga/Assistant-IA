"""NURU V15 — FloatingSearchWidget (⌘⇧Space / Ctrl+Shift+Space).

Widget flottant type Raycast/Spotlight :
  - Fenêtre autonome, sans bordure, toujours au-dessus
  - Apparaît au centre de l'écran avec un fade-in
  - Champ de recherche + commandes filtrées
  - Fonctionne même quand NuruWindow est minimisée

Usage :
    search = FloatingSearchWidget()
    search.register_commands(commands)
    search.show_search()
    search.toggle()

DM-1 : fond BG_SURFACE1, accent cyan, coins arrondis, ombre.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QKeySequence, QScreen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QApplication,
    QGraphicsOpacityEffect, QFrame,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, AnimDuration
from src.ui.components.command_palette import CommandItem, CommandListItem

logger = logging.getLogger(__name__)


class FloatingSearchWidget(QWidget):
    """Widget flottant type Spotlight/Raycast — ⌘⇧Space.

    Fenêtre autonome, frameless, top-most. Apparaît centrée
    avec un fade-in. Sert de lanceur rapide pour les actions NURU.
    """

    closed = Signal()

    SEARCH_STYLE = f"""
        #FloatingSearchBg {{
            background: {Color.BG_SURFACE1};
            border: 1px solid {Color.BORDER};
            border-radius: {Radius.WIDGET}px;
        }}
        #FloatingSearchInput {{
            background: {Color.BG_SURFACE2};
            color: {Color.TEXT_PRIMARY};
            border: 1px solid {Color.BORDER};
            border-radius: 8px;
            padding: 12px 16px;
            font-size: 15px;
            font-family: {Typography.FAMILY_BODY};
            selection-background-color: rgba(0, 212, 255, 0.25);
        }}
        #FloatingSearchInput:focus {{
            border-color: {Color.CYAN};
        }}
        #FloatingList {{
            background: transparent;
            border: none;
            outline: none;
        }}
        #FloatingList::item {{
            border: none;
            border-radius: 6px;
            padding: 0px;
        }}
        #FloatingList::item:selected {{
            background: {Color.CYAN_GLOW};
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._commands: list[CommandItem] = []
        self._filtered: list[CommandItem] = []
        self._visible = False

        # Fenêtre autonome
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setVisible(False)

        # Opacity effect pour fade-in
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(AnimDuration.OVERLAY_SHOW)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Fond (permet les coins arrondis via QSS)
        self._bg = QFrame(self)
        self._bg.setObjectName("FloatingSearchBg")
        self._bg.setGeometry(QRect(0, 0, 520, 420))
        self._bg.setStyleSheet(self.SEARCH_STYLE)

        # Layout de la fenêtre
        layout = QVBoxLayout(self._bg)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)

        # Titre
        title = QLabel("Recherche rapide")
        title.setStyleSheet(
            "background: transparent; color: #6B7280;"
            " font-size: 10px; font-weight: 600; letter-spacing: 0.08em;"
            " padding: 0 0 4px 0;"
        )
        layout.addWidget(title)

        # Champ de recherche
        self._search = QLineEdit()
        self._search.setObjectName("FloatingSearchInput")
        self._search.setPlaceholderText("Rechercher une action…")
        self._search.textChanged.connect(self._filter_commands)
        layout.addWidget(self._search)

        # Liste des commandes
        self._list = QListWidget()
        self._list.setObjectName("FloatingList")
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setCursor(Qt.PointingHandCursor)
        self._list.setSpacing(2)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list, stretch=1)

        # Footer
        footer = QLabel("↑↓  Naviguer    ↩  Exécuter    Esc  Fermer")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet(
            "background: transparent; color: #4A5568;"
            " font-size: 10px; padding: 6px 0 0 0;"
        )
        layout.addWidget(footer)

        self.setFixedSize(520, 420)

    # ── API publique ──

    def register_commands(self, commands: list[CommandItem]) -> None:
        self._commands = commands
        self._filtered = commands[:]
        self._rebuild_list()

    def show_search(self) -> None:
        """Affiche le widget flottant centré sur l'écran actif."""
        if self._visible:
            return
        self._visible = True

        # Centrer sur l'écran actif
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() // 3  # 1/3 from top
            self.move(x, y)

        # Fade-in
        self._opacity_effect.setOpacity(0.0)
        self.setVisible(True)
        self.raise_()
        self.activateWindow()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        self._search.clear()
        self._search.setFocus()
        self._filter_commands("")
        logger.debug("FloatingSearch affiché")

    def hide_search(self) -> None:
        """Cache le widget flottant."""
        if not self._visible:
            return
        self._visible = False
        self.setVisible(False)
        self.closed.emit()
        logger.debug("FloatingSearch caché")

    def toggle(self) -> None:
        if self._visible:
            self.hide_search()
        else:
            self.show_search()

    @property
    def is_visible(self) -> bool:
        return self._visible

    # ── Événements ──

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.hide_search()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._execute_current()
        elif key == Qt.Key_Down:
            self._move_selection(1)
        elif key == Qt.Key_Up:
            self._move_selection(-1)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        """Cache automatiquement si on perd le focus (clic ailleurs)."""
        super().focusOutEvent(event)
        # Petit délai pour éviter la fermeture pendant le clic sur la liste
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._check_focus)

    def _check_focus(self):
        """Cache si aucun enfant n'a le focus."""
        if self._visible and not self.isActiveWindow():
            self.hide_search()

    # ── Interne ──

    def _filter_commands(self, text: str) -> None:
        q = text.lower().strip()
        if not q:
            self._filtered = self._commands[:]
        else:
            self._filtered = [
                cmd for cmd in self._commands
                if q in cmd.label.lower() or q in cmd.category.lower()
            ]
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        self._list.clear()
        for cmd in self._filtered:
            item_widget = CommandListItem(cmd)
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, cmd.id)
            self._list.addItem(list_item)
            self._list.setItemWidget(list_item, item_widget)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._execute_item(item)

    def _execute_current(self) -> None:
        item = self._list.currentItem()
        if item:
            self._execute_item(item)

    def _execute_item(self, item: QListWidgetItem) -> None:
        cmd_id = item.data(Qt.UserRole)
        for cmd in self._commands:
            if cmd.id == cmd_id and cmd.action:
                logger.info(f"⚡ FloatingSearch → {cmd.label}")
                self.hide_search()
                cmd.action()
                return

    def _move_selection(self, direction: int) -> None:
        row = self._list.currentRow()
        new_row = row + direction
        if 0 <= new_row < self._list.count():
            self._list.setCurrentRow(new_row)
