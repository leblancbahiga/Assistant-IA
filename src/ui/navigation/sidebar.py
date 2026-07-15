"""
NURU V16 — Sidebar.
Navigation verticale avec icônes + texte, repliable 200px / 52px.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QVariantAnimation, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QButtonGroup

from src.ui.tokens import Color, Spacing, WindowSizes
from src.ui.assets.icons import svg_icon

NAV_ITEMS = [
    ("home", "Accueil"),
    ("chat", "Chat"),
    ("documents", "Documents"),
    ("memory", "Mémoire"),
    ("agents", "Agents"),
    ("plugins", "Plugins"),
    ("tools", "Outils"),
    ("models", "Modèles"),
    ("dashboard", "Dashboard"),
    ("settings", "Paramètres"),
]


class Sidebar(QWidget):
    """Barre de navigation verticale — repliable 200px / 52px, icônes SVG."""

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
        self._buttons: dict[str, QToolButton] = {}

        for key, label in NAV_ITEMS:
            btn = QToolButton()
            btn.setObjectName("SidebarItem")
            btn.setIcon(svg_icon(key))
            btn.setIconSize(QSize(20, 20))
            btn.setText(f"  {label}")
            btn.setToolTip(label)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
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
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        target = WindowSizes.SIDEBAR_COLLAPSED if collapsed else WindowSizes.SIDEBAR_WIDTH
        start_w = self.width()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setStartValue(float(start_w))
        self._anim.setEndValue(float(target))
        self._anim.valueChanged.connect(lambda v: self.setFixedWidth(int(v)))
        self._anim.start()
        for key, label in NAV_ITEMS:
            btn = self._buttons[key]
            if collapsed:
                btn.setText("")
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            else:
                btn.setText(f"  {label}")
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
