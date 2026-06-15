"""
Guides Page — Bibliothèque de guides utilisateur avec recherche et filtrage.
Design Aether Dashboard, glassmorphism.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QPushButton, QComboBox,
    QLineEdit, QTextEdit, QDialog,
)
from PySide6.QtCore import Qt, Signal


# ─────────────────────────────────────────────────────────
# DONNÉES DES GUIDES (statiques)
# ─────────────────────────────────────────────────────────

GUIDES_DATA = [
    {
        "icon": "📄",
        "title": "Importer des documents",
        "category": "Import",
        "description": "Apprenez à ajouter des PDF, DOCX et TXT à la base documentaire pour enrichir les connaissances de NURU.",
        "content": (
            "# 📄 Importer des documents\n\n"
            "## Pourquoi importer des documents ?\n\n"
            "L'import de documents permet à NURU d'accéder à vos fichiers personnels "
            "(PDF, DOCX, TXT, MD, CSV, JSON) pour vous assister avec vos propres données.\n\n"
            "## Formats supportés\n\n"
            "- **PDF** — Documents Adobe Portable Document Format\n"
            "- **DOCX** — Documents Microsoft Word\n"
            "- **TXT** — Fichiers texte brut\n"
            "- **MD** — Fichiers Markdown\n"
            "- **CSV** — Données tabulaires\n"
            "- **JSON** — Fichiers de données structurées\n"
            "- **XLSX** — Classeurs Excel\n\n"
            "## Comment importer\n\n"
            "1. Ouvrez la page **Base Documentaire** depuis le menu latéral.\n"
            "2. Cliquez sur le bouton **📂 Importer** pour sélectionner un fichier unique.\n"
            "3. Utilisez **📂 Import Multiple** pour ajouter plusieurs fichiers à la fois.\n"
            "4. La progression de l'indexation s'affiche dans la barre de progression.\n"
            "5. Une fois indexé, le document apparaît dans le tableau avec son statut ✅.\n\n"
            "## Astuces\n\n"
            "- Les PDF volumineux peuvent prendre quelques secondes à indexer.\n"
            "- Les documents sont automatiquement découpés en chunks pour le RAG.\n"
            "- Vous pouvez glisser-déposer des fichiers directement dans la page."
        ),
    },
    {
        "icon": "🔍",
        "title": "Utiliser le RAG",
        "category": "RAG",
        "description": "Le Retrieval-Augmented Generation permet à NURU de répondre en exploitant vos documents importés.",
        "content": (
            "# 🔍 Utiliser le RAG\n\n"
            "## Qu'est-ce que le RAG ?\n\n"
            "Le **Retrieval-Augmented Generation** (RAG) est une technique qui combine "
            "la recherche d'information dans vos documents avec la génération de texte par IA. "
            "NURU peut ainsi répondre avec précision en s'appuyant sur vos données.\n\n"
            "## Comment ça fonctionne\n\n"
            "1. **Indexation** — Vos documents sont découpés en chunks et vectorisés.\n"
            "2. **Recherche** — Quand vous posez une question, NURU cherche les chunks les plus pertinents.\n"
            "3. **Génération** — Le contexte trouvé est envoyé au modèle pour produire une réponse.\n\n"
            "## Utilisation\n\n"
            "- Posez des questions sur le contenu de vos documents.\n"
            "- NURU affiche les sources utilisées dans sa réponse.\n"
            "- Utilisez le panneau de **Débogage RAG** pour voir quels chunks sont récupérés.\n\n"
            "## Configuration\n\n"
            "Dans **Paramètres > RAG**, vous pouvez ajuster :\n"
            "- Le nombre de chunks récupérés (1-20)\n"
            "- Le score de similarité minimum\n"
            "- Le modèle d'embedding utilisé"
        ),
    },
    {
        "icon": "🤖",
        "title": "Changer de modèle",
        "category": "Modèles",
        "description": "Basculez entre Qwen 3B local, Deepseek Cloud, Gemini ou Groq selon vos besoins.",
        "content": (
            "# 🤖 Changer de modèle\n\n"
            "## Modèles disponibles\n\n"
            "NURU supporte plusieurs modèles d'IA, chacun avec ses avantages :\n\n"
            "### 🏠 Local\n"
            "- **Qwen 3B** — Modèle léger, fonctionne hors-ligne, idéal pour la confidentialité\n\n"
            "### ☁️ Cloud\n"
            "- **Deepseek Cloud** — Performances élevées, grande capacité de contexte\n"
            "- **Gemini Flash** — Rapide et économique, par Google\n"
            "- **Groq Llama** — Inférence ultra-rapide sur matériel spécialisé\n\n"
            "## Comment changer\n\n"
            "1. Allez dans **Paramètres > Modèles IA**.\n"
            "2. Sélectionnez le modèle actif dans la liste déroulante.\n"
            "3. Ajustez les paramètres (température, top-p, contexte)\n"
            "4. Les changements s'appliquent immédiatement.\n\n"
            "## Conseils\n\n"
            "- Utilisez un modèle local pour les données sensibles.\n"
            "- Préférez les modèles cloud pour les tâches complexes.\n"
            "- Surveillez les performances dans les métriques système."
        ),
    },
    {
        "icon": "🎤",
        "title": "Mode vocal",
        "category": "Vocal",
        "description": "Activez la reconnaissance vocale et le TTS pour interagir avec NURU à la voix.",
        "content": (
            "# 🎤 Mode vocal\n\n"
            "## Présentation\n\n"
            "Le mode vocal permet d'interagir avec NURU par la parole :\n"
            "- **Reconnaissance vocale** — Parlez et NURU comprend vos requêtes\n"
            "- **Synthèse vocale (TTS)** — NURU répond oralement\n\n"
            "## Activation\n\n"
            "1. Cliquez sur l'icône 🎤 dans la barre de saisie.\n"
            "2. Autorisez l'accès au microphone si demandé.\n"
            "3. Parlez clairement pour énoncer votre requête.\n"
            "4. NURU transcrit automatiquement et génère une réponse.\n\n"
            "## Configuration\n\n"
            "Dans **Paramètres > Voix** :\n"
            "- Activez/désactivez le mode vocal\n"
            "- Réglez la vitesse de la synthèse vocale\n"
            "- Ajustez le volume\n"
            "- Sélectionnez le moteur TTS\n\n"
            "## Raccourcis\n\n"
            "- **Cmd+M** — Activer/désactiver le microphone\n"
            "- **Cmd+V** — Basculer le mode vocal"
        ),
    },
    {
        "icon": "⚡",
        "title": "Optimiser les performances",
        "category": "Performance",
        "description": "Conseils pour tirer le meilleur parti de NURU et optimiser les ressources système.",
        "content": (
            "# ⚡ Optimiser les performances\n\n"
            "## Conseils généraux\n\n"
            "### Mémoire RAM\n"
            "- Fermez les applications inutilisées pour libérer de la RAM.\n"
            "- NURU fonctionne mieux avec au moins 8 Go de RAM disponible.\n"
            "- Surveillez l'utilisation mémoire dans le panneau de métriques.\n\n"
            "### Modèle local\n"
            "- Le modèle Qwen 3B nécessite ~4 Go de RAM.\n"
            "- Pour les machines avec moins de 8 Go, privilégiez les modèles cloud.\n\n"
            "### Base documentaire\n"
            "- Limitez le nombre de chunks à 5-7 pour des réponses rapides.\n"
            "- Évitez d'indexer des fichiers trop volumineux (>100 pages).\n"
            "- Utilisez le filtre de score de similarité minimum (0.60 recommandé).\n\n"
            "### Cache\n"
            "- NURU met en cache les réponses pour les requêtes similaires.\n"
            "- Le cache améliore les performances jusqu'à 10x.\n"
            "- Vous pouvez vider le cache dans les paramètres système.\n\n"
            "## Monitoring\n\n"
            "Les métriques en temps réel (RAM, CPU, latence, TPS) sont affichées "
            "dans le panneau supérieur droit du tableau de bord."
        ),
    },
]


class GuideDetailDialog(QDialog):
    """Dialogue d'affichage détaillé d'un guide utilisateur."""

    def __init__(self, guide_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(guide_data["title"])
        self.setMinimumSize(600, 450)
        self.setModal(True)
        self.setObjectName("GuideDetailDialog")

        # Fond semi-transparent
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("""
            #GuideDetailDialog {
                background-color: rgba(10, 15, 26, 0.95);
                border: 1px solid rgba(0, 242, 255, 0.15);
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Titre
        title_label = QLabel(f"{guide_data['icon']}  {guide_data['title']}")
        title_label.setObjectName("GuideDetailTitle")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: 700;
            color: #00f2ff;
            letter-spacing: 1px;
        """)
        layout.addWidget(title_label)

        # Catégorie
        cat_label = QLabel(f"Catégorie : {guide_data['category']}")
        cat_label.setStyleSheet("""
            font-size: 11px;
            color: #64748b;
            letter-spacing: 1.5px;
            font-weight: 600;
            padding: 4px 10px;
            background-color: rgba(0, 242, 255, 0.06);
            border-radius: 6px;
            max-width: 200px;
        """)
        layout.addWidget(cat_label)

        # Contenu (read-only)
        self.content_edit = QTextEdit()
        self.content_edit.setObjectName("GuideDetailContent")
        self.content_edit.setReadOnly(True)
        self.content_edit.setPlainText(guide_data["content"])
        self.content_edit.setStyleSheet("""
            #GuideDetailContent {
                background-color: rgba(15, 20, 35, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 10px;
                color: #e2e8f0;
                font-size: 13px;
                padding: 12px;
                line-height: 1.6;
            }
            #GuideDetailContent:focus {
                border: 1px solid rgba(0, 242, 255, 0.2);
            }
        """)
        layout.addWidget(self.content_edit, stretch=1)

        # Bouton Fermer
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.setObjectName("PrimaryBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedWidth(120)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)


class GuidesPage(QWidget):
    """Bibliothèque de guides utilisateur avec recherche et filtrage."""

    guide_opened = Signal(str)  # signal émis quand un guide est ouvert

    def __init__(self, parent=None):
        super().__init__(parent)
        self._guides = GUIDES_DATA
        self._guide_cards = []  # liste de QFrame
        self.setup_ui()

    # ─────────── UI SETUP ───────────

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ── 1. HEADER ──
        header = QHBoxLayout()

        title = QLabel("📖 GUIDES & TUTORIELS")
        title.setObjectName("PageTitle")
        title.setStyleSheet("""
            font-size: 16px;
            font-weight: 700;
            color: #00f2ff;
            letter-spacing: 1px;
        """)
        header.addWidget(title)
        header.addStretch()

        # Champ de recherche
        self.search_input = QLineEdit()
        self.search_input.setObjectName("GuideSearchInput")
        self.search_input.setPlaceholderText("Rechercher un guide…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self._on_search)
        self.search_input.setStyleSheet("""
            #GuideSearchInput {
                background-color: rgba(20, 28, 48, 0.6);
                border: 1px solid rgba(0, 242, 255, 0.12);
                border-radius: 8px;
                color: #e2e8f0;
                padding: 6px 12px;
                font-size: 13px;
                min-height: 18px;
            }
            #GuideSearchInput:focus {
                border: 1px solid rgba(0, 242, 255, 0.4);
                background-color: rgba(20, 28, 48, 0.8);
            }
        """)
        header.addWidget(self.search_input)

        # Filtre par catégorie
        self.category_filter = QComboBox()
        self.category_filter.setObjectName("GuideCategoryFilter")
        self.category_filter.addItems(["Tous", "Import", "RAG", "Modèles", "Vocal", "Performance"])
        self.category_filter.currentTextChanged.connect(self._on_category_filter)
        self.category_filter.setStyleSheet("""
            #GuideCategoryFilter {
                background-color: rgba(20, 28, 48, 0.6);
                border: 1px solid rgba(0, 242, 255, 0.12);
                border-radius: 8px;
                color: #e2e8f0;
                padding: 6px 12px;
                font-size: 13px;
                min-height: 18px;
                min-width: 140px;
            }
            #GuideCategoryFilter:focus {
                border: 1px solid rgba(0, 242, 255, 0.4);
                background-color: rgba(20, 28, 48, 0.8);
            }
            #GuideCategoryFilter::drop-down {
                border: none;
                width: 24px;
                subcontrol-origin: padding;
                subcontrol-position: top right;
                padding-right: 8px;
            }
            #GuideCategoryFilter QAbstractItemView {
                background-color: rgba(10, 15, 26, 0.95);
                border: 1px solid rgba(0, 242, 255, 0.15);
                border-radius: 8px;
                color: #e2e8f0;
                padding: 4px;
                outline: none;
            }
        """)
        header.addWidget(self.category_filter)

        layout.addLayout(header)

        # ── 2. GRILLE DE GUIDES (ScrollArea) ──
        scroll = QScrollArea()
        scroll.setObjectName("GuideGrid")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none; background: transparent;")

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_layout = QVBoxLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 8, 0, 8)
        self.grid_layout.setSpacing(12)

        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll, stretch=1)

        # ── 3. EMPTY STATE ──
        self.empty_label = QLabel(
            "🔍 Aucun guide ne correspond à votre recherche.\n"
            "Essayez d'autres mots-clés ou réinitialisez les filtres."
        )
        self.empty_label.setObjectName("EmptyState")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("""
            #EmptyState {
                color: #64748b;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        # ── Initialisation ──
        self._build_all_cards()

    # ─────────── BUILD CARDS ───────────

    def _build_all_cards(self):
        """Construit les cartes guides et les ajoute à la grille."""
        for guide in self._guides:
            card = self._create_card(guide)
            self._guide_cards.append(card)
            self.grid_layout.addWidget(card)
        self.grid_layout.addStretch()

    def _create_card(self, guide: dict) -> QFrame:
        """Crée une carte cliquable pour un guide."""
        card = QFrame()
        card.setObjectName("GuideCard")
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet("""
            #GuideCard {
                background-color: rgba(15, 20, 35, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 16px;
            }
            #GuideCard:hover {
                border: 1px solid #00f2ff;
            }
        """)

        # Layout horizontal : icône | texte | lien
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(16)

        # Icône
        icon_label = QLabel(guide["icon"])
        icon_label.setStyleSheet("""
            font-size: 28px;
            background: transparent;
        """)
        icon_label.setFixedSize(42, 42)
        icon_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(icon_label)

        # Texte (titre + description)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        title_label = QLabel(guide["title"])
        title_label.setStyleSheet("""
            font-size: 15px;
            font-weight: 600;
            color: #00f2ff;
            background: transparent;
        """)
        text_layout.addWidget(title_label)

        desc_label = QLabel(guide["description"])
        desc_label.setStyleSheet("""
            font-size: 13px;
            color: #94a3b8;
            background: transparent;
            line-height: 1.4;
        """)
        desc_label.setWordWrap(True)
        text_layout.addWidget(desc_label)

        # Tag catégorie
        cat_tag = QLabel(f"{guide['category']}")
        cat_tag.setStyleSheet("""
            font-size: 10px;
            color: #64748b;
            font-weight: 600;
            letter-spacing: 1px;
            background-color: rgba(0, 242, 255, 0.06);
            border-radius: 4px;
            padding: 2px 8px;
        """)
        cat_tag.setFixedWidth(cat_tag.sizeHint().width() + 16)
        text_layout.addWidget(cat_tag)

        card_layout.addLayout(text_layout, stretch=1)

        # Lien "Lire →"
        read_link = QLabel("Lire →")
        read_link.setObjectName("GuideReadLink")
        read_link.setStyleSheet("""
            #GuideReadLink {
                font-size: 13px;
                font-weight: 600;
                color: #64748b;
                background: transparent;
            }
            #GuideCard:hover #GuideReadLink {
                color: #00f2ff;
            }
        """)
        read_link.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        read_link.setFixedWidth(60)
        card_layout.addWidget(read_link)

        # Connecter le clic
        title = guide["title"]
        card.mousePressEvent = lambda event, t=title: self._on_card_clicked(t)

        # Stocker le titre dans le card pour filtrage
        card._guide_title = guide["title"]
        card._guide_category = guide["category"]

        return card

    # ─────────── FILTRES ET RECHERCHE ───────────

    def _on_search(self, text: str):
        """Filtre les cartes par titre."""
        self.search_guides(text)

    def search_guides(self, text: str):
        """Filtre les cartes dont le titre contient le texte."""
        query = text.strip().lower()
        self._apply_filters(search_query=query)

    def _on_category_filter(self, category: str):
        """Filtre les cartes par catégorie."""
        self.filter_by_category(category)

    def filter_by_category(self, category: str):
        """Montre seulement les guides d'une catégorie."""
        self._apply_filters(category_filter=category)

    def _apply_filters(self, search_query: str = "", category_filter: str = ""):
        """Applique tous les filtres actifs et met à jour la visibilité."""
        # Récupérer les valeurs actuelles si non fournies
        if not search_query and self.search_input:
            search_query = self.search_input.text().strip().lower()
        if not category_filter and self.category_filter:
            category_filter = self.category_filter.currentText()

        visible_count = 0
        for card in self._guide_cards:
            title_match = not search_query or search_query in card._guide_title.lower()
            cat_match = category_filter == "Tous" or card._guide_category == category_filter
            is_visible = title_match and cat_match
            card.setVisible(is_visible)
            if is_visible:
                visible_count += 1

        # Empty state
        has_data = visible_count > 0
        self.empty_label.setVisible(not has_data)

    # ─────────── OUVRIR UN GUIDE ───────────

    def _on_card_clicked(self, title: str):
        """Callback quand une carte est cliquée."""
        self.open_guide(title)

    def open_guide(self, title: str):
        """Ouvre le dialogue de détail pour le guide correspondant."""
        for guide in self._guides:
            if guide["title"] == title:
                dialog = GuideDetailDialog(guide, self)
                dialog.exec()
                self.guide_opened.emit(title)
                return

    # ─────────── RÉINITIALISATION ───────────

    def reset_filters(self):
        """Réinitialise la recherche et le filtre."""
        self.search_input.clear()
        self.category_filter.setCurrentIndex(0)
