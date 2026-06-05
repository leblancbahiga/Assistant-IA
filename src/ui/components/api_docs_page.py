"""
ApiDocsPage — Page de documentation API interactive de l'architecture NURU
V4.5 : Cyberpunk obsidienne, glassmorphism, sections interactives.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QPushButton, QTextEdit,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


# ─────────────────────────────────────────────────────────
# ApiDocsPage
# ─────────────────────────────────────────────────────────

class ApiDocsPage(QWidget):
    """Page de documentation interactive de l'architecture NURU."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── HEADER ──
        header = QHBoxLayout()
        header.setContentsMargins(24, 16, 24, 4)
        header.setSpacing(12)

        title = QLabel("⟨ ⟩ DOCUMENTATION API")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()

        btn_copy = QPushButton("📋 Copier")
        btn_copy.setObjectName("GhostBtn")
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_all_content)
        header.addWidget(btn_copy)

        layout.addLayout(header)

        # ── SCROLL AREA ──
        scroll = QScrollArea()
        scroll.setObjectName("ApiDocsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_widget.setObjectName("ApiDocsContent")
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(24, 8, 24, 24)
        self.content_layout.setSpacing(10)

        # ── 1. Architecture du système ──
        self._add_section(
            "🏗  Architecture du système",
            (
                "NURU est un assistant IA hybride local/cloud combinant un "
                "moteur RAG vectoriel, un pipeline de génération multi-modèle, "
                "des modules vocaux et une base documentaire persistante — le "
                "tout orchestré par un routeur sémantique intelligent.\n\n"
                "┌─────────────────────────────────────────────┐\n"
                "│            CONSOLE NURU (Interface)          │\n"
                "├───────┬─────────────┬──────────┬────────────┤\n"
                "│  RAG  │ Pipeline IA │   Voix   │  Documents │\n"
                "│ Engine│  (LLM Local │  STT/TTS │    Store   │\n"
                "│       │   / Cloud)  │          │            │\n"
                "└───────┴─────────────┴──────────┴────────────┘\n"
                "         ↕                    ↕\n"
                "   ┌──────────┐      ┌──────────────┐\n"
                "   │ Mémoire  │      │   Routeur    │\n"
                "   │  Longue   │      │  Sémantique  │\n"
                "   └──────────┘      └──────────────┘"
            ),
            extra_content=(
                "Composants principaux :\n"
                "  • Console — Interface de chat principale\n"
                "  • Moteur RAG — Recherche vectorielle et contextuelle\n"
                "  • Pipeline IA — Génération locale (Ollama) et cloud (OpenAI, Anthropic)\n"
                "  • Modules Voix — Synthèse et reconnaissance vocale\n"
                "  • Base documentaire — Indexation et ingestion de fichiers\n"
                "  • Routeur sémantique — Aiguillage intelligent des requêtes"
            ),
        )

        # ── 2. API de Chat ──
        self._add_section(
            "💬 API de Chat",
            (
                "Endpoint : POST /api/chat\n\n"
                "Paramètres :\n"
                "  • query (string, requis) — Message utilisateur\n"
                "  • model (string, optionnel) — Modèle à utiliser (défaut: qwen-3b)\n"
                "  • temperature (float, optionnel) — Créativité (0.0 – 2.0, défaut: 0.7)\n"
                "  • stream (bool, optionnel) — Réponse en streaming (défaut: true)\n\n"
                "Exemple de requête :"
            ),
            code_block='{\n  "query": "Bonjour",\n  "model": "qwen-3b",\n  "temperature": 0.7\n}',
            extra_content=(
                "Réponse : Streaming de tokens via Server-Sent Events (SSE).\n"
                "Chaque token est encapsulé dans un chunk JSON au format :\n"
                '{"token": "...", "done": false, "model": "qwen-3b"}'
            ),
        )

        # ── 3. API RAG ──
        self._add_section(
            "📚 API RAG",
            (
                "Endpoint : POST /api/rag/retrieve\n\n"
                "Paramètres :\n"
                "  • query (string, requis) — Requête de recherche\n"
                "  • k (int, optionnel) — Nombre de chunks à retourner (défaut: 5, max: 20)\n"
                "  • threshold (float, optionnel) — Seuil de similarité minimale (0.0 – 1.0, défaut: 0.65)\n\n"
                "Exemple de réponse :"
            ),
            code_block='{\n  "query": "Qui est YARID ?",\n  "results": [\n    {\n      "chunk_id": "c7f3a1b2",\n      "source": "yarid_report_2025.pdf",\n      "score": 0.923,\n      "text": "YARID (Youth Alliance for Refugee...)",\n      "page": 12\n    },\n    {\n      "chunk_id": "d4e8f9c1",\n      "source": "yarid_overview.md",\n      "score": 0.871,\n      "text": "YARID est une organisation...",\n      "page": 3\n    }\n  ],\n  "total_chunks": 2,\n  "latency_ms": 145\n}',
            extra_content=(
                "Le moteur RAG utilise une base vectorielle ChromaDB / FAISS avec\n"
                "des embeddings bilingues (anglais/français) pour une recherche\n"
                "cross-langue performante."
            ),
        )

        # ── 4. API Système ──
        self._add_section(
            "⚙  API Système",
            (
                "GET /api/system/status\n"
                "→ Status complet du système (RAM, CPU, modules actifs, temps d'activité)\n\n"
                "GET /api/system/health\n"
                "→ Healthcheck simple (uptime, version, état des connecteurs)\n\n"
                "POST /api/system/shutdown\n"
                "→ Arrêt gracieux de NURU\n\n"
                "GET /api/system/config\n"
                "→ Configuration courante (modèle actif, réglages RAG, préférences)\n\n"
                "POST /api/system/config\n"
                "→ Mise à jour de la configuration (partielle ou complète)"
            ),
            code_block='{\n  "status": "running",\n  "uptime_s": 28453,\n  "version": "4.5.0",\n  "ram": {\n    "used_gb": 1.2,\n    "total_gb": 8.0,\n    "percent": 15\n  },\n  "modules": {\n    "rag": "active",\n    "voice": "idle",\n    "pipeline": "active"\n  },\n  "active_model": "qwen-3b"\n}',
        )

        # ── 5. API Modèles ──
        self._add_section(
            "🧠 API Modèles",
            (
                "GET /api/models/list\n"
                "→ Liste des modèles disponibles localement et via cloud\n\n"
                "POST /api/models/switch\n"
                "→ Changement du modèle actif en cours d'exécution\n\n"
                "GET /api/models/active\n"
                "→ Modèle actuellement chargé et ses métriques\n"
                "(taille, contexte max, vitesse d'inférence)\n\n"
                "POST /api/models/unload\n"
                "→ Déchargement du modèle courant (libération RAM)"
            ),
            code_block='{\n  "models": [\n    {\n      "id": "qwen-3b",\n      "name": "Qwen 3B",\n      "provider": "ollama",\n      "context": 8192,\n      "status": "active"\n    },\n    {\n      "id": "deepseek-r1:7b",\n      "name": "DeepSeek R1 7B",\n      "provider": "ollama",\n      "context": 16384,\n      "status": "available"\n    },\n    {\n      "id": "gpt-4o",\n      "name": "GPT-4o",\n      "provider": "openai",\n      "context": 128000,\n      "status": "available"\n    }\n  ]\n}',
            extra_content=(
                "Le switch de modèle est progressif : le modèle sortant reste en mémoire\n"
                "jusqu'à ce que le nouveau soit complètement chargé, garantissant zéro\n"
                "temps d'arrêt pour l'utilisateur."
            ),
        )

        # Final spacer
        self.content_layout.addStretch()

        scroll.setWidget(content_widget)
        layout.addWidget(scroll, stretch=1)

    # ─────────── PRIVATE HELPERS ───────────

    def _add_section(self, title: str, content: str, *,
                     code_block: str = "", extra_content: str = ""):
        """Create a consistent documentation section frame."""
        section = QFrame()
        section.setObjectName("DocSection")

        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(18, 16, 18, 18)
        section_layout.setSpacing(8)

        # Title
        title_label = QLabel(title)
        title_label.setObjectName("DocSectionTitle")
        section_layout.addWidget(title_label)

        # Main content
        content_label = QLabel(content)
        content_label.setObjectName("DocSectionContent")
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.PlainText)  # preserve ASCII art
        section_layout.addWidget(content_label)

        # Optional code block
        if code_block:
            code_edit = QTextEdit()
            code_edit.setObjectName("CodeBlock")
            code_edit.setPlainText(code_block)
            code_edit.setReadOnly(True)
            code_edit.setFixedHeight(
                self._estimate_code_height(code_block)
            )
            font = QFont("JetBrains Mono", 12)
            font.setStyleHint(QFont.Monospace)
            code_edit.setFont(font)
            section_layout.addWidget(code_edit)

        # Optional extra content
        if extra_content:
            extra_label = QLabel(extra_content)
            extra_label.setObjectName("DocSectionContent")
            extra_label.setWordWrap(True)
            section_layout.addWidget(extra_label)

        self.content_layout.addWidget(section)

    @staticmethod
    def _estimate_code_height(code: str) -> int:
        """Estimate the QTextEdit height based on line count."""
        lines = code.count("\n") + 1
        # Rough estimate: ~20px per line + padding
        return max(60, lines * 22 + 16)

    def _copy_all_content(self):
        """Copy all documentation content to clipboard."""
        from PySide6.QtGui import QGuiApplication

        parts = []
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QFrame):
                section = item.widget()
                labels = section.findChildren(QLabel, "DocSectionTitle")
                contents = section.findChildren(QLabel, "DocSectionContent")
                code_edits = section.findChildren(QTextEdit, "CodeBlock")

                for lbl in labels:
                    parts.append(lbl.text())
                for c in contents:
                    parts.append(c.text())
                for ce in code_edits:
                    parts.append(ce.toPlainText())

        QGuiApplication.clipboard().setText("\n\n".join(parts))
