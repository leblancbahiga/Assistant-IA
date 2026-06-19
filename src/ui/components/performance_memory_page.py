"""
PerformanceMemoryPage — Fusion MemoryPage V11.x + MemoryExplorer V8 (P1-D).

Combine en une unique page avec tabs :
  - Faits (facts_table + ajout)
  - Procédures
  - Épisodique (données + recherche)
  - Sémantique (données + recherche)
  - Cache (stats + purge)

API publique compatible dashboard (slug "memory") :
  - set_data(data: dict)
  - refresh()
  - set_memory_store(memory_store)

Design cyberpunk NURU : bg #0A0E14, texte #C0D0E0, accent #3b82f6.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .memory_explorer import count_by_type, filter_entries, format_memory_entry
from .stat_card import StatCard

# ── Constantes de thème cyberpunk NURU ─────────────────────────────────────
BG_PRIMARY = "#0A0E14"
BG_PANEL = "#121820"
BG_INPUT = "#0D1117"
ACCENT_BLUE = "#3b82f6"
ACCENT_GREEN = "#22c55e"
ACCENT_ORANGE = "#f59e0b"
ACCENT_RED = "#ef4444"
TEXT_PRIMARY = "#C0D0E0"
TEXT_SECONDARY = "#6B7D93"
TEXT_DIM = "#3A4A5A"
BORDER_COLOR = "rgba(255,255,255,0.06)"
FONT_FAMILY = "'Segoe UI', 'SF Pro Display', system-ui, sans-serif"

# ── Styles QSS ──────────────────────────────────────────────────────────────

PANEL_STYLE = f"""
    PerformanceMemoryPage, QFrame#Panel {{
        background-color: {BG_PRIMARY};
        color: {TEXT_PRIMARY};
        font-family: {FONT_FAMILY};
    }}
"""

TAB_WIDGET_STYLE = f"""
    QTabWidget::pane {{
        background-color: transparent;
        border: none;
        border-top: 1px solid {BORDER_COLOR};
        margin-top: -1px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {TEXT_SECONDARY};
        border: none;
        padding: 8px 18px;
        font-size: 11px;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    QTabBar::tab:selected {{
        color: {ACCENT_BLUE};
        border-bottom: 2px solid {ACCENT_BLUE};
    }}
    QTabBar::tab:hover:!selected {{
        color: {TEXT_PRIMARY};
    }}
"""

TABLE_STYLE = f"""
    QTableWidget {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 6px;
        gridline-color: rgba(255,255,255,0.04);
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 6px 8px;
    }}
    QTableWidget::item:selected {{
        background-color: rgba(59, 130, 246, 0.2);
        color: {TEXT_PRIMARY};
    }}
    QHeaderView::section {{
        background-color: {BG_PANEL};
        color: {TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {BORDER_COLOR};
        padding: 6px 8px;
        font-size: 11px;
        font-weight: bold;
        text-transform: uppercase;
    }}
"""

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

INPUT_STYLE = f"""
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

BUTTON_GHOST = f"""
    QPushButton {{
        background-color: transparent;
        color: {TEXT_SECONDARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: rgba(59, 130, 246, 0.1);
        color: {ACCENT_BLUE};
        border: 1px solid {ACCENT_BLUE};
    }}
    QPushButton:pressed {{
        background-color: rgba(59, 130, 246, 0.2);
    }}
"""

BUTTON_PRIMARY = f"""
    QPushButton {{
        background-color: {ACCENT_BLUE};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: #2563eb;
    }}
    QPushButton:pressed {{
        background-color: #1d4ed8;
    }}
"""

BUTTON_DANGER = f"""
    QPushButton {{
        background-color: transparent;
        color: {ACCENT_RED};
        border: 1px solid {ACCENT_RED};
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: rgba(239, 68, 68, 0.1);
    }}
    QPushButton:pressed {{
        background-color: rgba(239, 68, 68, 0.2);
    }}
"""

LABEL_ENTRY_STYLE = f"""
    color: {TEXT_PRIMARY};
    font-size: 12px;
    padding: 4px 0px;
"""

LIST_SCROLL_STYLE = f"""
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        width: 4px;
        background: transparent;
    }}
    QScrollBar::handle:vertical {{
        background: {ACCENT_BLUE};
        border-radius: 2px;
        min-height: 20px;
    }}
"""


# ── Widget principal ────────────────────────────────────────────────────────


class PerformanceMemoryPage(QWidget):
    """Page mémoire unifiée avec 5 onglets : Faits, Procédures, Épisodique, Sémantique, Cache.

    Fusionne MemoryPage V11.x et MemoryExplorer V8.

    API publique :
        set_data(data: dict)   — injecte toutes les données
        refresh()              — déclenche le rechargement
        set_memory_store(ms)   — définit le memory store
    """

    def __init__(self, memory_store: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PerformanceMemoryPage")
        self.setStyleSheet(PANEL_STYLE)

        self._memory_store = memory_store

        # ── Données internes ──
        self._data: dict[str, Any] = {
            "facts": [],
            "procedures": "",
            "procedures_list": [],
            "episodic": [],
            "semantic": [],
            "user": [],
            "error": [],
            "cache_stats": {},
        }
        self._search_queries: dict[str, str] = {
            "episodic": "",
            "semantic": "",
        }

        self._setup_ui()

    # ────────────────────────────────────────────────────────────────────────
    #  API publique
    # ────────────────────────────────────────────────────────────────────────

    def set_data(self, data: dict[str, Any]) -> None:
        """Injecte toutes les données et rafraîchit les onglets.

        Le dictionnaire peut contenir :
            facts, procedures, procedures_list, episodic, semantic,
            user, error, cache_stats, stats
        """
        # Fusionner avec les données existantes
        for key in self._data:
            if key in data:
                self._data[key] = data[key]

        self._update_all()

    def refresh(self) -> None:
        """Déclenche un rechargement complet depuis le memory store (si défini)."""
        if self._memory_store is not None:
            self._load_from_store()
        else:
            self._update_all()

    def set_memory_store(self, memory_store: Any) -> None:
        """Définit le memory store et recharge les données."""
        self._memory_store = memory_store
        self.refresh()

    def load_data(self) -> None:
        """Alias legacy pour compatibilité avec MemoryPage."""
        self.refresh()

    # ────────────────────────────────────────────────────────────────────────
    #  UI
    # ────────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        header_widget = QWidget()
        header_widget.setStyleSheet(f"background-color: {BG_PRIMARY};")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 16, 20, 8)
        header_layout.setSpacing(10)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("🧠  MÉMOIRE")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: bold; "
            f"font-family: {FONT_FAMILY}; letter-spacing: 1px;"
        )

        self.btn_purge = QPushButton("🗑  Purger")
        self.btn_purge.setObjectName("GhostButton")
        self.btn_purge.setCursor(Qt.PointingHandCursor)
        self.btn_purge.setStyleSheet(BUTTON_DANGER)
        self.btn_purge.clicked.connect(self._purge_cache)

        self.btn_refresh = QPushButton("↻  Actualiser")
        self.btn_refresh.setObjectName("GhostButton")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setStyleSheet(BUTTON_GHOST)
        self.btn_refresh.clicked.connect(self.refresh)

        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self.btn_purge)
        title_row.addWidget(self.btn_refresh)
        header_layout.addLayout(title_row)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.stat_facts = StatCard("📌 Faits Stockés", icon="📌", value="0", color=ACCENT_BLUE)
        self.stat_cache = StatCard("💾 Cache", icon="💾", value="0 entrées", color=ACCENT_GREEN)
        self.stat_procedures = StatCard("📋 Procédures", icon="📋", value="0 règles", color=ACCENT_ORANGE)
        self.stat_episodic = StatCard("📅 Épisodique", icon="📅", value="0", color=ACCENT_BLUE)
        self.stat_semantic = StatCard("📚 Sémantique", icon="📚", value="0", color=ACCENT_GREEN)
        stats_row.addWidget(self.stat_facts)
        stats_row.addWidget(self.stat_cache)
        stats_row.addWidget(self.stat_procedures)
        stats_row.addWidget(self.stat_episodic)
        stats_row.addWidget(self.stat_semantic)
        header_layout.addLayout(stats_row)

        layout.addWidget(header_widget)

        # ── Status label ──────────────────────────────────────────────────
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; padding: 4px 20px;"
            f" background: rgba(255,255,255,0.02);"
        )
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # ── Tab widget ────────────────────────────────────────────────────
        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("PerformanceMemoryTabs")
        self._tab_widget.setStyleSheet(TAB_WIDGET_STYLE)
        self._tab_widget.tabBar().setCursor(Qt.PointingHandCursor)

        # Créer les 5 onglets
        self._build_facts_tab()
        self._build_procedures_tab()
        self._build_episodic_tab()
        self._build_semantic_tab()
        self._build_cache_tab()

        layout.addWidget(self._tab_widget, stretch=1)

        # ── Fallback panel (affiché si memory_store est None) ────────────
        self.fallback_panel = QFrame()
        self.fallback_panel.setObjectName("Panel")
        self.fallback_panel.setStyleSheet(
            f"background-color: {BG_PANEL}; border-radius: 8px;"
        )
        fallback_layout = QVBoxLayout(self.fallback_panel)
        fallback_title = QLabel("ℹ️  STOCK DE MÉMOIRE NON DISPONIBLE")
        fallback_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold; "
            f"padding: 10px 0;"
        )
        fallback_layout.addWidget(fallback_title)

        self.fallback_text = QLabel(
            "Le module MemoryStore n'est pas connecté.\n\n"
            "Cela peut arriver si :\n"
            "  • La base de données n'a pas encore été initialisée\n"
            "  • L'import de MemoryStore a échoué (dépendances manquantes)\n"
            "  • Aucun core NURU n'a fourni de store mémoire\n\n"
            "Vous pouvez :\n"
            "  • Redémarrer le dashboard après installation complète\n"
            "  • Vérifier les logs dans la page 📋 Logs\n"
            "  • Revenir plus tard quand le système sera prêt\n\n"
            "Dès qu'un MemoryStore sera disponible, cette page s'affichera "
            "automatiquement."
        )
        self.fallback_text.setWordWrap(True)
        self.fallback_text.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; padding: 10px; "
            f"line-height: 1.6;"
        )
        fallback_layout.addWidget(self.fallback_text)
        self.fallback_panel.hide()
        layout.addWidget(self.fallback_panel)

    def _build_facts_tab(self) -> None:
        """Construit l'onglet Faits avec table + formulaire d'ajout."""
        tab = QWidget()
        tab.setStyleSheet(f"background-color: {BG_PRIMARY};")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Add fact row
        add_layout = QHBoxLayout()
        add_layout.setSpacing(8)

        self.fact_input = QLineEdit()
        self.fact_input.setObjectName("FactInput")
        self.fact_input.setPlaceholderText("Ajouter un fait...")
        self.fact_input.setStyleSheet(INPUT_STYLE)
        self.fact_input.returnPressed.connect(self._add_fact)

        self.fact_category = QLineEdit()
        self.fact_category.setObjectName("FactCategory")
        self.fact_category.setPlaceholderText("Catégorie (ex: général)")
        self.fact_category.setStyleSheet(INPUT_STYLE)
        self.fact_category.setFixedWidth(160)

        self.btn_add_fact = QPushButton("+ Ajouter")
        self.btn_add_fact.setObjectName("PrimaryButton")
        self.btn_add_fact.setCursor(Qt.PointingHandCursor)
        self.btn_add_fact.setStyleSheet(BUTTON_PRIMARY)
        self.btn_add_fact.clicked.connect(self._add_fact)

        add_layout.addWidget(self.fact_input, stretch=1)
        add_layout.addWidget(self.fact_category)
        add_layout.addWidget(self.btn_add_fact)
        layout.addLayout(add_layout)

        # Facts table
        self.facts_table = QTableWidget()
        self.facts_table.setObjectName("FactsTable")
        self.facts_table.setStyleSheet(TABLE_STYLE)
        self.facts_table.setColumnCount(3)
        self.facts_table.setHorizontalHeaderLabels(["Contenu", "Catégorie", "Date"])
        self.facts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.facts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.facts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.facts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.facts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.facts_table.verticalHeader().setDefaultSectionSize(32)
        layout.addWidget(self.facts_table, stretch=1)

        # Empty state label
        self.facts_empty_label = QLabel("Aucun fait mémorisé pour le moment.")
        self.facts_empty_label.setAlignment(Qt.AlignCenter)
        self.facts_empty_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; padding: 20px;"
        )
        self.facts_empty_label.hide()
        layout.addWidget(self.facts_empty_label)

        self._tab_widget.addTab(tab, "📌  Faits")

    def _build_procedures_tab(self) -> None:
        """Construit l'onglet Procédures."""
        tab = QWidget()
        tab.setStyleSheet(f"background-color: {BG_PRIMARY};")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QLabel("📋  PROCÉDURES & RÈGLES")
        header.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold; "
            f"padding-bottom: 4px;"
        )
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(LIST_SCROLL_STYLE)

        self.proc_content = QLabel("Aucune procédure enregistrée.")
        self.proc_content.setWordWrap(True)
        self.proc_content.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; padding: 10px;"
        )
        self.proc_content.setTextFormat(Qt.PlainText)
        self.proc_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.proc_content.setTextInteractionFlags(Qt.TextSelectableByMouse)

        scroll.setWidget(self.proc_content)
        layout.addWidget(scroll, stretch=1)

        self._tab_widget.addTab(tab, "📋  Procédures")

    def _build_episodic_tab(self) -> None:
        """Construit l'onglet Épisodique avec barre de recherche."""
        tab = QWidget()
        tab.setStyleSheet(f"background-color: {BG_PRIMARY};")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Tête d'onglet
        header_row = QHBoxLayout()
        header = QLabel("📅  MÉMOIRE ÉPISODIQUE")
        header.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold;"
        )
        self._episodic_count_label = QLabel("0")
        self._episodic_count_label.setStyleSheet(
            f"color: {ACCENT_BLUE}; font-size: 10px; "
            f"background: rgba(59,130,246,0.1); padding: 2px 8px; "
            f"border-radius: 4px; font-weight: bold;"
        )
        header_row.addWidget(header)
        header_row.addSpacing(8)
        header_row.addWidget(self._episodic_count_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Barre de recherche
        search_layout = QHBoxLayout()
        search_layout.setSpacing(6)

        self._episodic_search = QLineEdit()
        self._episodic_search.setObjectName("EpisodicSearch")
        self._episodic_search.setPlaceholderText("🔍  Rechercher dans la mémoire épisodique...")
        self._episodic_search.setStyleSheet(SEARCH_STYLE)
        self._episodic_search.setFixedHeight(32)
        self._episodic_search.textChanged.connect(
            lambda txt: self._on_tab_search("episodic", txt)
        )
        search_layout.addWidget(self._episodic_search)

        self._episodic_clear_btn = QPushButton("✕")
        self._episodic_clear_btn.setFixedSize(28, 28)
        self._episodic_clear_btn.setCursor(Qt.PointingHandCursor)
        self._episodic_clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; "
            f"border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {TEXT_PRIMARY}; }}"
        )
        self._episodic_clear_btn.clicked.connect(
            lambda: self._clear_tab_search("episodic")
        )
        search_layout.addWidget(self._episodic_clear_btn)
        layout.addLayout(search_layout)

        # Liste des entrées
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(LIST_SCROLL_STYLE)

        self._episodic_content = QLabel()
        self._episodic_content.setObjectName("EpisodicContent")
        self._episodic_content.setWordWrap(True)
        self._episodic_content.setStyleSheet(
            f"#EpisodicContent {{ color: {TEXT_PRIMARY}; font-size: 12px; "
            f"padding: 4px; }}"
        )
        self._episodic_content.setTextFormat(Qt.PlainText)
        self._episodic_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._episodic_content.setTextInteractionFlags(Qt.TextSelectableByMouse)

        scroll.setWidget(self._episodic_content)
        layout.addWidget(scroll, stretch=1)

        self._tab_widget.addTab(tab, "📅  Épisodique")

    def _build_semantic_tab(self) -> None:
        """Construit l'onglet Sémantique avec barre de recherche."""
        tab = QWidget()
        tab.setStyleSheet(f"background-color: {BG_PRIMARY};")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Tête d'onglet
        header_row = QHBoxLayout()
        header = QLabel("📚  MÉMOIRE SÉMANTIQUE")
        header.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold;"
        )
        self._semantic_count_label = QLabel("0")
        self._semantic_count_label.setStyleSheet(
            f"color: {ACCENT_GREEN}; font-size: 10px; "
            f"background: rgba(34,197,94,0.1); padding: 2px 8px; "
            f"border-radius: 4px; font-weight: bold;"
        )
        header_row.addWidget(header)
        header_row.addSpacing(8)
        header_row.addWidget(self._semantic_count_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Barre de recherche
        search_layout = QHBoxLayout()
        search_layout.setSpacing(6)

        self._semantic_search = QLineEdit()
        self._semantic_search.setObjectName("SemanticSearch")
        self._semantic_search.setPlaceholderText("🔍  Rechercher dans la mémoire sémantique...")
        self._semantic_search.setStyleSheet(SEARCH_STYLE)
        self._semantic_search.setFixedHeight(32)
        self._semantic_search.textChanged.connect(
            lambda txt: self._on_tab_search("semantic", txt)
        )
        search_layout.addWidget(self._semantic_search)

        self._semantic_clear_btn = QPushButton("✕")
        self._semantic_clear_btn.setFixedSize(28, 28)
        self._semantic_clear_btn.setCursor(Qt.PointingHandCursor)
        self._semantic_clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; "
            f"border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {TEXT_PRIMARY}; }}"
        )
        self._semantic_clear_btn.clicked.connect(
            lambda: self._clear_tab_search("semantic")
        )
        search_layout.addWidget(self._semantic_clear_btn)
        layout.addLayout(search_layout)

        # Liste des entrées
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(LIST_SCROLL_STYLE)

        self._semantic_content = QLabel()
        self._semantic_content.setObjectName("SemanticContent")
        self._semantic_content.setWordWrap(True)
        self._semantic_content.setStyleSheet(
            f"#SemanticContent {{ color: {TEXT_PRIMARY}; font-size: 12px; "
            f"padding: 4px; }}"
        )
        self._semantic_content.setTextFormat(Qt.PlainText)
        self._semantic_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._semantic_content.setTextInteractionFlags(Qt.TextSelectableByMouse)

        scroll.setWidget(self._semantic_content)
        layout.addWidget(scroll, stretch=1)

        self._tab_widget.addTab(tab, "📚  Sémantique")

    def _build_cache_tab(self) -> None:
        """Construit l'onglet Cache avec stats et purge."""
        tab = QWidget()
        tab.setStyleSheet(f"background-color: {BG_PRIMARY};")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        header = QLabel("💾  CACHE SÉMANTIQUE")
        header.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(header)

        # Cache stats group
        stats_group = QGroupBox("Statistiques du Cache")
        stats_group.setStyleSheet(
            f"QGroupBox {{ color: {TEXT_SECONDARY}; font-size: 12px; font-weight: bold; "
            f"border: 1px solid {BORDER_COLOR}; border-radius: 8px; "
            f"margin-top: 12px; padding: 16px 12px 12px 12px; }}"
            f"QGroupBox::title {{ "
            f"subcontrol-origin: margin; subcontrol-position: top left; "
            f"padding: 0 8px; color: {TEXT_SECONDARY}; }}"
        )
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setSpacing(8)

        self._cache_stats_labels: dict[str, QLabel] = {}
        cache_stat_fields = [
            ("total_entries", "Total entrées"),
            ("cache_hits", "Cache hits"),
            ("cache_misses", "Cache misses"),
            ("hit_rate", "Taux de succès"),
            ("memory_size", "Taille mémoire"),
            ("last_updated", "Dernière mise à jour"),
        ]
        for field, display_name in cache_stat_fields:
            row = QHBoxLayout()
            name_label = QLabel(display_name)
            name_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
            value_label = QLabel("—")
            value_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setObjectName(f"CacheStat_{field}")
            self._cache_stats_labels[field] = value_label
            row.addWidget(name_label)
            row.addStretch()
            row.addWidget(value_label)
            stats_layout.addLayout(row)

        layout.addWidget(stats_group)

        # Purge section
        purge_group = QGroupBox("Actions")
        purge_group.setStyleSheet(
            f"QGroupBox {{ color: {TEXT_SECONDARY}; font-size: 12px; font-weight: bold; "
            f"border: 1px solid {BORDER_COLOR}; border-radius: 8px; "
            f"margin-top: 12px; padding: 16px 12px 12px 12px; }}"
            f"QGroupBox::title {{ "
            f"subcontrol-origin: margin; subcontrol-position: top left; "
            f"padding: 0 8px; color: {TEXT_SECONDARY}; }}"
        )
        purge_layout = QVBoxLayout(purge_group)
        purge_layout.setSpacing(8)

        purge_desc = QLabel(
            "Purger le cache sémantique libère de la mémoire mais peut ralentir "
            "temporairement les réponses de l'assistant le temps de reconstruire le cache."
        )
        purge_desc.setWordWrap(True)
        purge_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        purge_layout.addWidget(purge_desc)

        self.btn_purge_cache = QPushButton("🗑  Purger le Cache")
        self.btn_purge_cache.setObjectName("DangerButton")
        self.btn_purge_cache.setCursor(Qt.PointingHandCursor)
        self.btn_purge_cache.setStyleSheet(BUTTON_DANGER)
        self.btn_purge_cache.setFixedWidth(200)
        self.btn_purge_cache.clicked.connect(self._purge_cache)
        purge_layout.addWidget(self.btn_purge_cache)

        layout.addWidget(purge_group)

        layout.addStretch()

        self._tab_widget.addTab(tab, "💾  Cache")

    # ────────────────────────────────────────────────────────────────────────
    #  Remplissage des données
    # ────────────────────────────────────────────────────────────────────────

    def _update_all(self) -> None:
        """Met à jour tous les onglets et les stats."""
        self._update_facts_tab()
        self._update_procedures_tab()
        self._update_episodic_tab()
        self._update_semantic_tab()
        self._update_cache_tab()
        self._update_stat_cards()

    def _update_facts_tab(self) -> None:
        """Remplit la table des faits."""
        facts = self._data.get("facts", [])
        if not facts:
            self.facts_table.setRowCount(0)
            self.facts_empty_label.show()
            return

        self.facts_empty_label.hide()
        self.facts_table.setRowCount(len(facts))

        for i, fact in enumerate(facts):
            if isinstance(fact, dict):
                content = fact.get("content", fact.get("summary", str(fact)))
                category = fact.get("category", fact.get("fact_type", "general"))
                date = fact.get("updated_at", fact.get("timestamp", "—"))
                if isinstance(date, str) and len(date) > 10:
                    date = date[:10]
            else:
                content = str(fact)
                category = "general"
                date = "—"

            self.facts_table.setItem(i, 0, QTableWidgetItem(str(content)))
            self.facts_table.setItem(i, 1, QTableWidgetItem(str(category)))
            self.facts_table.setItem(i, 2, QTableWidgetItem(str(date)))

    def _update_procedures_tab(self) -> None:
        """Remplit le contenu des procédures."""
        procedures = self._data.get("procedures", "")
        procedures_list = self._data.get("procedures_list", [])

        if procedures_list:
            lines = "\n\n".join(
                f"• {p}" if isinstance(p, str) else f"• {p.get('name', str(p))}"
                for p in procedures_list
            )
            self.proc_content.setText(lines)
            self.proc_content.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 12px; padding: 10px;"
            )
        elif procedures and procedures.strip():
            self.proc_content.setText(procedures)
            self.proc_content.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 12px; padding: 10px;"
            )
        else:
            self.proc_content.setText("Aucune procédure enregistrée.")
            self.proc_content.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 13px; padding: 10px;"
            )

    def _update_episodic_tab(self) -> None:
        """Remplit le contenu de l'onglet épisodique avec filtre."""
        query = self._search_queries.get("episodic", "")
        entries = self._data.get("episodic", [])

        if query:
            entries = filter_entries(entries, query)

        self._episodic_count_label.setText(str(len(entries)))

        if not entries:
            self._episodic_content.setText(
                "    Aucune entrée épisodique."
                if not query
                else f"    Aucun résultat pour \"{query}\"."
            )
            self._episodic_content.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 12px; padding: 4px;"
            )
            return

        lines = [
            f"{i + 1}. {format_memory_entry(entry, 'episodic')}"
            for i, entry in enumerate(entries)
        ]
        self._episodic_content.setText("\n\n".join(lines))
        self._episodic_content.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; padding: 4px;"
        )

    def _update_semantic_tab(self) -> None:
        """Remplit le contenu de l'onglet sémantique avec filtre."""
        query = self._search_queries.get("semantic", "")
        entries = self._data.get("semantic", [])

        if query:
            entries = filter_entries(entries, query)

        self._semantic_count_label.setText(str(len(entries)))

        if not entries:
            self._semantic_content.setText(
                "    Aucune entrée sémantique."
                if not query
                else f"    Aucun résultat pour \"{query}\"."
            )
            self._semantic_content.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 12px; padding: 4px;"
            )
            return

        lines = [
            f"{i + 1}. {format_memory_entry(entry, 'semantic')}"
            for i, entry in enumerate(entries)
        ]
        self._semantic_content.setText("\n\n".join(lines))
        self._semantic_content.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; padding: 4px;"
        )

    def _update_cache_tab(self) -> None:
        """Remplit les stats du cache."""
        cache_stats = self._data.get("cache_stats", {})

        for field, label in [
            ("total_entries", "—"),
            ("cache_hits", "—"),
            ("cache_misses", "—"),
            ("hit_rate", "—"),
            ("memory_size", "—"),
            ("last_updated", "—"),
        ]:
            value_label = self._cache_stats_labels.get(field)
            if value_label is None:
                continue
            val = cache_stats.get(field, "—")
            if val == "—" and field in cache_stats:
                val = cache_stats[field]
            if field == "hit_rate" and isinstance(val, (int, float)):
                val = f"{val * 100:.1f}%" if val <= 1 else f"{val:.1f}%"
            if field == "memory_size" and isinstance(val, (int, float)):
                if val >= 1024 * 1024:
                    val = f"{val / (1024 * 1024):.2f} MB"
                elif val >= 1024:
                    val = f"{val / 1024:.2f} KB"
                else:
                    val = f"{val} B"
            value_label.setText(str(val))

    def _update_stat_cards(self) -> None:
        """Met à jour les cartes de stats dans le header."""
        # Faits
        facts = self._data.get("facts", [])
        self.stat_facts.set_value(str(len(facts)))

        # Cache
        cache_stats = self._data.get("cache_stats", {})
        cache_entries = cache_stats.get("total_entries", 0)
        self.stat_cache.set_value(f"{cache_entries} entrées")

        # Procédures
        procedures_list = self._data.get("procedures_list", [])
        procedures = self._data.get("procedures", "")
        if procedures_list:
            proc_count = len(procedures_list)
        elif procedures and procedures.strip():
            proc_count = len(procedures.split("\n"))
        else:
            proc_count = 0
        self.stat_procedures.set_value(f"{proc_count} règles")

        # Épisodique
        episodic = self._data.get("episodic", [])
        self.stat_episodic.set_value(str(len(episodic)))

        # Sémantique
        semantic = self._data.get("semantic", [])
        self.stat_semantic.set_value(str(len(semantic)))

    # ────────────────────────────────────────────────────────────────────────
    #  Recherche dans les tabs
    # ────────────────────────────────────────────────────────────────────────

    def _on_tab_search(self, tab_name: str, text: str) -> None:
        """Handler pour les changements dans les barres de recherche."""
        self._search_queries[tab_name] = text
        if tab_name == "episodic":
            self._update_episodic_tab()
        elif tab_name == "semantic":
            self._update_semantic_tab()

    def _clear_tab_search(self, tab_name: str) -> None:
        """Vide la barre de recherche d'un onglet."""
        search_input = (
            self._episodic_search if tab_name == "episodic"
            else self._semantic_search
        )
        search_input.blockSignals(True)
        search_input.clear()
        search_input.blockSignals(False)
        self._search_queries[tab_name] = ""
        if tab_name == "episodic":
            self._update_episodic_tab()
        elif tab_name == "semantic":
            self._update_semantic_tab()

    # ────────────────────────────────────────────────────────────────────────
    #  Chargement depuis memory_store
    # ────────────────────────────────────────────────────────────────────────

    def _load_from_store(self) -> None:
        """Charge toutes les données depuis le memory store et met à jour l'UI."""
        if self._memory_store is None:
            self._show_no_store_state()
            return

        try:
            # Facts
            facts = self._memory_store.get_recent_facts(limit=50) or []
            user_facts = self._memory_store.get_user_facts(limit=50) or []
            combined_facts = []

            for fact in facts:
                if isinstance(fact, dict):
                    combined_facts.append(fact)
                else:
                    combined_facts.append({"content": fact, "category": "general", "date": "—"})

            for uf in user_facts:
                if isinstance(uf, dict):
                    # Already dict, use as-is
                    combined_facts.append(uf)

            self._data["facts"] = combined_facts

            # Procedures
            try:
                procedures = self._memory_store.get_procedures() or ""
                self._data["procedures"] = procedures
            except Exception:
                self._data["procedures"] = ""

            # Procedures as list (some stores support this)
            try:
                procedures_list = self._memory_store.get_procedures_list() or []
                self._data["procedures_list"] = procedures_list
            except Exception:
                self._data["procedures_list"] = []

            # Cache stats
            try:
                cache_stats = self._memory_store.get_cache_stats() or {}
                self._data["cache_stats"] = cache_stats
            except Exception:
                self._data["cache_stats"] = {}

            # Épisodique & Sémantique (if the store has these)
            try:
                episodic = self._memory_store.get_episodic_memories(limit=100) or []
                self._data["episodic"] = episodic
            except Exception:
                self._data["episodic"] = []

            try:
                semantic = self._memory_store.get_semantic_memories(limit=100) or []
                self._data["semantic"] = semantic
            except Exception:
                self._data["semantic"] = []

            self._update_all()
            self.status_label.hide()
            self.fallback_panel.hide()

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("PerformanceMemoryPage._load_from_store error: %s", e)
            self.status_label.show()
            self.status_label.setText(
                f"⚠️ Erreur lors du chargement : {e}"
            )

    def _show_no_store_state(self) -> None:
        """Affiche le panneau d'information quand memory_store est None."""
        self.fallback_panel.show()
        self.status_label.hide()
        self.btn_purge.setEnabled(False)
        self.btn_purge_cache.setEnabled(False)

    # ────────────────────────────────────────────────────────────────────────
    #  Actions
    # ────────────────────────────────────────────────────────────────────────

    def _add_fact(self) -> None:
        """Ajoute un fait via le memory store."""
        text = self.fact_input.text().strip()
        if not text or self._memory_store is None:
            return

        category = self.fact_category.text().strip() or "general"
        try:
            self._memory_store.add_fact(text, category)
            self.fact_input.clear()
            self.fact_category.clear()
            self.refresh()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("PerformanceMemoryPage._add_fact error: %s", e)

    def _purge_cache(self) -> None:
        """Purger le cache sémantique avec confirmation."""
        from PySide6.QtWidgets import QMessageBox

        if self._memory_store is None:
            QMessageBox.information(
                self, "Non disponible",
                "Aucun MemoryStore connecté. Impossible de purger le cache."
            )
            return

        reply = QMessageBox.question(
            self, "Purger le cache",
            "Voulez-vous vraiment purger le cache sémantique ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self._memory_store.purge_cache()
                self._data["cache_stats"] = {}
                self._update_cache_tab()
                self._update_stat_cards()
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Purge impossible : {e}")

    # ────────────────────────────────────────────────────────────────────────
    #  Événements du cycle de vie
    # ────────────────────────────────────────────────────────────────────────

    def showEvent(self, event):
        """Actualise les données à l'affichage."""
        super().showEvent(event)
        self.refresh()
