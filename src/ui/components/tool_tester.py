"""
NURU V10 — ToolTester : Interface de test des outils NURU.

Permet de tester :
  - DocumentGenerator (Word, PDF, PPTX, XLSX, Markdown)
  - WebResearcher (recherche web avec scoring)

Design cyberpunk NURU : bg #0D1117, accent #00A3FF.
"""

from __future__ import annotations

import importlib.util
import logging
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Couleurs du thème ──────────────────────────────────────────────────────

BG_DARK = "#0D1117"
BG_PANEL = "#161b22"
BG_INPUT = "#0D1117"
ACCENT_BLUE = "#00A3FF"
ACCENT_GREEN = "#39FF14"
ACCENT_RED = "#FF3333"
ACCENT_ORANGE = "#FF8C00"
ACCENT_PURPLE = "#A78BFA"
ACCENT_YELLOW = "#FFD700"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
BORDER_COLOR = "rgba(255,255,255,0.08)"

PANEL_STYLE = f"""
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
"""

CARD_STYLE = f"""
    background-color: rgba(0, 0, 0, 0.5);
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 14px;
"""

INPUT_STYLE = f"""
    QLineEdit, QPlainTextEdit {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 6px;
        padding: 8px;
        font-size: 12px;
    }}
    QLineEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {ACCENT_BLUE};
    }}
"""

BTN_PRIMARY_STYLE = f"""
    QPushButton {{
        background-color: {ACCENT_BLUE};
        color: #000;
        font-weight: bold;
        font-size: 12px;
        border: none;
        border-radius: 6px;
        padding: 10px 24px;
    }}
    QPushButton:hover {{
        background-color: #33B5FF;
    }}
    QPushButton:pressed {{
        background-color: #0088CC;
    }}
    QPushButton:disabled {{
        background-color: rgba(0,163,255,0.3);
        color: rgba(0,0,0,0.4);
    }}
"""

COMBO_STYLE = f"""
    QComboBox {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 4px;
        padding: 6px 10px;
        font-size: 12px;
    }}
    QComboBox::drop-down {{
        border: none;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 6px solid {TEXT_SECONDARY};
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        selection-background-color: rgba(0,163,255,0.2);
    }}
"""


# ── Helpers de vérification des modules ────────────────────────────────────


def _module_available(module_path: str) -> bool:
    """Vérifie si un module Python existe (importlib)."""
    spec = importlib.util.find_spec(module_path)
    return spec is not None


# Vérifications au niveau module (calculées une fois au chargement)
DOC_GEN_AVAILABLE: bool = _module_available("src.tools.document")
WEB_RESEARCH_AVAILABLE: bool = _module_available("src.research.web")
REGISTRY_AVAILABLE: bool = _module_available("src.tools.registry")


def _status_badge(available: bool, label: str) -> str:
    """Retourne une pastille de statut HTML."""
    if available:
        return f'<span style="color:{ACCENT_GREEN};font-weight:bold;">🟢 {label}</span>'
    return f'<span style="color:{ACCENT_RED};font-weight:bold;">🔴 {label} (non disponible)</span>'


# ══════════════════════════════════════════════════════════════════════════
#  ToolTester — page de test des outils
# ══════════════════════════════════════════════════════════════════════════


class ToolTester(QScrollArea):
    """Interface de test interactive pour les outils NURU V10.

    Sections :
      - Document Generator : format + titre + sections → génère un fichier réel
      - Résultat : affiche le chemin, taille, durée
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ToolTester")
        self.setWidgetResizable(True)
        self.setStyleSheet(f"background-color: {BG_DARK}; border: none;")
        self._build_ui()

    def _build_ui(self) -> None:
        """Construit l'interface de test."""
        container = QWidget()
        container.setStyleSheet(f"background-color: {BG_DARK};")
        self.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── En-tête ──
        title = QLabel("🔧 Testeur d'Outils NURU V10")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 22px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Testez les outils de génération de documents et de recherche web en temps réel."
        )
        subtitle.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── Barre de statut des outils ─────────────────────────────────
        status_panel = QFrame()
        status_panel.setStyleSheet(f"""
            background-color: {BG_PANEL};
            border: 1px solid {BORDER_COLOR};
            border-radius: 6px;
            padding: 10px 14px;
        """)
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(14, 8, 14, 8)
        status_layout.setSpacing(20)

        status_label = QLabel("📡 Statut des outils :")
        status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold; background: transparent;")
        status_layout.addWidget(status_label)

        self._doc_status = QLabel("")
        self._doc_status.setStyleSheet("background: transparent;")
        status_layout.addWidget(self._doc_status)

        self._web_status = QLabel("")
        self._web_status.setStyleSheet("background: transparent;")
        status_layout.addWidget(self._web_status)

        self._reg_status = QLabel("")
        self._reg_status.setStyleSheet("background: transparent;")
        status_layout.addWidget(self._reg_status)

        status_layout.addStretch()
        layout.addWidget(status_panel)

        # Mise à jour des statuts
        self._update_status_indicators()

        # ════════════════════════════════════════════════════════════════
        #  Section 1 : Document Generator
        # ════════════════════════════════════════════════════════════════
        doc_label = QLabel("📄 Générateur de Documents")
        doc_label.setStyleSheet(f"color: {ACCENT_BLUE}; font-size: 15px; font-weight: bold; background: transparent;")
        layout.addWidget(doc_label)

        doc_desc = QLabel(
            "Génère un fichier réel (Word, PDF, PowerPoint ou Excel) avec le titre et les sections ci-dessous."
        )
        doc_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        doc_desc.setWordWrap(True)
        layout.addWidget(doc_desc)

        # Panneau document
        self._doc_panel = QFrame()
        self._doc_panel.setStyleSheet(CARD_STYLE)
        doc_layout = QVBoxLayout(self._doc_panel)
        doc_layout.setSpacing(10)

        # Ligne 1 : Format + Nom du fichier
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        fmt_lbl = QLabel("Format :")
        fmt_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        row1.addWidget(fmt_lbl)

        self._format_combo = QComboBox()
        self._format_combo.addItems(["Word (.docx)", "PDF (.pdf)", "PowerPoint (.pptx)", "Excel (.xlsx)", "Markdown (.md)"])
        self._format_combo.setStyleSheet(COMBO_STYLE)
        self._format_combo.setFixedWidth(180)
        row1.addWidget(self._format_combo)

        row1.addSpacing(20)

        name_lbl = QLabel("Nom du fichier :")
        name_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        row1.addWidget(name_lbl)

        self._file_name_input = QLineEdit("test_nuru_document")
        self._file_name_input.setStyleSheet(INPUT_STYLE)
        self._file_name_input.setFixedWidth(250)
        row1.addWidget(self._file_name_input)

        row1.addStretch()
        doc_layout.addLayout(row1)

        # Ligne 2 : Titre du document
        row2 = QHBoxLayout()
        title_lbl = QLabel("Titre du document :")
        title_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        row2.addWidget(title_lbl)

        self._doc_title_input = QLineEdit("Rapport NURU V10 — Test de génération")
        self._doc_title_input.setStyleSheet(INPUT_STYLE)
        row2.addWidget(self._doc_title_input, stretch=1)
        doc_layout.addLayout(row2)

        # Ligne 3 : Sections
        sections_lbl = QLabel("Sections (une par ligne : Titre | Contenu) :")
        sections_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        doc_layout.addWidget(sections_lbl)

        self._sections_input = QPlainTextEdit()
        self._sections_input.setStyleSheet(INPUT_STYLE)
        self._sections_input.setPlaceholderText(
            "Introduction | Ce document a été généré automatiquement par NURU V10 pour tester le générateur de documents.\n"
            "Méthodologie | L'outil DocumentGenerator supporte les formats Word, PDF, PowerPoint et Excel.\n"
            "Résultats | Le test a été réalisé avec succès. Tous les formats produisent des fichiers valides.\n"
            "Conclusion | NURU V10 est capable de générer des documents professionnels en quelques secondes."
        )
        self._sections_input.setFixedHeight(120)
        doc_layout.addWidget(self._sections_input)

        # Bouton générer
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._generate_btn = QPushButton("🚀 Générer le document")
        self._generate_btn.setStyleSheet(BTN_PRIMARY_STYLE)
        self._generate_btn.setFixedHeight(38)
        self._generate_btn.clicked.connect(self._generate_document)
        btn_row.addWidget(self._generate_btn)

        doc_layout.addLayout(btn_row)

        # Résultat
        self._doc_result = QLabel("")
        self._doc_result.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent; padding: 4px 0;")
        self._doc_result.setWordWrap(True)
        self._doc_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        doc_layout.addWidget(self._doc_result)

        layout.addWidget(self._doc_panel)

        # ════════════════════════════════════════════════════════════════
        #  Section 2 : Web Researcher
        # ════════════════════════════════════════════════════════════════
        layout.addSpacing(8)
        web_label = QLabel("🌐 Test Recherche Web")
        web_label.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 15px; font-weight: bold; background: transparent;")
        layout.addWidget(web_label)

        web_desc = QLabel(
            "Teste le WebResearcher — scoring de pertinence, déduplication et classement."
        )
        web_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        web_desc.setWordWrap(True)
        layout.addWidget(web_desc)

        self._web_panel = QFrame()
        self._web_panel.setStyleSheet(CARD_STYLE)
        web_layout = QVBoxLayout(self._web_panel)
        web_layout.setSpacing(10)

        # Requête
        web_query_row = QHBoxLayout()
        q_lbl = QLabel("Requête de test :")
        q_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        web_query_row.addWidget(q_lbl)

        self._web_query_input = QLineEdit("Rapport agronomique RDC 2024")
        self._web_query_input.setStyleSheet(INPUT_STYLE)
        web_query_row.addWidget(self._web_query_input, stretch=1)

        self._web_test_btn = QPushButton("🔍 Tester le scoring")
        self._web_test_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(57,255,20,0.15);
                color: {ACCENT_GREEN};
                font-weight: bold;
                font-size: 11px;
                border: 1px solid rgba(57,255,20,0.3);
                border-radius: 6px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: rgba(57,255,20,0.25);
            }}
        """)
        self._web_test_btn.clicked.connect(self._test_web_search)
        web_query_row.addWidget(self._web_test_btn)

        web_layout.addLayout(web_query_row)

        # Résultat web
        self._web_result = QLabel("")
        self._web_result.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent; padding: 4px 0;")
        self._web_result.setWordWrap(True)
        self._web_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        web_layout.addWidget(self._web_result)

        layout.addWidget(self._web_panel)

        # ════════════════════════════════════════════════════════════════
        #  Section 3 : ToolRegistry Info
        # ════════════════════════════════════════════════════════════════
        layout.addSpacing(8)
        reg_label = QLabel("📋 Outils enregistrés")
        reg_label.setStyleSheet(f"color: {ACCENT_PURPLE}; font-size: 15px; font-weight: bold; background: transparent;")
        layout.addWidget(reg_label)

        self._reg_panel = QFrame()
        self._reg_panel.setStyleSheet(CARD_STYLE)
        reg_layout = QVBoxLayout(self._reg_panel)
        reg_layout.setContentsMargins(14, 10, 14, 10)
        reg_layout.setSpacing(4)

        self._reg_refresh_btn = QPushButton("🔄 Actualiser")
        self._reg_refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {ACCENT_BLUE};
                font-size: 10px;
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                border: 1px solid {ACCENT_BLUE};
            }}
        """)
        self._reg_refresh_btn.setFixedWidth(120)
        self._reg_refresh_btn.clicked.connect(self._refresh_registry)
        reg_layout.addWidget(self._reg_refresh_btn)

        self._reg_info = QLabel("Cliquez sur Actualiser pour voir les outils enregistrés.")
        self._reg_info.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        self._reg_info.setWordWrap(True)
        reg_layout.addWidget(self._reg_info)

        layout.addWidget(self._reg_panel)

        layout.addStretch()

    # ── Indicateurs de statut ──────────────────────────────────────────────

    def _update_status_indicators(self) -> None:
        """Met à jour les pastilles de statut pour chaque module."""
        self._doc_status.setText(_status_badge(DOC_GEN_AVAILABLE, "DocumentGenerator"))
        self._web_status.setText(_status_badge(WEB_RESEARCH_AVAILABLE, "WebResearcher"))
        self._reg_status.setText(_status_badge(REGISTRY_AVAILABLE, "ToolRegistry"))

    # ── Helpers ────────────────────────────────────────────────────────────

    def _get_format_enum(self) -> str:
        """Retourne le format sélectionné en chaîne."""
        mapping = {
            "Word (.docx)": "word",
            "PDF (.pdf)": "pdf",
            "PowerPoint (.pptx)": "pptx",
            "Excel (.xlsx)": "xlsx",
            "Markdown (.md)": "markdown",
        }
        return mapping.get(self._format_combo.currentText(), "word")

    def _get_extension(self) -> str:
        """Retourne l'extension de fichier pour le format sélectionné."""
        mapping = {
            "word": ".docx",
            "pdf": ".pdf",
            "pptx": ".pptx",
            "xlsx": ".xlsx",
            "markdown": ".md",
        }
        return mapping.get(self._get_format_enum(), ".docx")

    # ── Génération de document ─────────────────────────────────────────────

    def _generate_document(self) -> None:
        """Génère un document réel en utilisant DocumentGenerator."""
        self._generate_btn.setEnabled(False)
        self._generate_btn.setText("⏳ Génération en cours...")
        self._doc_result.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        self._doc_result.setText("Génération en cours...")

        try:
            # Vérification explicite de la disponibilité du module
            if not DOC_GEN_AVAILABLE:
                raise ImportError(
                    "Le module 'src.tools.document' est introuvable.\n\n"
                    "Le backend DocumentGenerator n'a pas encore été implémenté.\n"
                    "Pour l'ajouter :\n"
                    "  1. Créez src/tools/document.py avec les classes DocumentGenerator,\n"
                    "     DocumentSpec, DocSection, DocFormat\n"
                    "  2. Implémentez generate(spec, output_path) pour produire des fichiers\n"
                    "     aux formats Word, PDF, PPTX, XLSX et Markdown.\n\n"
                    "Le formulaire ci-dessus reste fonctionnel — remplissez les champs,\n"
                    "puis cliquez sur Générer une fois le backend ajouté."
                )

            from src.tools.document import DocumentGenerator, DocumentSpec, DocSection, DocFormat

            # Parser les sections
            raw_text = self._sections_input.toPlainText().strip()
            sections = []
            for line in raw_text.split("\n"):
                line = line.strip()
                if "|" in line:
                    title, content = line.split("|", 1)
                    sections.append(DocSection(
                        title=title.strip(),
                        content=content.strip(),
                        level=1,
                    ))

            # Fallback si pas de sections parsées
            if not sections:
                sections.append(DocSection(
                    title="Section unique",
                    content=raw_text or "Contenu de test généré par NURU V10.",
                    level=1,
                ))

            # Format
            fmt_str = self._get_format_enum()
            fmt_map = {
                "word": DocFormat.WORD,
                "pdf": DocFormat.PDF,
                "pptx": DocFormat.PPTX,
                "xlsx": DocFormat.XLSX,
                "markdown": DocFormat.MARKDOWN,
            }
            doc_format = fmt_map.get(fmt_str, DocFormat.WORD)

            # Chemin de sortie
            output_dir = Path.home() / "Nuru_Workspace" / "documents"
            output_dir.mkdir(parents=True, exist_ok=True)
            file_name = self._file_name_input.text().strip() or "test_nuru_document"
            output_path = output_dir / f"{file_name}{self._get_extension()}"

            # Générer
            spec = DocumentSpec(
                title=self._doc_title_input.text().strip() or "Document NURU",
                format=doc_format,
                sections=sections,
                metadata={"Généré par": "NURU V10", "Outil": "DocumentGenerator"},
            )

            start = time.time()
            generator = DocumentGenerator()
            result_path = generator.generate(spec, output_path)
            duration = (time.time() - start) * 1000

            file_size = result_path.stat().st_size
            size_str = f"{file_size / 1024:.1f} Ko" if file_size < 1_048_576 else f"{file_size / 1_048_576:.1f} Mo"

            self._doc_result.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 11px; background: transparent;")
            self._doc_result.setText(
                f"✅ Document généré avec succès !\n"
                f"   📁 {result_path}\n"
                f"   📦 {size_str}  |  ⏱️ {duration:.0f} ms  |  📄 {len(sections)} section(s)"
            )

        except ImportError as e:
            logger.warning("DocumentGenerator non disponible: %s", e)
            self._doc_result.setStyleSheet(f"color: {ACCENT_YELLOW}; font-size: 11px; background: transparent;")
            self._doc_result.setText(f"⚠️ Module DocumentGenerator non disponible\n\n{e}")

        except Exception as e:
            logger.error("Échec génération document: %s", e)
            self._doc_result.setStyleSheet(f"color: {ACCENT_RED}; font-size: 11px; background: transparent;")
            self._doc_result.setText(f"❌ Erreur : {e}")

        finally:
            self._generate_btn.setEnabled(True)
            self._generate_btn.setText("🚀 Générer le document")

    # ── Test de recherche web ──────────────────────────────────────────────

    def _test_web_search(self) -> None:
        """Teste le scoring et le filtrage du WebResearcher.

        Tente une recherche réelle via WebResearcher.search().
        Si le backend n'est pas intégré (retourne []), passe en mode
        démo avec des données générées dynamiquement par score_relevance
        pour valider la pipeline scoring → dédup → classement → filtrage.
        """
        self._web_test_btn.setEnabled(False)
        self._web_result.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        self._web_result.setText("Test en cours...")

        try:
            # Vérification explicite de la disponibilité du module
            if not WEB_RESEARCH_AVAILABLE:
                raise ImportError(
                    "Le module 'src.research.web' est introuvable.\n\n"
                    "Le backend WebResearcher n'a pas encore été implémenté.\n"
                    "Pour l'ajouter, créez src/research/web.py avec les classes\n"
                    "WebResearcher, SearchResult, ResearchQuery.\n\n"
                    "Le formulaire reste fonctionnel dès que le backend est présent."
                )

            from src.research.web import WebResearcher, SearchResult, ResearchQuery

            researcher = WebResearcher()
            query_text = self._web_query_input.text().strip() or "test"

            # 1) Tentative de recherche réelle
            rq = ResearchQuery(query=query_text, max_results=5, min_relevance=0.1)
            real_results = researcher.search(rq)

            if real_results:
                # Résultats réels — on applique la pipeline sur ceux-ci
                deduped = researcher.deduplicate(real_results)
                ranked = researcher.rank_results(deduped)
                filtered = researcher.filter_by_relevance(ranked, rq.min_relevance)

                lines = [
                    f"🔍 Requête : \"{rq.query}\"",
                    f"🌐 Source : recherche réelle",
                    f"📊 Résultats bruts : {len(real_results)}",
                    f"   Après dédup : {len(deduped)}",
                    f"   Après classement : {len(ranked)}",
                    f"   Après filtrage (≥{rq.min_relevance}) : {len(filtered)}",
                    "",
                ]
                for i, r in enumerate(filtered, 1):
                    lines.append(f"  {i}. {r.title}")
                    lines.append(f"     Score : {r.relevance_score:.2f}  |  {r.url}")

            else:
                # 2) Mode démo — pas de backend recherche disponible
                #    Génère des résultats d'exemple dynamiquement pour
                #    valider la pipeline complète (scoring → dédup →
                #    classement → filtrage).
                demo_sources = [
                    (f"{query_text} — Rapport de synthèse",
                     f"Analyse détaillée de {query_text} avec données récentes."),
                    (f"Analyse : {query_text} — Perspectives 2025",
                     f"Étude prospective sur le thème {query_text}."),
                    (f"{query_text} — Étude comparative",
                     f"Comparaison des approches existantes autour de {query_text}."),
                ]
                demo_results = []
                for title, snippet in demo_sources:
                    score = researcher.score_relevance(query_text, title, snippet)
                    url_title = title.lower().replace(" ", "-")[:30]
                    demo_results.append(SearchResult(
                        url=f"https://demo.nuru.local/{url_title}",
                        title=title,
                        snippet=snippet,
                        relevance_score=score,
                    ))

                deduped = researcher.deduplicate(demo_results)
                ranked = researcher.rank_results(deduped)
                filtered = researcher.filter_by_relevance(ranked, 0.1)

                lines = [
                    f"🔍 Requête : \"{query_text}\"",
                    f"🧪 Mode DÉMO — backend recherche web non intégré",
                    f"   (WebResearcher.search() nécessite un adaptateur",
                    f"    Firecrawl / SerpAPI / Tavily — ajouter dans",
                    f"    src/research/web.py si besoin)",
                    "",
                    f"📊 Résultats démo : {len(demo_results)}",
                    f"   Après dédup : {len(deduped)}",
                    f"   Après classement : {len(ranked)}",
                    f"   Après filtrage (≥0.1) : {len(filtered)}",
                    "",
                ]
                for i, r in enumerate(filtered, 1):
                    lines.append(f"  {i}. {r.title}")
                    lines.append(f"     Score : {r.relevance_score:.2f}  |  {r.url}")

            self._web_result.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 11px; background: transparent;")
            self._web_result.setText("\n".join(lines))

        except ImportError as e:
            logger.warning("WebResearcher non disponible: %s", e)
            self._web_result.setStyleSheet(f"color: {ACCENT_YELLOW}; font-size: 11px; background: transparent;")
            self._web_result.setText(f"⚠️ Module WebResearcher non disponible\n\n{e}")

        except Exception as e:
            logger.error("Échec test web: %s", e)
            self._web_result.setStyleSheet(f"color: {ACCENT_RED}; font-size: 11px; background: transparent;")
            self._web_result.setText(f"❌ Erreur : {e}")

        finally:
            self._web_test_btn.setEnabled(True)

    # ── Registre des outils ────────────────────────────────────────────────

    def _refresh_registry(self) -> None:
        """Affiche les outils enregistrés dans ToolRegistry."""
        try:
            # Vérification explicite de la disponibilité du module
            if not REGISTRY_AVAILABLE:
                raise ImportError(
                    "Le module 'src.tools.registry' est introuvable.\n\n"
                    "Le backend ToolRegistry n'a pas encore été implémenté.\n"
                    "Pour l'ajouter, créez src/tools/registry.py avec la classe\n"
                    "ToolRegistry et sa méthode list_tools().\n\n"
                    "Le bouton Actualiser reste fonctionnel dès que le backend est présent."
                )

            from src.tools.registry import ToolRegistry

            registry = ToolRegistry()
            tools = registry.list_tools()

            if not tools:
                self._reg_info.setText("ℹ️ Aucun outil enregistré. Exécutez l'application pour initialiser le registre.")
                self._reg_info.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
                return

            lines = [f"📋 {len(tools)} outil(s) enregistré(s) :", ""]
            for t in tools:
                params_str = ", ".join(p.name for p in t.parameters[:5])
                if len(t.parameters) > 5:
                    params_str += "..."
                lines.append(f"  🛠️ {t.name} ({t.category})")
                lines.append(f"     {t.description}")
                lines.append(f"     Paramètres : [{params_str}]")
                lines.append("")

            self._reg_info.setText("\n".join(lines))
            self._reg_info.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; background: transparent;")

        except ImportError as e:
            logger.warning("ToolRegistry non disponible: %s", e)
            self._reg_info.setStyleSheet(f"color: {ACCENT_YELLOW}; font-size: 11px; background: transparent;")
            self._reg_info.setText(f"⚠️ Module ToolRegistry non disponible\n\n{e}")

        except Exception as e:
            logger.error("Échec refresh registry: %s", e)
            self._reg_info.setStyleSheet(f"color: {ACCENT_RED}; font-size: 11px; background: transparent;")
            self._reg_info.setText(f"❌ Erreur : {e}")
