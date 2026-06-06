"""
ApiDocsPage — Page de documentation API interactive de l'architecture NURU
V6.2 : Aether Dashboard, RAG hybride avancé, mémoire long terme structurée.
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
            "🏗  Architecture NURU V6.2",
            (
                "NURU est un assistant IA hybride local/cloud optimisé pour Apple Silicon M1 (8 Go RAM).\n"
                "Il combine un moteur RAG vectoriel (sqlite-vec + FTS5 BM25), un LLM local Phi-4-mini\n"
                "(via MLX Metal), un fallback cloud Groq/OpenRouter, et une mémoire persistante structurée.\n\n"
                "┌────────────────────────────────────────────────────┐\n"
                "│               AETHER DASHBOARD (PySide6)           │\n"
                "├──────────┬───────────────────────┬─────────────────┤\n"
                "│ Sidebar  │   Console centrale    │   Télémétrie    │\n"
                "│ Icônes   │   Chat + streaming    │ RAM, LLM, RAG  │\n"
                "│ Nav.     │   Bulles avec confiance│ Notifications   │\n"
                "└──────────┴───────────────────────┴─────────────────┘\n"
                "       ↕                        ↕\n"
                "┌──────────────┐      ┌──────────────────────┐\n"
                "│  RAG Engine  │      │  Orchestrateur V4.5  │\n"
                "│ sqlite-vec   │      │  Routeur → RAG → Gen  │\n"
                "│ + BM25 FTS5  │      │  → Vérification → UI  │\n"
                "│ RRF Fusion   │      │  Dual-Query Retrieval │\n"
                "└──────────────┘      └──────────────────────┘"
            ),
            extra_content=(
                "Composants principaux V6.2 :\n"
                "  • Console — Interface de chat avec bulles, score confiance, actions 👍👎📋\n"
                "  • Moteur RAG — sqlite-vec (768d) + FTS5 BM25 + RRF Fusion + Profile Boost\n"
                "  • LLM Local — Phi-4-mini-instruct-4bit via MLX (~12 tok/s sur M1)\n"
                "  • LLM Cloud — Groq (llama-3.3-70b) / fallback OpenRouter (DeepSeek V4 Flash)\n"
                "  • TokenJuice — Compression 40-60% avant envoi au LLM\n"
                "  • Nuru_Brain — Dual-Write Markdown dans ~/Nuru_Brain/ (compatible Obsidian)\n"
                "  • LongTermMemory — Extraction de faits et stockage structuré (table user_facts)\n"
                "  • Learning Loop — TraceCollector + MiningWorker (analyse patterns d'échec)\n"
                "  • OCR Tesseract — Fallback pour PDF scannés"
            ),
        )

        # ── 2. API de Chat ──
        self._add_section(
            "💬 Pipeline de Chat",
            (
                "Le chat suit un pipeline asynchrone en 7 étapes :\n\n"
                "1. TokenJuice — Compression de la requête utilisateur\n"
                "2. SemanticRouter — Détection d'intention (RAG / COMPLEX / TRIVIAL / WEB)\n"
                "3. RAG Engine — Dual-Query Retrieval (requête originale + réécrite)\n"
                "4. Profile Boost — x2.5 pour les documents personnels de Leblanc\n"
                "5. StrictRAGGuard — Mode HYBRID : RAG d'abord, connaissances générales si pas trouvé\n"
                "6. Génération — Phi-4-mini (local) ou Groq (cloud) selon stratégie\n"
                "7. EvidenceVerifier — Vérification des citations [Source: fichier]"
            ),
            code_block='# Exemple d\'utilisation directe\nimport asyncio\nfrom src.rag_engine import RAGEngine\n\nasync def query():\n    engine = RAGEngine()\n    context, result = await engine.retrieve(\n        "rapport Palabek 2024", k=5\n    )\n    print(f"Score: {result.top_score}")\n    print(f"Documents: {result.documents_found}")\n    for s in result.sources:\n        print(f"  [{s[\'score\']:.2f}] {s[\'name\']}")\n\nasyncio.run(query())',
            extra_content=(
                "Le streaming se fait via InferenceWorker (QThreadPool) qui émet\n"
                "des signaux Qt thread-safe : token_received, rag_data, finished, error.\n"
                "Le score de confiance RAG est affiché dans chaque bulle assistant."
            ),
        )

        # ── 3. API RAG ──
        self._add_section(
            "📚 Moteur RAG — Caractéristiques",
            (
                "Le RAG utilise une combinaison de 4 techniques pour un Recall@5 de 92% :\n\n"
                "1. Dual-Query Retrieval : Embedding de la requête ORIGINALE + RÉÉCRITE,\n"
                "   fusion des résultats avec déduplication par contenu\n\n"
                "2. RRF Fusion : Reciprocal Rank Fusion entre recherche vectorielle\n"
                "   (sqlite-vec, 768d) et recherche lexicale (FTS5 BM25 Porter)\n\n"
                "3. Reranking Systématique : Cross-encoder MiniLM L6 activé dès que\n"
                "   le score > 0.15 (si RAM > 1.5 Go disponible)\n\n"
                "4. Score de Fraîcheur : Bonus de +0.10 pour les chunks indexés\n"
                "   il y a moins de 30 jours\n\n"
                "Paramètres actuels :\n"
                "  • rag_score_threshold: 0.50\n"
                "  • rag_k: 5\n"
                "  • chunk_size: 1200 chars\n"
                "  • overlap_chars: 30-200 selon chunker\n"
                "  • SHORT_DOC_THRESHOLD: 2000 chars"
            ),
            code_block='{\n  "query": "Qui est YARID ?",\n  "results": [\n    {\n      "chunk_id": "c7f3a1b2",\n      "source": "yarid_report_2025.pdf",\n      "score": 0.923,\n      "text": "YARID (Youth Alliance for Refugee...)"\n    }\n  ],\n  "total_chunks": 2,\n  "latency_ms": 145\n}',
            extra_content=(
                "Le stockage vectoriel utilise sqlite-vec (extension SQLite native,\n"
                "zéro dépendance, zéro serveur). Les embeddings sont générés par\n"
                "multilingual-e5-base-mlx (768 dimensions, multilingue FR/EN/Swahili)."
            ),
        )

        # ── 4. API Système ──
        self._add_section(
            "⚙  Configuration & Monitoring",
            (
                "Fichier de configuration : config/settings.yaml\n\n"
                "Paramètres clés modifiables :\n"
                "  • response_mode: strict | hybrid | free\n"
                "  • rag_score_threshold: 0.0 – 1.0 (défaut: 0.50)\n"
                "  • rag_k: 1 – 20 (défaut: 5)\n"
                "  • hybrid_mode: local_only | verify | plan | rag\n"
                "  • cloud_provider: groq | openrouter | deepseek\n"
                "  • cloud_fallback: openrouter/deepseek/deepseek-v4-flash\n\n"
                "Clés API stockées dans macOS Keychain (ne jamais les mettre dans YAML) :\n"
                "  • com.nuru.assistant / groq\n"
                "  • com.nuru.assistant / openrouter\n"
                "  • com.nuru.assistant / gemini"
            ),
            code_block='# État dashboard\nRAM:      3.1G / 8.0G  (39%)\nLLM:      87%\nRAG:      0.92\nTokens:   -52% (TokenJuice)\nTraces:   24 (Learning Loop)',
        )

        # ── 5. Modules & Mémoire ──
        self._add_section(
            "🧠 Modules V6.2",
            (
                "Module TokenJuice — Compression de contexte avant envoi au LLM.\n"
                "  • HTML → Markdown, troncature URLs, dédup lignes\n"
                "  • Économie ~0.5 Go RAM, réduction 40-60% des tokens\n\n"
                "Module Nuru_Brain — Dual-Write Mémoire.\n"
                "  • Chaque chunk RAG écrit dans ~/Nuru_Brain/sources/\n"
                "  • Compatible Obsidian, modification manuelle → ré-indexation auto\n\n"
                "Module Learning Loop — Traces → Mining → Amélioration.\n"
                "  • TraceCollector : enregistre chaque interaction dans SQLite\n"
                "  • MiningWorker : analyse les patterns d'échec (daemon 60s)\n\n"
                "Module LongTermMemory — Mémoire structurée.\n"
                "  • Table user_facts : fact_type, content, confidence, source\n"
                "  • Extraction LLM des conversations via Groq\n"
                "  • Injection automatique dans le contexte avant chaque requête\n\n"
                "Module OCR Tesseract — Fallback pour PDF scannés.\n"
                "  • pytesseract + pdf2image, langues fra+eng\n"
                "  • Activé automatiquement si PyMuPDF extrait < 100 chars"
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
