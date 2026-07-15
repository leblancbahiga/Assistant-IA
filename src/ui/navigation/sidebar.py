"""
NURU V16 — Sidebar.
Navigation verticale avec icônes + texte, repliable 200px / 52px.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QButtonGroup

from src.ui.tokens import Color, Spacing, WindowSizes

NAV_ITEMS = [
    ("home", "🏠", "Accueil"),
    ("chat", "💬", "Chat"),
    ("documents", "📄", "Documents"),
    ("memory", "🧠", "Mémoire"),
    ("agents", "🤖", "Agents"),
    ("plugins", "🔌", "Plugins"),
    ("tools", "🛠", "Outils"),
    ("models", "🧩", "Modèles"),
    ("dashboard", "📊", "Dashboard"),
    ("settings", "⚙", "Paramètres"),
]


class Sidebar(QWidget):
    """Barre de navigation verticale — repliable 200px / 52px."""

    page_selected = Signal(str)  # émet la clé de la page

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(WindowSizes.SIDEBAR_WIDTH)
        self._collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.LG, Spacing.SM, Spacing.LG)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}

        for key, icon, label in NAV_ITEMS:
            btn = QPushButton(f"  {icon}   {label}")
            btn.setObjectName("SidebarItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda _, k=key: self.page_selected.emit(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()
        self._buttons["chat"].setChecked(True)

    def set_active(self, key: str) -> None:
        """Met en surbrillance l'item correspondant."""
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        width = WindowSizes.SIDEBAR_COLLAPSED if collapsed else WindowSizes.SIDEBAR_WIDTH
        self.setFixedWidth(width)
        for key, icon, label in NAV_ITEMS:
            self._buttons[key].setText(f"  {icon}" if collapsed else f"  {icon}   {label}")
