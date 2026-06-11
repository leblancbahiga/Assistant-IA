"""
MemoryExplorer — Explore et recherche dans les 6 types de mémoire (Dashboard V9).

Onglets : Épisodique, Sémantique, Utilisateur, Erreurs.
Barre de recherche textuelle + compteurs par type + filtrage catégorie.

Design cyberpunk NURU : bg #0D1117, accent #00A3FF.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

# ── Constantes de thème ────────────────────────────────────────────────────

BG_PANEL = "#161b22"
BG_INPUT = "#0D1117"
ACCENT_BLUE = "#00A3FF"
ACCENT_GREEN = "#39FF14"
ACCENT_RED = "#FF3333"
ACCENT_ORANGE = "#FF8C00"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
BORDER_COLOR = "rgba(255,255,255,0.08)"

PANEL_STYLE = f"""
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
"""

# ── Helpers d'affichage ────────────────────────────────────────────────────

MEMORY_TYPE_LABELS: dict[str, str] = {
    "episodic": "Épisodique",
    "semantic": "Sémantique",
    "user": "Utilisateur",
    "error": "Erreurs",
}

MEMORY_TYPE_ICONS: dict[str, str] = {
    "episodic": "📅",
    "semantic": "📚",
    "user": "👤",
    "error": "⚠️",
}

MEMORY_TYPE_COLORS: dict[str, str] = {
    "episodic": ACCENT_BLUE,
    "semantic": ACCENT_GREEN,
    "user": ACCENT_ORANGE,
    "error": ACCENT_RED,
}


def format_memory_entry(entry: dict[str, Any], memory_type: str = "") -> str:
    """Formate une entrée mémoire en texte lisible.

    Args:
        entry: Dictionnaire représentant une entrée mémoire.
               Champs typiques : id, summary, content, category, timestamp, score, tags.
        memory_type: Type de mémoire (épisodique, sémantique, etc.) — optionnel.

    Returns:
        Chaîne formatée prête à afficher.
    """
    icon = MEMORY_TYPE_ICONS.get(memory_type, "📌")
    prefix = f"{icon} " if memory_type else ""

    summary = entry.get("summary") or entry.get("content", "")
    if isinstance(summary, str) and len(summary) > 120:
        summary = summary[:117] + "..."

    category = entry.get("category", "")
    score = entry.get("score", "")
    tags = entry.get("tags", [])

    parts = [f"{prefix}{summary}"]

    if category:
        parts.append(f"[{category}]")
    if score:
        parts.append(f"(score: {score})")
    if tags and isinstance(tags, list):
        tag_str = " ".join(f"#{t}" for t in tags[:3])
        parts.append(tag_str)

    return "  ".join(parts)


def filter_entries(entries: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Filtre les entrées mémoire par requête textuelle.

    Cherche dans : summary, content, category, tags.

    Args:
        entries: Liste d'entrées mémoire.
        query: Chaîne de recherche (insensible à la casse).

    Returns:
        Sous-liste des entrées correspondant à la requête.
    """
    if not query or not query.strip():
        return entries

    q = query.strip().lower()
    results: list[dict[str, Any]] = []
    for entry in entries:
        searchable = [
            str(entry.get("summary", "")),
            str(entry.get("content", "")),
            str(entry.get("category", "")),
            " ".join(str(t) for t in entry.get("tags", [])),
        ]
        if any(q in s.lower() for s in searchable):
            results.append(entry)
    return results


def count_by_type(data: dict[str, list[Any]]) -> dict[str, int]:
    """Compte le nombre d'entrées par type de mémoire.

    Args:
        data: Dictionnaire {"episodic": [...], "semantic": [...], "user": [...], "error": [...]}.

    Returns:
        Dictionnaire {"episodic": N, "semantic": N, "user": N, "error": N}.
    """
    return {key: len(val) if isinstance(val, list) else 0 for key, val in data.items()}


# ── Style QSS ──────────────────────────────────────────────────────────────

SEARCH_STYLE = f"""
    QLineEdit {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }}
    QLineEdit:focus {{
        border: 1px solid {ACCENT_BLUE};
    }}
"""

TAB_STYLE = f"""
    QTabWidget::pane {{
        background-color: transparent;
        border: none;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {TEXT_SECONDARY};
        border: none;
        padding: 6px 14px;
        font-size: 11px;
        font-weight: bold;
        text-transform: uppercase;
    }}
    QTabBar::tab:selected {{
        color: {ACCENT_BLUE};
        border-bottom: 2px solid {ACCENT_BLUE};
    }}
    QTabBar::tab:hover:!selected {{
        color: {TEXT_PRIMARY};
    }}
"""

ITEM_STYLE = f"""
    color: {TEXT_PRIMARY};
    font-size: 12px;
    padding: 4px 0px;
"""


# ── Widget principal ───────────────────────────────────────────────────────


class MemoryExplorer(QFrame):
    """Explore et recherche dans les 6 types de mémoire.

    Fonctionnalités :
    - Onglets par type de mémoire (Épisodique, Sémantique, Utilisateur, Erreurs)
    - Barre de recherche textuelle
    - Liste des résultats avec scroll
    - Compteurs par type
    - Filtre par catégorie/type d'événement

    Signaux :
        search_requested(query) — émis quand l'utilisateur tape une recherche.

    API publique :
        set_data(data: dict) — data = {"episodic": [...], "semantic": [...], "user": [...], "error": [...]}
        search(query: str) — filtre les résultats
        clear() — vide tout
    """

    search_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MemoryExplorer")
        self.setStyleSheet(f"#MemoryExplorer {{ {PANEL_STYLE} }}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ── Données ──
        self._data: dict[str, list[dict[str, Any]]] = {
            "episodic": [],
            "semantic": [],
            "user": [],
            "error": [],
        }
        self._current_type: str = "episodic"

        # ── Layout principal ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── En-tête : titre + compteurs ──
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("🧠 Mémoires")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold;")
        header.addWidget(title)

        self._counter_labels: dict[str, QLabel] = {}
        for mtype in ("episodic", "semantic", "user", "error"):
            lbl = QLabel("0")
            lbl.setStyleSheet(
                f"color: {MEMORY_TYPE_COLORS[mtype]}; font-size: 10px; "
                f"background: rgba(255,255,255,0.04); padding: 2px 6px; "
                f"border-radius: 4px;"
            )
            self._counter_labels[mtype] = lbl
            header.addWidget(lbl)

        header.addStretch()
        layout.addLayout(header)

        # ── Barre de recherche ──
        search_layout = QHBoxLayout()
        search_layout.setSpacing(6)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("MemorySearchInput")
        self._search_input.setPlaceholderText("🔍 Rechercher dans la mémoire...")
        self._search_input.setStyleSheet(SEARCH_STYLE)
        self._search_input.setFixedHeight(32)
        self._search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search_input)

        self._clear_btn = QPushButton("✕")
        self._clear_btn.setFixedSize(28, 28)
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; "
            f"border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {TEXT_PRIMARY}; }}"
        )
        self._clear_btn.clicked.connect(self._on_clear_search)
        search_layout.addWidget(self._clear_btn)

        layout.addLayout(search_layout)

        # ── Zone d'onglets ──
        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("MemoryTabWidget")
        self._tab_widget.setStyleSheet(TAB_STYLE)
        self._tab_widget.tabBar().setCursor(Qt.PointingHandCursor)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        self._tab_pages: dict[str, QScrollArea] = {}
        self._tab_labels: dict[str, QLabel] = {}

        for mtype in ("episodic", "semantic", "user", "error"):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet(
                f"QScrollArea {{ background: transparent; border: none; }}"
                f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
                f"QScrollBar::handle:vertical {{ background: {ACCENT_BLUE}; "
                f"border-radius: 2px; min-height: 20px; }}"
            )

            content = QLabel()
            content.setObjectName(f"MemoryContent_{mtype}")
            content.setWordWrap(True)
            content.setStyleSheet(
                f"#MemoryContent_{mtype} {{ color: {TEXT_PRIMARY}; font-size: 12px; "
                f"padding: 4px; }}"
            )
            content.setTextFormat(Qt.PlainText)
            content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            content.setTextInteractionFlags(Qt.TextSelectableByMouse)

            scroll.setWidget(content)
            self._tab_pages[mtype] = scroll
            self._tab_labels[mtype] = content

            icon = MEMORY_TYPE_ICONS.get(mtype, "📌")
            label = MEMORY_TYPE_LABELS.get(mtype, mtype.capitalize())
            self._tab_widget.addTab(scroll, f"{icon} {label}")

        layout.addWidget(self._tab_widget)

    # ── API publique ─────────────────────────────────────────────────────

    def set_data(self, data: dict[str, list[dict[str, Any]]]) -> None:
        """Met à jour les données et rafraîchit l'affichage.

        Args:
            data: Dictionnaire avec clés "episodic", "semantic", "user", "error".
        """
        self._data = {
            "episodic": data.get("episodic", []),
            "semantic": data.get("semantic", []),
            "user": data.get("user", []),
            "error": data.get("error", []),
        }
        self._update_counters()
        self._refresh_current_tab()

    def search(self, query: str) -> None:
        """Filtre les résultats par requête textuelle.

        Args:
            query: Texte de recherche.
        """
        self._search_input.blockSignals(True)
        self._search_input.setText(query)
        self._search_input.blockSignals(False)
        self._refresh_current_tab()

    def clear(self) -> None:
        """Vide toutes les données et la recherche."""
        self._data = {
            "episodic": [],
            "semantic": [],
            "user": [],
            "error": [],
        }
        self._search_input.blockSignals(True)
        self._search_input.clear()
        self._search_input.blockSignals(False)
        self._update_counters()
        self._refresh_current_tab()

    # ── Méthodes privées ─────────────────────────────────────────────────

    def _update_counters(self) -> None:
        """Met à jour les compteurs affichés par type."""
        counts = count_by_type(self._data)
        for mtype, count in counts.items():
            lbl = self._counter_labels.get(mtype)
            if lbl:
                lbl.setText(str(count))

    def _refresh_current_tab(self) -> None:
        """Rafraîchit le contenu de l'onglet actif avec filtre éventuel."""
        query = self._search_input.text()
        entries = self._data.get(self._current_type, [])

        if query:
            entries = filter_entries(entries, query)

        content_label = self._tab_labels.get(self._current_type)
        if content_label is None:
            return

        if not entries:
            content_label.setText(
                f"    {TEXT_SECONDARY}Aucune entrée mémoire."
                if not query
                else f"    {TEXT_SECONDARY}Aucun résultat pour \"{query}\"."
            )
            content_label.setStyleSheet(
                f"#MemoryContent_{self._current_type} {{ color: {TEXT_SECONDARY}; "
                f"font-size: 12px; padding: 4px; }}"
            )
            return

        lines: list[str] = []
        for i, entry in enumerate(entries):
            line = format_memory_entry(entry, self._current_type)
            lines.append(f"{i + 1}. {line}")

        content_label.setText("\n\n".join(lines))
        content_label.setStyleSheet(
            f"#MemoryContent_{self._current_type} {{ color: {TEXT_PRIMARY}; "
            f"font-size: 12px; padding: 4px; }}"
        )

    def _on_search(self, query: str) -> None:
        """Handler interne : changement dans la barre de recherche."""
        self._refresh_current_tab()
        self.search_requested.emit(query)

    def _on_clear_search(self) -> None:
        """Handler interne : bouton clear."""
        self._search_input.clear()
        self._refresh_current_tab()

    def _on_tab_changed(self, index: int) -> None:
        """Handler interne : changement d'onglet."""
        mtype_order = ("episodic", "semantic", "user", "error")
        if 0 <= index < len(mtype_order):
            self._current_type = mtype_order[index]
            self._refresh_current_tab()
