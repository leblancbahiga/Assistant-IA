"""NURU V15 — CommandPalette (Ctrl+K / ⌘K).

Palette de commandes modale type VS Code / Raycast :
  - Overlay semi-transparent sur toute la fenêtre
  - Champ de recherche en haut, liste filtrée en bas
  - Navigation clavier (↑↓↩Esc)
  - Chaque commande a : icône + label + raccourci + action

Usage :
    palette = CommandPalette(parent_window)
    palette.register_commands([...])
    palette.show()
    palette.toggle()  # show/hide

DM-1 : fond sombre, accent cyan, glassmorphism subtil.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QKeySequence, QFont
from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QApplication,
    QSizePolicy, QGraphicsOpacityEffect,
)

from src.ui.tokens import Color, Typography, Radius, Spacing, AnimDuration

logger = logging.getLogger(__name__)


# ── Modèle ─────────────────────────────────────────────────────────────────


@dataclass
class CommandItem:
    """Une action disponible dans la palette."""
    id: str
    label: str
    icon: str = ""
    shortcut: str = ""
    category: str = "Général"
    action: Callable[[], None] | None = None


# ── Widget item personnalisé ───────────────────────────────────────────────


class CommandListItem(QWidget):
    """Item de liste pour la palette — icône + label + raccourci."""

    def __init__(self, cmd: CommandItem, parent=None):
        super().__init__(parent)
        self._cmd = cmd
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Icône
        icon_lbl = QLabel(cmd.icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setStyleSheet("background: transparent; font-size: 14px;")
        layout.addWidget(icon_lbl)

        # Label
        label = QLabel(cmd.label)
        label.setStyleSheet(
            "background: transparent; color: #E2E8F0;"
            " font-size: 13px; font-weight: 500;"
        )
        layout.addWidget(label, stretch=1)

        # Raccourci
        if cmd.shortcut:
            sc_lbl = QLabel(cmd.shortcut)
            sc_lbl.setStyleSheet(
                "background: rgba(255,255,255,0.06); color: #6B7280;"
                " font-size: 10px; padding: 2px 6px; border-radius: 3px;"
                f" font-family: '{Typography.FAMILY_CODE}';"
            )
            layout.addWidget(sc_lbl)

        self.setStyleSheet("background: transparent;")


# ── Palette modale ─────────────────────────────────────────────────────────


class CommandPalette(QFrame):
    """Palette de commandes modale — Ctrl+K / ⌘K.

    Overlay semi-transparent avec champ de recherche + liste filtrée.
    S'affiche par-dessus le parent (NuruCentralWidget).
    """

    # Émis quand la palette se ferme (sans action)
    closed = Signal()

    STYLE = """
        #CommandPaletteBackdrop {{
            background: rgba(10, 14, 23, 0.70);
        }}
        #CommandPaletteContainer {{
            background: {bg_surface};
            border: 1px solid {border};
            border-radius: {radius}px;
        }}
        #CommandSearch {{
            background: {bg_surface2};
            color: {text_primary};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 14px;
            font-family: {font_body};
            selection-background-color: rgba(0, 212, 255, 0.25);
        }}
        #CommandSearch:focus {{
            border-color: {cyan};
        }}
        #CommandList {{
            background: transparent;
            border: none;
            outline: none;
        }}
        #CommandList::item {{
            border: none;
            border-radius: 6px;
            padding: 0px;
        }}
        #CommandList::item:selected {{
            background: {cyan_glow};
        }}
    """.format(
        bg_surface=Color.BG_SURFACE1,
        bg_surface2=Color.BG_SURFACE2,
        text_primary=Color.TEXT_PRIMARY,
        border=Color.BORDER,
        cyan=Color.CYAN,
        cyan_glow=Color.CYAN_GLOW,
        radius=Radius.WIDGET,
        font_body=Typography.FAMILY_BODY,
    )

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._commands: list[CommandItem] = []
        self._filtered: list[CommandItem] = []
        self._visible = False

        self.setObjectName("CommandPaletteBackdrop")
        self.setStyleSheet(self.STYLE)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setVisible(False)
        # Opacity effect pour fade-in
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity")
        self._fade_anim.setDuration(AnimDuration.OVERLAY_SHOW)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Layout principal (backdrop)
        backdrop_layout = QVBoxLayout(self)
        backdrop_layout.setContentsMargins(0, 0, 0, 0)
        backdrop_layout.setAlignment(Qt.AlignCenter)

        # Conteneur centré
        self._container = QFrame()
        self._container.setObjectName("CommandPaletteContainer")
        self._container.setFixedWidth(500)
        self._container.setMaximumHeight(400)
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(16, 16, 16, 12)
        container_layout.setSpacing(8)

        # Titre
        title = QLabel("Commandes")
        title.setStyleSheet(
            "background: transparent; color: #6B7280;"
            " font-size: 10px; font-weight: 600; letter-spacing: 0.08em;"
            " text-transform: uppercase; padding: 0 0 4px 0;"
        )
        container_layout.addWidget(title)

        # Champ de recherche
        self._search = QLineEdit()
        self._search.setObjectName("CommandSearch")
        self._search.setPlaceholderText("Rechercher une action…")
        self._search.textChanged.connect(self._filter_commands)
        container_layout.addWidget(self._search)

        # Liste des commandes
        self._list = QListWidget()
        self._list.setObjectName("CommandList")
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setCursor(Qt.PointingHandCursor)
        self._list.setSpacing(2)
        self._list.itemClicked.connect(self._on_item_clicked)
        container_layout.addWidget(self._list, stretch=1)

        # Footer — hint raccourci
        footer = QLabel("↑↓  Naviguer    ↩  Exécuter    Esc  Fermer")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet(
            "background: transparent; color: #4A5568;"
            " font-size: 10px; padding: 6px 0 0 0;"
        )
        container_layout.addWidget(footer)

        backdrop_layout.addWidget(self._container)

        # Forcer la largeur du conteneur
        self._container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

    # ── API publique ──

    def register_commands(self, commands: list[CommandItem]) -> None:
        """Enregistre la liste complète des commandes disponibles."""
        self._commands = commands
        self._filtered = commands[:]
        self._rebuild_list()

    def add_command(self, cmd: CommandItem) -> None:
        """Ajoute une commande individuelle."""
        self._commands.append(cmd)
        self._filter_commands(self._search.text())

    def show_palette(self) -> None:
        """Affiche la palette et donne le focus à la recherche."""
        if not self.parent():
            return
        self._visible = True
        self.setGeometry(self.parent().rect())
        # Démarrer la fade-in depuis zéro
        self._opacity.setOpacity(0.0)
        self.setVisible(True)
        self.raise_()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        self._search.clear()
        self._search.setFocus()
        self._filter_commands("")
        logger.debug("Palette affichée")

    def hide_palette(self) -> None:
        """Cache la palette."""
        self._visible = False
        self.setVisible(False)
        self.closed.emit()
        logger.debug("Palette cachée")

    def toggle(self) -> None:
        """Bascule affichage / masquage."""
        if self._visible:
            self.hide_palette()
        else:
            self.show_palette()

    @property
    def is_visible(self) -> bool:
        return self._visible

    # ── Événements ──

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.hide_palette()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._execute_current()
        elif key == Qt.Key_Down:
            self._move_selection(1)
        elif key == Qt.Key_Up:
            self._move_selection(-1)
        elif key == Qt.Key_K and event.modifiers() & Qt.ControlModifier:
            self.hide_palette()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Clic sur le backdrop (hors conteneur) ferme la palette."""
        child = self.childAt(event.pos())
        if child is None or child == self or child == self._container:
            # Vérifier si clic hors conteneur
            container_rect = self._container.geometry()
            if not container_rect.contains(event.pos()):
                self.hide_palette()
                return
        super().mousePressEvent(event)

    def _filter_commands(self, text: str) -> None:
        """Filtre les commandes par texte de recherche."""
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
        """Reconstruit la QListWidget à partir des commandes filtrées."""
        self._list.clear()
        for cmd in self._filtered:
            item_widget = CommandListItem(cmd)
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, cmd.id)
            self._list.addItem(list_item)
            self._list.setItemWidget(list_item, item_widget)

        # Pré-sélectionner le premier item
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Exécute la commande cliquée."""
        self._execute_item(item)

    def _execute_current(self) -> None:
        """Exécute l'item sélectionné."""
        item = self._list.currentItem()
        if item:
            self._execute_item(item)

    def _execute_item(self, item: QListWidgetItem) -> None:
        """Exécute la commande associée à un item."""
        cmd_id = item.data(Qt.UserRole)
        for cmd in self._commands:
            if cmd.id == cmd_id and cmd.action:
                logger.info(f"⚡ Palette → {cmd.label}")
                self.hide_palette()
                cmd.action()
                return

    def _move_selection(self, direction: int) -> None:
        """Déplace la sélection dans la liste (↑↓)."""
        row = self._list.currentRow()
        new_row = row + direction
        if 0 <= new_row < self._list.count():
            self._list.setCurrentRow(new_row)
