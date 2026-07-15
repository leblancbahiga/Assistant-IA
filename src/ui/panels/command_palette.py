"""
NURU V16 — CommandPalette.
Overlay de recherche rapide type Spotlight (Ctrl+K).
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeyEvent, QColor
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QWidget, QHBoxLayout, QLabel,
)

from src.ui.tokens import Color, Typography, Spacing, Radius

logger = logging.getLogger(__name__)

# ── Une entrée de commande ───────────────────────────────

class CommandItem:
    """Entrée dans la palette : action avec callback ou page key."""

    def __init__(
        self,
        label: str,
        icon: str = "",
        category: str = "Actions",
        shortcut_hint: str = "",
        callback=None,
        page_key: str = "",
    ):
        self.label = label
        self.icon = icon
        self.category = category
        self.shortcut_hint = shortcut_hint
        self.callback = callback
        self.page_key = page_key

    def score(self, query: str) -> float:
        """Score de correspondance floue avec la requête."""
        if not query:
            return 0.0
        q = query.lower()
        label_lower = self.label.lower()
        # correspondance exacte → max
        if q == label_lower:
            return 100.0
        # commence par → haut score
        if label_lower.startswith(q):
            return 80.0
        # contient → score moyen
        if q in label_lower:
            return 50.0
        # ratio de séquence → bas score
        return SequenceMatcher(None, q, label_lower).ratio() * 30.0


# ── Palette ──────────────────────────────────────────────

class CommandPalette(QFrame):
    """Overlay de commandes type Spotlight.

    Usage :
        palette = CommandPalette(main_window)
        palette.show_centered()
        # ou palette.set_window(main_window)
    """

    # Émis quand une commande est exécutée
    command_executed = Signal(str)  # label de la commande
    closed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._commands: list[CommandItem] = []
        self._main_window = None  # référence pour les callbacks pages

        self.setObjectName("CommandPalette")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Popup
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFixedSize(520, 420)

        self.setStyleSheet(
            f"#CommandPalette {{"
            f"  background-color: {Color.BG_OVERLAY};"
            f"  border: 1px solid {Color.BORDER_STRONG};"
            f"  border-radius: {Radius.WIDGET}px;"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # Champ de recherche
        self._search = QLineEdit()
        self._search.setObjectName("CommandPaletteInput")
        self._search.setPlaceholderText("Chercher une commande ou page…")
        self._search.setStyleSheet(
            f"#CommandPaletteInput {{"
            f"  background-color: {Color.BG_SURFACE2};"
            f"  color: {Color.TEXT_PRIMARY};"
            f"  font-size: {Typography.SIZE_BODY}pt;"
            f"  font-family: {Typography.FAMILY_BODY};"
            f"  border: 1px solid {Color.BORDER_MEDIUM};"
            f"  border-radius: {Radius.SM}px;"
            f"  padding: {Spacing.SM}px {Spacing.MD}px;"
            f"  selection-background-color: {Color.CYAN_GLOW};"
            f"}}"
            f"#CommandPaletteInput:focus {{"
            f"  border-color: {Color.CYAN};"
            f"}}"
        )
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        # Résultats
        self._results = QListWidget()
        self._results.setObjectName("CommandPaletteResults")
        self._results.setStyleSheet(
            f"#CommandPaletteResults {{"
            f"  background-color: transparent;"
            f"  border: none;"
            f"  font-size: {Typography.SIZE_BODY}pt;"
            f"  color: {Color.TEXT_PRIMARY};"
            f"}}"
            f"#CommandPaletteResults::item {{"
            f"  padding: {Spacing.SM}px {Spacing.MD}px;"
            f"  border-radius: {Radius.XS}px;"
            f"}}"
            f"#CommandPaletteResults::item:selected {{"
            f"  background-color: {Color.CYAN_GLOW};"
            f"  color: {Color.CYAN};"
            f"}}"
            f"#CommandPaletteResults::item:hover {{"
            f"  background-color: {Color.CYAN_GLOW};"
            f"}}"
        )
        self._results.itemClicked.connect(self._on_item_click)
        layout.addWidget(self._results, stretch=1)

        # Footer hints
        footer = QLabel("↑↓ naviguer  ↵ ouvrir  ⎋ fermer")
        footer.setStyleSheet(
            f"color: {Color.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}pt; "
            f"font-family: {Typography.FAMILY_BODY}; padding: 2px 4px;"
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

        # ── Commandes par défaut ──
        self._build_default_commands()

    def _build_default_commands(self) -> None:
        """Construit la liste intégrée de commandes."""
        from src.ui.navigation.sidebar import NAV_ITEMS
        self._commands = []

        # Navigation — pages
        icon_map = {k: i for k, i, _ in NAV_ITEMS}
        label_map = {k: l for k, _, l in NAV_ITEMS}
        for key, icon, label in NAV_ITEMS:
            self._commands.append(CommandItem(
                label=label,
                icon=icon,
                category="Navigation",
                shortcut_hint="",
                page_key=key,
            ))

        # Actions système
        sys_actions = [
            ("Nouvelle conversation", "✨", "Ctrl+N"),
            ("Basculer sidebar", "📌", "Ctrl+B"),
            ("Basculer inspecteur", "📋", "Ctrl+\\"),
            ("Activer focus mode", "🎯", "Ctrl+Shift+F"),
            ("Quitter focus mode", "↩", "Escape"),
        ]
        for label, icon, hint in sys_actions:
            self._commands.append(CommandItem(
                label=label,
                icon=icon,
                category="Actions",
                shortcut_hint=hint,
            ))

        # Thèmes / sauts
        self._commands.append(CommandItem(
            label="Aller aux paramètres",
            icon="⚙",
            category="Actions",
            page_key="settings",
        ))
        self._commands.append(CommandItem(
            label="Ouvrir le dashboard",
            icon="📊",
            category="Actions",
            page_key="dashboard",
        ))

    # ── Affichage ──

    def show_centered(self) -> None:
        """Affiche centré sur la fenêtre parente."""
        if not self.parent():
            return
        parent_rect = self.parent().rect()
        x = (parent_rect.width() - self.width()) // 2
        y = (parent_rect.height() - self.height()) // 3  # 1/3 depuis le haut
        self.move(self.parent().mapToGlobal(parent_rect.topLeft()) + x, y)
        self.show()
        self.raise_()
        self._search.setFocus()
        self._search.selectAll()
        self._filter()

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Navigation clavier : ↑↓↵⎋."""
        if event.key() == Qt.Key.Key_Down:
            i = self._results.currentRow()
            self._results.setCurrentRow(min(i + 1, self._results.count() - 1))
            event.accept()
        elif event.key() == Qt.Key.Key_Up:
            i = self._results.currentRow()
            self._results.setCurrentRow(max(i - 1, 0))
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._results.currentItem()
            if item:
                self._execute_item(item)
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ── Filtrage ──

    def _filter(self) -> None:
        """Filtre les commandes selon la requête."""
        query = self._search.text().strip()

        # Marquer les items filtrés
        scored = []
        for cmd in self._commands:
            s = cmd.score(query) if query else (1.0 if not cmd.category else 0.5)
            if s > 0:
                scored.append((cmd, s))

        scored.sort(key=lambda x: -x[1])

        # Regrouper par catégorie
        self._results.clear()
        current_category = None
        for cmd, _ in scored[:12]:  # max 12 résultats
            if cmd.category != current_category:
                current_category = cmd.category
                # En-tête de catégorie
                header = QListWidgetItem(f"── {current_category} ──")
                header.setFlags(header.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                header.setForeground(QColor(Color.TEXT_MUTED))
                header.setBackground(QColor(Color.BG_OVERLAY))
                self._results.addItem(header)

            # Item
            label = f"{cmd.icon}  {cmd.label}"
            if cmd.shortcut_hint:
                label += f"    {cmd.shortcut_hint}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, cmd)
            self._results.addItem(item)

        if self._results.count() > 0:
            self._results.setCurrentRow(0)

    def _on_item_click(self, item: QListWidgetItem) -> None:
        self._execute_item(item)

    def _execute_item(self, item: QListWidgetItem) -> None:
        """Exécute la commande sélectionnée."""
        cmd: CommandItem | None = item.data(Qt.ItemDataRole.UserRole)
        if cmd is None:
            return

        self.command_executed.emit(cmd.label)
        self.close()

        if cmd.page_key and self._main_window:
            from src.ui.navigation.nav_controller import NavigationController
            nav = getattr(self._main_window, 'nav', None)
            if nav and hasattr(nav, 'navigate_to'):
                nav.navigate_to(cmd.page_key)
                logger.debug(f"Palette → navigation vers {cmd.page_key}")
                return

        # Callback direct
        if cmd.callback:
            cmd.callback()
            return

        # Actions système connues par label
        if self._main_window:
            mw = self._main_window
            label = cmd.label
            if "Nouvelle conversation" in label:
                mw._new_conversation()
            elif "Basculer sidebar" in label:
                mw.toggle_sidebar()
            elif "Basculer inspecteur" in label:
                mw.toggle_right_panel()
            elif "Activer focus mode" in label:
                mw.enter_focus_mode()
            elif "Quitter focus mode" in label:
                mw.exit_focus_mode()

    # ── API setup ──

    def set_main_window(self, mw) -> None:
        """Référence à MainWindow pour la navigation."""
        self._main_window = mw

    def add_command(self, cmd: CommandItem) -> None:
        """Ajoute une commande personnalisée."""
        self._commands.append(cmd)
