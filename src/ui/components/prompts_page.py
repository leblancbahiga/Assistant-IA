"""
PromptsPage — Galerie de prompts classés par catégorie avec favoris et copie.
Cyberpunk glassmorphism, NURU V4.5.
"""
import logging
import json
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QPushButton, QComboBox,
    QLineEdit, QSizePolicy, QGridLayout,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QClipboard

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# DONNÉES STATIQUES DES PROMPTS
# ─────────────────────────────────────────────────────────

DEFAULT_PROMPTS = [
    {
        "categorie": "Analyse documentaire",
        "titre": "Analyse de document PDF",
        "contenu": "Analyse ce document PDF et extrais les points clés, les arguments principaux et une synthèse structurée en 200 mots maximum.",
    },
    {
        "categorie": "Analyse documentaire",
        "titre": "Extraction de données",
        "contenu": "Extrais toutes les données chiffrées, dates et entités nommées de ce document et présente-les dans un tableau structuré.",
    },
    {
        "categorie": "Recherche",
        "titre": "Recherche et synthèse",
        "contenu": "Effectue une recherche sur [sujet] et synthétise les informations trouvées en 5 points essentiels avec sources.",
    },
    {
        "categorie": "Recherche",
        "titre": "Analyse comparative",
        "contenu": "Compare les différentes approches / solutions concernant [sujet] et présente un tableau comparatif avantages-inconvénients.",
    },
    {
        "categorie": "Résumé",
        "titre": "Résumé concis",
        "contenu": "Résume le texte suivant en 5 points clés maximum. Chaque point doit tenir en une phrase courte et précise.",
    },
    {
        "categorie": "Résumé",
        "titre": "Résumé exécutif",
        "contenu": "Produis un résumé exécutif de ce document adapté à un comité de direction : enjeux, constats, recommandations.",
    },
    {
        "categorie": "Traduction",
        "titre": "Traduction français → anglais",
        "contenu": "Traduis ce texte du français vers l'anglais en conservant le ton, le style et la terminologie technique.",
    },
    {
        "categorie": "Traduction",
        "titre": "Traduction anglais → français",
        "contenu": "Traduis ce texte de l'anglais vers le français avec une attention particulière aux expressions idiomatiques.",
    },
    {
        "categorie": "Codage",
        "titre": "Analyse et revue de code",
        "contenu": "Explique le code suivant et suggère des améliorations de performance, sécurité et maintenabilité.",
    },
    {
        "categorie": "Codage",
        "titre": "Génération de code",
        "contenu": "Génère un script [langage] qui résout le problème suivant en respectant les bonnes pratiques et en incluant la gestion d'erreurs.",
    },
    {
        "categorie": "Agriculture",
        "titre": "Pratiques culturales",
        "contenu": "Quelles sont les meilleures pratiques pour la culture du maïs en zone tropicale ? Inclus calendrier, fertilisation et gestion des ravageurs.",
    },
    {
        "categorie": "Agriculture",
        "titre": "Diagnostic de culture",
        "contenu": "Mon culture de [plante] présente [symptômes]. Quel est le diagnostic probable et quelles mesures correctives recommandez-vous ?",
    },
    {
        "categorie": "Gestion de projet",
        "titre": "Décomposition de projet",
        "contenu": "Décompose ce projet en tâches avec un planning estimé, jalons clés, dépendances et risques identifiés.",
    },
    {
        "categorie": "Gestion de projet",
        "titre": "Analyse SWOT",
        "contenu": "Réalise une analyse SWOT (Forces, Faiblesses, Opportunités, Menaces) pour [projet/initiative] avec des recommandations actionnables.",
    },
    {
        "categorie": "Diagnostic",
        "titre": "Diagnostic de problème",
        "contenu": "Diagnostique le problème suivant à partir des symptômes décrits, propose les causes possibles et une procédure de résolution pas à pas.",
    },
    {
        "categorie": "Diagnostic",
        "titre": "Arbre de décision",
        "contenu": "Construis un arbre de décision pour diagnostiquer [problème] en partant des symptômes généraux vers les causes spécifiques.",
    },
]

CATEGORIES = [
    "Tous",
    "Analyse documentaire",
    "Recherche",
    "Résumé",
    "Traduction",
    "Codage",
    "Agriculture",
    "Gestion de projet",
    "Diagnostic",
]


# ─────────────────────────────────────────────────────────
# PromptCard — Widget individuel pour un prompt
# ─────────────────────────────────────────────────────────

class PromptCard(QFrame):
    """Carte individuelle de prompt avec titre, catégorie, contenu et boutons."""

    def __init__(self, index: int, data: dict, parent=None):
        super().__init__(parent)
        self._index = index
        self._data = data
        self.setObjectName("PromptCard")
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # ── Ligne supérieure : Titre + badge catégorie ──
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.lbl_titre = QLabel(data["titre"])
        self.lbl_titre.setObjectName("PromptCardTitle")
        self.lbl_titre.setWordWrap(True)
        top_row.addWidget(self.lbl_titre, stretch=1)

        self.lbl_categorie = QLabel(data["categorie"].upper())
        self.lbl_categorie.setObjectName("PromptCardBadge")
        self.lbl_categorie.setFixedHeight(22)
        top_row.addWidget(self.lbl_categorie)

        layout.addLayout(top_row)

        # ── Contenu (tronqué visuellement à 2 lignes via CSS) ──
        self.lbl_contenu = QLabel(data["contenu"])
        self.lbl_contenu.setObjectName("PromptCardContent")
        self.lbl_contenu.setWordWrap(True)
        layout.addWidget(self.lbl_contenu)

        # ── Boutons d'action ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_copy = QPushButton("📋 Copier")
        self.btn_copy.setObjectName("CopyBtn")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setFixedHeight(28)

        self.btn_fav = QPushButton("☆ Favori")
        self.btn_fav.setObjectName("FavoriteBtn")
        self.btn_fav.setCursor(Qt.PointingHandCursor)
        self.btn_fav.setFixedHeight(28)
        self.btn_fav.setCheckable(True)

        if data.get("favori", False):
            self.btn_fav.setText("★ Favori")
            self.btn_fav.setChecked(True)

        btn_row.addWidget(self.btn_copy)
        btn_row.addWidget(self.btn_fav)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def set_favorite(self, is_fav: bool):
        """Met à jour l'état favori sans émettre de signal."""
        self._data["favori"] = is_fav
        self.btn_fav.setText("★ Favori" if is_fav else "☆ Favori")
        self.btn_fav.setChecked(is_fav)

    def is_favorite(self) -> bool:
        return self._data.get("favori", False)

    def get_data(self) -> dict:
        return self._data

    def get_index(self) -> int:
        return self._index

    def set_index(self, idx: int):
        self._index = idx


# ─────────────────────────────────────────────────────────
# PromptsPage — Galerie de prompts
# ─────────────────────────────────────────────────────────

class PromptsPage(QWidget):
    """Galerie de prompts classés par catégorie avec favoris et copie."""

    FAVORITES_FILE = Path.home() / ".nuru_prompt_favorites.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prompts_data = self._load_prompts()
        self._filtered_indices = []  # indices dans _prompts_data visibles après filtrage
        self._favorites_ids: set = self._load_favorites()
        self._copy_timer = None
        self.setup_ui()
        self._apply_filters()

    # ─────────── CHARGEMENT / SAUVEGARDE ───────────

    def _load_prompts(self) -> list:
        """Charge les prompts depuis la liste statique."""
        prompts = []
        for p in DEFAULT_PROMPTS:
            entry = dict(p)
            entry["favori"] = False
            prompts.append(entry)
        return prompts

    def _load_favorites(self) -> set:
        """Charge les indices des favoris depuis le fichier JSON."""
        try:
            if self.FAVORITES_FILE.exists():
                data = json.loads(self.FAVORITES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return set(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Impossible de charger les favoris : {e}")
        return set()

    def _save_favorites(self):
        """Sauvegarde les indices des favoris dans le fichier JSON."""
        try:
            ids = [i for i, p in enumerate(self._prompts_data) if p.get("favori")]
            self.FAVORITES_FILE.write_text(
                json.dumps(ids, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning(f"Impossible de sauvegarder les favoris : {e}")

    # ─────────── UI SETUP ───────────

    def setup_ui(self):
        """Construit l'interface complète de la page."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ── 1. HEADER ──
        header = QHBoxLayout()
        header.setContentsMargins(24, 16, 24, 0)

        title = QLabel("✨ EXEMPLES DE PROMPTS")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()

        # Filtre Favoris
        self.btn_fav_filter = QPushButton("⭐ Favoris")
        self.btn_fav_filter.setObjectName("GhostBtn")
        self.btn_fav_filter.setCursor(Qt.PointingHandCursor)
        self.btn_fav_filter.setCheckable(True)
        self.btn_fav_filter.toggled.connect(self._on_fav_filter_toggled)
        header.addWidget(self.btn_fav_filter)

        layout.addLayout(header)

        # ── 2. BARRE DE RECHERCHE ET FILTRE ──
        filters_frame = QFrame()
        filters_frame.setObjectName("FilterBar")
        filters_frame.setFixedHeight(44)
        filters_layout = QHBoxLayout(filters_frame)
        filters_layout.setContentsMargins(24, 4, 24, 4)
        filters_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("PromptSearchInput")
        self.search_input.setPlaceholderText("Rechercher un prompt…")
        self.search_input.textChanged.connect(self._on_search)
        self.search_input.setClearButtonEnabled(True)

        self.category_filter = QComboBox()
        self.category_filter.setObjectName("PromptCategoryFilter")
        self.category_filter.addItems(CATEGORIES)
        self.category_filter.currentTextChanged.connect(self._on_category_changed)

        filters_layout.addWidget(self.search_input, stretch=1)
        filters_layout.addWidget(self.category_filter)
        layout.addWidget(filters_frame)

        # ── 3. GRILLE DE PROMPTS (SCROLLABLE) ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("PromptScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("PromptGrid")
        self.scroll_content.setStyleSheet("background: transparent;")
        self.grid_layout = QVBoxLayout(self.scroll_content)
        self.grid_layout.setContentsMargins(24, 8, 24, 24)
        self.grid_layout.setSpacing(12)
        self.grid_layout.addStretch()

        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area, stretch=1)

        # ── 4. EMPTY STATE ──
        self.empty_label = QLabel(
            "🔍 Aucun prompt trouvé.\n"
            "Essayez de modifier vos filtres ou votre recherche."
        )
        self.empty_label.setObjectName("EmptyState")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

    # ─────────── FILTRAGE ───────────

    def _on_search(self, text: str):
        """Callback lorsque le texte de recherche change."""
        self._apply_filters()

    def _on_category_changed(self, cat: str):
        """Callback lorsque la catégorie sélectionnée change."""
        self._apply_filters()

    def _on_fav_filter_toggled(self, checked: bool):
        """Callback pour le filtre 'Favoris uniquement'."""
        self._apply_filters()

    def _apply_filters(self):
        """Applique tous les filtres actifs et reconstruit la grille."""
        search_text = self.search_input.text().strip().lower()
        category = self.category_filter.currentText()
        fav_only = self.btn_fav_filter.isChecked()

        indices = []
        for i, prompt in enumerate(self._prompts_data):
            # Filtre favoris
            if fav_only and not prompt.get("favori", False):
                continue

            # Filtre catégorie
            if category != "Tous" and prompt["categorie"] != category:
                continue

            # Filtre texte
            if search_text:
                if search_text not in prompt["titre"].lower():
                    continue

            indices.append(i)

        self._filtered_indices = indices
        self._rebuild_grid()

    def _rebuild_grid(self):
        """Reconstruit les cartes de prompt dans la grille."""
        # Vider la grille (conserver le stretch final)
        while self.grid_layout.count() > 1:
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        # Retirer l'ancien stretch s'il existe
        last_stretch = self.grid_layout.takeAt(self.grid_layout.count() - 1)
        if last_stretch:
            del last_stretch

        visible_count = len(self._filtered_indices)
        self.empty_label.setVisible(visible_count == 0)

        for idx_in_list, prompt_idx in enumerate(self._filtered_indices):
            prompt = self._prompts_data[prompt_idx]
            card = PromptCard(prompt_idx, prompt)
            card.btn_copy.clicked.connect(
                lambda checked, c=prompt["contenu"]: self._copy_prompt(c)
            )
            card.btn_fav.toggled.connect(
                lambda checked, i=prompt_idx: self._toggle_favorite(i, checked)
            )
            self.grid_layout.addWidget(card)

        # Rajouter le stretch à la fin
        self.grid_layout.addStretch()

    # ─────────── ACTIONS ───────────

    def _copy_prompt(self, content: str):
        """Copie le contenu du prompt dans le presse-papier avec feedback."""
        clipboard = QClipboard()
        clipboard.setText(content)

        # Feedback visuel : on trouve le bouton source via l'expéditeur
        btn = self.sender()
        if btn and isinstance(btn, QPushButton):
            original_text = btn.text()
            btn.setText("✓ Copié!")
            btn.setEnabled(False)

            # Restaurer après 1.5s
            if self._copy_timer:
                self._copy_timer.stop()
            self._copy_timer = QTimer()
            self._copy_timer.setSingleShot(True)
            self._copy_timer.timeout.connect(
                lambda b=btn, t=original_text: self._reset_copy_btn(b, t)
            )
            self._copy_timer.start(1500)

    def _reset_copy_btn(self, btn: QPushButton, original_text: str):
        """Restore le bouton après le feedback visuel."""
        try:
            btn.setText(original_text)
            btn.setEnabled(True)
        except RuntimeError:
            pass  # widget peut avoir été supprimé

    def _toggle_favorite(self, index: int, checked: bool):
        """Bascule l'état favori d'un prompt et met à jour la carte."""
        if index < 0 or index >= len(self._prompts_data):
            return

        self._prompts_data[index]["favori"] = checked

        # Mettre à jour la carte si elle existe encore
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), PromptCard):
                card = item.widget()
                if card.get_index() == index:
                    card.set_favorite(checked)
                    break

        # Si le filtre favori est actif, reconstruire
        if self.btn_fav_filter.isChecked():
            self._apply_filters()

        self._save_favorites()

    def search_prompts(self, text: str):
        """Filtre les prompts par texte (interface publique)."""
        self.search_input.setText(text)

    def filter_category(self, cat: str):
        """Filtre les prompts par catégorie (interface publique)."""
        idx = CATEGORIES.index(cat) if cat in CATEGORIES else 0
        self.category_filter.setCurrentIndex(idx)

    def copy_prompt(self, content: str):
        """Copie un prompt (interface publique)."""
        self._copy_prompt(content)

    def toggle_favorite(self, index: int):
        """Bascule l'état favori (interface publique)."""
        if 0 <= index < len(self._prompts_data):
            current = self._prompts_data[index].get("favori", False)
            self._toggle_favorite(index, not current)

    def show_all_prompts(self):
        """Affiche tous les prompts (désactive les filtres)."""
        self.search_input.clear()
        self.category_filter.setCurrentIndex(0)
        self.btn_fav_filter.setChecked(False)
        self._apply_filters()

    def get_favorites(self) -> list:
        """Retourne la liste des prompts favoris."""
        return [p for p in self._prompts_data if p.get("favori")]
