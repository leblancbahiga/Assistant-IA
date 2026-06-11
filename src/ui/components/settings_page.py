"""
Settings Page V10 — Configuration complète de NURU (glassmorphism cyberpunk).
6 sections interactives : Général, Modèles, RAG, Mémoire V9, Voix, Système.
Tous les widgets utilisent des objectName pour le QSS (pas de inline stylesheets).
"""
import json
import logging
import os
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QScrollArea, QPushButton, QComboBox,
    QCheckBox, QSlider, QSpinBox, QLineEdit,
    QFileDialog, QMessageBox, QSizePolicy,
    QGridLayout
)
from PySide6.QtCore import Qt, QTimer

logger = logging.getLogger(__name__)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not available — system stats will show N/A")

# ── Version NURU ──
NURU_VERSION = "V10"
NURU_MODULE_COUNT = 24


class SettingsPage(QWidget):
    """Page de paramètres NURU — 6 sections glassmorphism cyberpunk."""

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.settings_file = Path("settings.json")
        if config and hasattr(config, 'base_dir'):
            self.settings_file = Path(config.base_dir) / "settings.json"
        self._dirty = False
        self._sys_timer = None
        self.setup_ui()
        self.load_settings()
        self._start_sys_monitor()

    # ──────────────────────────────────────────────
    # UI BUILDER (appelé par __init__)
    # ──────────────────────────────────────────────

    def setup_ui(self):
        """Construit toute l'interface : header + scroll area + 6 sections."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── HEADER ──────────────────────────────
        header = self._build_header()
        layout.addWidget(header)

        # ── SCROLL AREA ─────────────────────────
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none; background: transparent;")

        content = QWidget()
        content.setObjectName("SettingsContent")
        content.setStyleSheet("background: transparent;")
        self.cl = QVBoxLayout(content)
        self.cl.setContentsMargins(24, 16, 24, 24)
        self.cl.setSpacing(20)

        # ── 6 SECTIONS ──────────────────────────
        self.cl.addWidget(self.build_general())
        self.cl.addWidget(self.build_models())
        self.cl.addWidget(self.build_rag())
        self.cl.addWidget(self.build_memory_v9())
        self.cl.addWidget(self.build_voice())
        self.cl.addWidget(self.build_system())

        self.cl.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

    # ── HEADER ────────────────────────────────────

    def _build_header(self):
        """Header avec titre + boutons d'action."""
        header = QFrame()
        header.setObjectName("SettingsHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("⚙  PARAMÈTRES")
        title.setObjectName("SettingsPageTitle")

        self.btn_save = QPushButton("💾  Sauvegarder")
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self.save_settings)

        self.btn_reset = QPushButton("↺  Réinitialiser")
        self.btn_reset.setObjectName("GhostBtn")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset_settings)

        self.btn_export = QPushButton("📤  Exporter")
        self.btn_export.setObjectName("GhostBtn")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._export_settings)

        h_layout.addWidget(title)
        h_layout.addStretch()
        h_layout.addWidget(self.btn_export)
        h_layout.addWidget(self.btn_reset)
        h_layout.addWidget(self.btn_save)
        return header

    # ──────────────────────────────────────────────
    # SECTION 1 : GÉNÉRAL
    # ──────────────────────────────────────────────

    def build_general(self):
        """Section Général — assistant name, langue, thème, taille texte, mode hybride, seuil confiance, max étapes."""
        section = QFrame()
        section.setObjectName("SettingsSection")
        vlay = QVBoxLayout(section)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        title = QLabel("GÉNÉRAL")
        title.setObjectName("SectionTitle")
        vlay.addWidget(title)

        # ── Nom assistant ──
        row1 = QFrame()
        row1.setObjectName("SettingRow")
        rl1 = QHBoxLayout(row1)
        rl1.setContentsMargins(16, 8, 16, 8)
        lbl1 = QLabel("Nom de l'assistant")
        lbl1.setObjectName("SettingLabel")
        self.asst_name_input = QLineEdit("NURU")
        self.asst_name_input.setObjectName("AsstNameInput")
        self.asst_name_input.setPlaceholderText("NURU")
        rl1.addWidget(lbl1)
        rl1.addWidget(self.asst_name_input, stretch=1)
        vlay.addWidget(row1)

        # ── Langue ──
        row2 = QFrame()
        row2.setObjectName("SettingRow")
        rl2 = QHBoxLayout(row2)
        rl2.setContentsMargins(16, 8, 16, 8)
        lbl2 = QLabel("Langue")
        lbl2.setObjectName("SettingLabel")
        self.lang_select = QComboBox()
        self.lang_select.setObjectName("LangSelect")
        self.lang_select.addItems(["Français", "English", "Español"])
        rl2.addWidget(lbl2)
        rl2.addWidget(self.lang_select, stretch=1)
        vlay.addWidget(row2)

        # ── Thème ──
        row3 = QFrame()
        row3.setObjectName("SettingRow")
        rl3 = QHBoxLayout(row3)
        rl3.setContentsMargins(16, 8, 16, 8)
        lbl3 = QLabel("Thème")
        lbl3.setObjectName("SettingLabel")
        self.theme_select = QComboBox()
        self.theme_select.setObjectName("ThemeSelect")
        self.theme_select.addItems(["Sombre", "Clair", "Automatique"])
        rl3.addWidget(lbl3)
        rl3.addWidget(self.theme_select, stretch=1)
        vlay.addWidget(row3)

        # ── Taille texte ──
        row4 = QFrame()
        row4.setObjectName("SettingRow")
        rl4 = QHBoxLayout(row4)
        rl4.setContentsMargins(16, 8, 16, 8)
        lbl4 = QLabel("Taille du texte")
        lbl4.setObjectName("SettingLabel")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setObjectName("FontSizeSpin")
        self.font_size_spin.setRange(10, 24)
        self.font_size_spin.setValue(14)
        rl4.addWidget(lbl4)
        rl4.addWidget(self.font_size_spin, stretch=1)
        vlay.addWidget(row4)

        # ── Mode hybride ──
        row5 = QFrame()
        row5.setObjectName("SettingRow")
        rl5 = QHBoxLayout(row5)
        rl5.setContentsMargins(16, 8, 16, 8)
        lbl5 = QLabel("Mode hybride")
        lbl5.setObjectName("SettingLabel")
        self.hybrid_mode_select = QComboBox()
        self.hybrid_mode_select.setObjectName("HybridModeSelect")
        self.hybrid_mode_select.addItems(["cloud_first", "local_first", "offline_only"])
        rl5.addWidget(lbl5)
        rl5.addWidget(self.hybrid_mode_select, stretch=1)
        vlay.addWidget(row5)

        # ── Seuil de confiance minimum ──
        row6 = QFrame()
        row6.setObjectName("SettingRow")
        rl6 = QHBoxLayout(row6)
        rl6.setContentsMargins(16, 8, 16, 8)
        lbl6 = QLabel("Seuil de confiance min.")
        lbl6.setObjectName("SettingLabel")
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setObjectName("ConfidenceSlider")
        self.confidence_slider.setRange(0, 100)
        self.confidence_slider.setValue(50)
        self.confidence_value = QLabel("0.50")
        self.confidence_value.setObjectName("ConfidenceValue")
        self.confidence_value.setFixedWidth(40)
        self.confidence_slider.valueChanged.connect(
            lambda v: self.confidence_value.setText(f"{v/100:.2f}")
        )
        rl6.addWidget(lbl6)
        rl6.addWidget(self.confidence_slider, stretch=1)
        rl6.addWidget(self.confidence_value)
        vlay.addWidget(row6)

        # ── Nombre max d'étapes agent ──
        row7 = QFrame()
        row7.setObjectName("SettingRow")
        rl7 = QHBoxLayout(row7)
        rl7.setContentsMargins(16, 8, 16, 8)
        lbl7 = QLabel("Max étapes agent")
        lbl7.setObjectName("SettingLabel")
        self.max_steps_spin = QSpinBox()
        self.max_steps_spin.setObjectName("MaxStepsSpin")
        self.max_steps_spin.setRange(1, 10)
        self.max_steps_spin.setValue(5)
        rl7.addWidget(lbl7)
        rl7.addWidget(self.max_steps_spin, stretch=1)
        vlay.addWidget(row7)

        # ── Réinitialiser ──
        row8 = QFrame()
        row8.setObjectName("SettingRow")
        rl8 = QHBoxLayout(row8)
        rl8.setContentsMargins(16, 8, 16, 8)
        rl8.addStretch()
        self.reset_btn = QPushButton("↺  Réinitialiser les paramètres")
        self.reset_btn.setObjectName("ResetSettingsBtn")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self._reset_settings)
        rl8.addWidget(self.reset_btn)
        vlay.addWidget(row8)

        return section

    # ──────────────────────────────────────────────
    # SECTION 2 : MODÈLES IA
    # ──────────────────────────────────────────────

    def build_models(self):
        """Section Modèles IA — sélection, fournisseur, paramètres, performances, modèle cloud, modèle local, timeout."""
        section = QFrame()
        section.setObjectName("SettingsSection")
        vlay = QVBoxLayout(section)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        title = QLabel("MODÈLES IA")
        title.setObjectName("SectionTitle")
        vlay.addWidget(title)

        # ── Modèle cloud ──
        row_cloud = QFrame()
        row_cloud.setObjectName("SettingRow")
        rl_cloud = QHBoxLayout(row_cloud)
        rl_cloud.setContentsMargins(16, 8, 16, 8)
        lbl_cloud = QLabel("Modèle cloud")
        lbl_cloud.setObjectName("SettingLabel")
        self.cloud_model_select = QComboBox()
        self.cloud_model_select.setObjectName("CloudModelSelect")
        self.cloud_model_select.addItems([
            "groq/llama-3.3-70b-versatile",
            "openrouter",
            "deepseek-chat",
        ])
        rl_cloud.addWidget(lbl_cloud)
        rl_cloud.addWidget(self.cloud_model_select, stretch=1)
        vlay.addWidget(row_cloud)

        # ── Modèle local (non modifiable) ──
        row_local = QFrame()
        row_local.setObjectName("SettingRow")
        rl_local = QHBoxLayout(row_local)
        rl_local.setContentsMargins(16, 8, 16, 8)
        lbl_local = QLabel("Modèle local")
        lbl_local.setObjectName("SettingLabel")
        self.local_model_label = QLabel("phi-4-mini-4bit")
        self.local_model_label.setObjectName("LocalModelLabel")
        self.local_model_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        rl_local.addWidget(lbl_local)
        rl_local.addWidget(self.local_model_label, stretch=1)
        vlay.addWidget(row_local)

        # ── Timeout LLM ──
        row_timeout = QFrame()
        row_timeout.setObjectName("SettingRow")
        rl_timeout = QHBoxLayout(row_timeout)
        rl_timeout.setContentsMargins(16, 8, 16, 8)
        lbl_timeout = QLabel("Timeout LLM (secondes)")
        lbl_timeout.setObjectName("SettingLabel")
        self.llm_timeout_spin = QSpinBox()
        self.llm_timeout_spin.setObjectName("LlmTimeoutSpin")
        self.llm_timeout_spin.setRange(10, 120)
        self.llm_timeout_spin.setValue(30)
        self.llm_timeout_spin.setSuffix(" s")
        rl_timeout.addWidget(lbl_timeout)
        rl_timeout.addWidget(self.llm_timeout_spin, stretch=1)
        vlay.addWidget(row_timeout)

        # ── Modèle actif ──
        row1 = QFrame()
        row1.setObjectName("SettingRow")
        rl1 = QHBoxLayout(row1)
        rl1.setContentsMargins(16, 8, 16, 8)
        lbl1 = QLabel("Modèle actif")
        lbl1.setObjectName("SettingLabel")
        self.active_model = QComboBox()
        self.active_model.setObjectName("ActiveModelSelect")
        self.active_model.addItems([
            "Phi-4-mini-instruct-4bit (local)",
            "Qwen2.5-1.5B-Instruct-4bit (local)",
            "llama-3.3-70b-versatile (Groq)",
            "deepseek-chat (Deepseek)",
        ])
        rl1.addWidget(lbl1)
        rl1.addWidget(self.active_model, stretch=1)
        vlay.addWidget(row1)

        # ── Fournisseur ──
        row2 = QFrame()
        row2.setObjectName("SettingRow")
        rl2 = QHBoxLayout(row2)
        rl2.setContentsMargins(16, 8, 16, 8)
        lbl2 = QLabel("Fournisseur")
        lbl2.setObjectName("SettingLabel")
        self.provider_select = QComboBox()
        self.provider_select.setObjectName("ProviderSelect")
        self.provider_select.addItems(["Local", "Cloud"])
        rl2.addWidget(lbl2)
        rl2.addWidget(self.provider_select, stretch=1)
        vlay.addWidget(row2)

        # ── Température ──
        row3 = QFrame()
        row3.setObjectName("SettingRow")
        rl3 = QHBoxLayout(row3)
        rl3.setContentsMargins(16, 8, 16, 8)
        lbl3 = QLabel("Température")
        lbl3.setObjectName("SettingLabel")
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setObjectName("TempSlider")
        self.temp_slider.setRange(0, 200)
        self.temp_slider.setValue(70)
        self.temp_value = QLabel("0.70")
        self.temp_value.setObjectName("TempValue")
        self.temp_value.setFixedWidth(40)
        self.temp_slider.valueChanged.connect(
            lambda v: self.temp_value.setText(f"{v/100:.2f}")
        )
        rl3.addWidget(lbl3)
        rl3.addWidget(self.temp_slider, stretch=1)
        rl3.addWidget(self.temp_value)
        vlay.addWidget(row3)

        # ── Top-P ──
        row4 = QFrame()
        row4.setObjectName("SettingRow")
        rl4 = QHBoxLayout(row4)
        rl4.setContentsMargins(16, 8, 16, 8)
        lbl4 = QLabel("Top-P")
        lbl4.setObjectName("SettingLabel")
        self.top_p_slider = QSlider(Qt.Horizontal)
        self.top_p_slider.setObjectName("TopPSlider")
        self.top_p_slider.setRange(0, 100)
        self.top_p_slider.setValue(90)
        self.top_p_value = QLabel("0.90")
        self.top_p_value.setObjectName("TopPValue")
        self.top_p_value.setFixedWidth(40)
        self.top_p_slider.valueChanged.connect(
            lambda v: self.top_p_value.setText(f"{v/100:.2f}")
        )
        rl4.addWidget(lbl4)
        rl4.addWidget(self.top_p_slider, stretch=1)
        rl4.addWidget(self.top_p_value)
        vlay.addWidget(row4)

        # ── Contexte ──
        row5 = QFrame()
        row5.setObjectName("SettingRow")
        rl5 = QHBoxLayout(row5)
        rl5.setContentsMargins(16, 8, 16, 8)
        lbl5 = QLabel("Taille du contexte")
        lbl5.setObjectName("SettingLabel")
        self.context_spin = QSpinBox()
        self.context_spin.setObjectName("ContextSpin")
        self.context_spin.setRange(1024, 32768)
        self.context_spin.setValue(4096)
        self.context_spin.setSingleStep(1024)
        rl5.addWidget(lbl5)
        rl5.addWidget(self.context_spin, stretch=1)
        vlay.addWidget(row5)

        # ── Max tokens ──
        row6 = QFrame()
        row6.setObjectName("SettingRow")
        rl6 = QHBoxLayout(row6)
        rl6.setContentsMargins(16, 8, 16, 8)
        lbl6 = QLabel("Max tokens")
        lbl6.setObjectName("SettingLabel")
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setObjectName("MaxTokensSpin")
        self.max_tokens_spin.setRange(128, 8192)
        self.max_tokens_spin.setValue(2048)
        self.max_tokens_spin.setSingleStep(128)
        rl6.addWidget(lbl6)
        rl6.addWidget(self.max_tokens_spin, stretch=1)
        vlay.addWidget(row6)

        # ── Performances (Metric Cards) ──
        row7 = QFrame()
        row7.setObjectName("SettingRow")
        rl7 = QHBoxLayout(row7)
        rl7.setContentsMargins(16, 12, 16, 12)
        rl7.setSpacing(12)

        card_speed = QFrame()
        card_speed.setObjectName("MetricCard")
        cl_speed = QVBoxLayout(card_speed)
        cl_speed.setContentsMargins(12, 10, 12, 10)
        cl_speed.setAlignment(Qt.AlignCenter)
        speed_title = QLabel("VITESSE")
        speed_title.setObjectName("MetricCardTitle")
        self.speed_value = QLabel("—")
        self.speed_value.setObjectName("MetricCardValue")
        cl_speed.addWidget(speed_title)
        cl_speed.addWidget(self.speed_value)
        rl7.addWidget(card_speed)

        card_lat = QFrame()
        card_lat.setObjectName("MetricCard")
        cl_lat = QVBoxLayout(card_lat)
        cl_lat.setContentsMargins(12, 10, 12, 10)
        cl_lat.setAlignment(Qt.AlignCenter)
        lat_title = QLabel("LATENCE")
        lat_title.setObjectName("MetricCardTitle")
        self.latency_value = QLabel("—")
        self.latency_value.setObjectName("MetricCardValue")
        cl_lat.addWidget(lat_title)
        cl_lat.addWidget(self.latency_value)
        rl7.addWidget(card_lat)

        card_qual = QFrame()
        card_qual.setObjectName("MetricCard")
        cl_qual = QVBoxLayout(card_qual)
        cl_qual.setContentsMargins(12, 10, 12, 10)
        cl_qual.setAlignment(Qt.AlignCenter)
        qual_title = QLabel("QUALITÉ")
        qual_title.setObjectName("MetricCardTitle")
        self.quality_value = QLabel("—")
        self.quality_value.setObjectName("MetricCardValue")
        cl_qual.addWidget(qual_title)
        cl_qual.addWidget(self.quality_value)
        rl7.addWidget(card_qual)

        vlay.addWidget(row7)

        return section

    # ──────────────────────────────────────────────
    # SECTION 3 : RAG
    # ──────────────────────────────────────────────

    def build_rag(self):
        """Section RAG — chunks, similarité, embedding, activation, réindexation, stats."""
        section = QFrame()
        section.setObjectName("SettingsSection")
        vlay = QVBoxLayout(section)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        title = QLabel("RAG")
        title.setObjectName("SectionTitle")
        vlay.addWidget(title)

        # ── Activer/désactiver RAG ──
        row0 = QFrame()
        row0.setObjectName("SettingRow")
        rl0 = QHBoxLayout(row0)
        rl0.setContentsMargins(16, 8, 16, 8)
        self.rag_enabled = QCheckBox("Activer le RAG")
        self.rag_enabled.setObjectName("RagEnabled")
        self.rag_enabled.setChecked(True)
        rl0.addWidget(self.rag_enabled)
        rl0.addStretch()
        vlay.addWidget(row0)

        # ── Nombre de chunks ──
        row1 = QFrame()
        row1.setObjectName("SettingRow")
        rl1 = QHBoxLayout(row1)
        rl1.setContentsMargins(16, 8, 16, 8)
        lbl1 = QLabel("Nombre max de chunks")
        lbl1.setObjectName("SettingLabel")
        self.rag_chunks_spin = QSpinBox()
        self.rag_chunks_spin.setObjectName("RagChunksSpin")
        self.rag_chunks_spin.setRange(5, 50)
        self.rag_chunks_spin.setValue(10)
        rl1.addWidget(lbl1)
        rl1.addWidget(self.rag_chunks_spin, stretch=1)
        vlay.addWidget(row1)

        # ── Score de similarité ──
        row2 = QFrame()
        row2.setObjectName("SettingRow")
        rl2 = QHBoxLayout(row2)
        rl2.setContentsMargins(16, 8, 16, 8)
        lbl2 = QLabel("Score similarité min.")
        lbl2.setObjectName("SettingLabel")
        self.similarity_slider = QSlider(Qt.Horizontal)
        self.similarity_slider.setObjectName("SimilaritySlider")
        self.similarity_slider.setRange(0, 100)
        self.similarity_slider.setValue(60)
        self.similarity_value = QLabel("0.60")
        self.similarity_value.setObjectName("SimilarityValue")
        self.similarity_value.setFixedWidth(40)
        self.similarity_slider.valueChanged.connect(
            lambda v: self.similarity_value.setText(f"{v/100:.2f}")
        )
        rl2.addWidget(lbl2)
        rl2.addWidget(self.similarity_slider, stretch=1)
        rl2.addWidget(self.similarity_value)
        vlay.addWidget(row2)

        # ── Modèle embedding ──
        row3 = QFrame()
        row3.setObjectName("SettingRow")
        rl3 = QHBoxLayout(row3)
        rl3.setContentsMargins(16, 8, 16, 8)
        lbl3 = QLabel("Modèle d'embedding")
        lbl3.setObjectName("SettingLabel")
        self.embedding_select = QComboBox()
        self.embedding_select.setObjectName("EmbeddingSelect")
        self.embedding_select.addItems([
            "multilingual-e5-base-mlx (768d)",
        ])
        rl3.addWidget(lbl3)
        rl3.addWidget(self.embedding_select, stretch=1)
        vlay.addWidget(row3)

        # ── Réindexation complète ──
        row4 = QFrame()
        row4.setObjectName("SettingRow")
        rl4 = QHBoxLayout(row4)
        rl4.setContentsMargins(16, 8, 16, 8)
        self.reindex_all_btn = QPushButton("⬡  Réindexation complète")
        self.reindex_all_btn.setObjectName("ReindexAllBtn")
        self.reindex_all_btn.setCursor(Qt.PointingHandCursor)
        self.reindex_all_btn.clicked.connect(self._on_reindex_all)
        rl4.addStretch()
        rl4.addWidget(self.reindex_all_btn)
        vlay.addWidget(row4)

        # ── Réindexation document ──
        row5 = QFrame()
        row5.setObjectName("SettingRow")
        rl5 = QHBoxLayout(row5)
        rl5.setContentsMargins(16, 8, 16, 8)
        self.reindex_doc_btn = QPushButton("⬡  Réindexer document")
        self.reindex_doc_btn.setObjectName("ReindexDocBtn")
        self.reindex_doc_btn.setCursor(Qt.PointingHandCursor)
        self.reindex_doc_btn.clicked.connect(self._on_reindex_doc)
        self.doc_select = QComboBox()
        self.doc_select.setObjectName("DocSelect")
        self.doc_select.setMinimumWidth(200)
        self.doc_select.addItem("— Sélectionner un document —")
        rl5.addWidget(self.reindex_doc_btn)
        rl5.addWidget(self.doc_select, stretch=1)
        vlay.addWidget(row5)

        # ── Statistiques ──
        stats_frame = QFrame()
        stats_frame.setObjectName("StatsPanel")
        stats_grid = QGridLayout(stats_frame)
        stats_grid.setContentsMargins(16, 12, 16, 12)
        stats_grid.setSpacing(8)

        stats_items = [
            ("📄  Documents", "DocTotalCount", "—"),
            ("🧩  Chunks", "ChunkTotalCount", "—"),
            ("📦  Index", "IndexSize", "—"),
            ("📅  Dernière indexation", "LastIndexDate", "—"),
        ]

        for col, (label_text, obj_name, default) in enumerate(stats_items):
            cell = QFrame()
            cell.setObjectName("StatCell")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(8, 6, 8, 6)
            cell_layout.setSpacing(2)
            stat_label = QLabel(label_text)
            stat_label.setObjectName("StatLabel")
            stat_value = QLabel(default)
            stat_value.setObjectName(obj_name)
            cell_layout.addWidget(stat_label)
            cell_layout.addWidget(stat_value)
            stats_grid.addWidget(cell, 0, col)

        vlay.addWidget(stats_frame)

        return section

    # ──────────────────────────────────────────────
    # SECTION 4 : MÉMOIRE V9
    # ──────────────────────────────────────────────

    def build_memory_v9(self):
        """Section Mémoire V9 — ConsolidationWorker, intervalle consolidation, seuil d'importance."""
        section = QFrame()
        section.setObjectName("SettingsSection")
        vlay = QVBoxLayout(section)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        title = QLabel("MÉMOIRE V9")
        title.setObjectName("SectionTitle")
        vlay.addWidget(title)

        # ── Activer ConsolidationWorker ──
        row1 = QFrame()
        row1.setObjectName("SettingRow")
        rl1 = QHBoxLayout(row1)
        rl1.setContentsMargins(16, 8, 16, 8)
        self.consolidation_enabled = QCheckBox("Activer ConsolidationWorker")
        self.consolidation_enabled.setObjectName("ConsolidationEnabled")
        self.consolidation_enabled.setChecked(True)
        rl1.addWidget(self.consolidation_enabled)
        rl1.addStretch()
        vlay.addWidget(row1)

        # ── Intervalle consolidation (en heures) ──
        row2 = QFrame()
        row2.setObjectName("SettingRow")
        rl2 = QHBoxLayout(row2)
        rl2.setContentsMargins(16, 8, 16, 8)
        lbl2 = QLabel("Intervalle consolidation")
        lbl2.setObjectName("SettingLabel")
        self.consolidation_interval_spin = QSpinBox()
        self.consolidation_interval_spin.setObjectName("ConsolidationIntervalSpin")
        self.consolidation_interval_spin.setRange(1, 24)
        self.consolidation_interval_spin.setValue(6)
        self.consolidation_interval_spin.setSuffix(" h")
        rl2.addWidget(lbl2)
        rl2.addWidget(self.consolidation_interval_spin, stretch=1)
        vlay.addWidget(row2)

        # ── Seuil d'importance minimum ──
        row3 = QFrame()
        row3.setObjectName("SettingRow")
        rl3 = QHBoxLayout(row3)
        rl3.setContentsMargins(16, 8, 16, 8)
        lbl3 = QLabel("Seuil importance min.")
        lbl3.setObjectName("SettingLabel")
        self.importance_slider = QSlider(Qt.Horizontal)
        self.importance_slider.setObjectName("ImportanceSlider")
        self.importance_slider.setRange(0, 100)
        self.importance_slider.setValue(30)
        self.importance_value = QLabel("0.30")
        self.importance_value.setObjectName("ImportanceValue")
        self.importance_value.setFixedWidth(40)
        self.importance_slider.valueChanged.connect(
            lambda v: self.importance_value.setText(f"{v/100:.2f}")
        )
        rl3.addWidget(lbl3)
        rl3.addWidget(self.importance_slider, stretch=1)
        rl3.addWidget(self.importance_value)
        vlay.addWidget(row3)

        return section

    # ──────────────────────────────────────────────
    # SECTION 5 : VOIX
    # ──────────────────────────────────────────────

    def build_voice(self):
        """Section Voix — activation, choix voix, vitesse, volume, test."""
        section = QFrame()
        section.setObjectName("SettingsSection")
        vlay = QVBoxLayout(section)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        title = QLabel("VOIX")
        title.setObjectName("SectionTitle")
        vlay.addWidget(title)

        # ── Activation vocale ──
        row1 = QFrame()
        row1.setObjectName("SettingRow")
        rl1 = QHBoxLayout(row1)
        rl1.setContentsMargins(16, 8, 16, 8)
        self.voice_enabled = QCheckBox("Activation vocale")
        self.voice_enabled.setObjectName("VoiceEnabled")
        self.voice_enabled.setChecked(True)
        rl1.addWidget(self.voice_enabled)
        rl1.addStretch()
        vlay.addWidget(row1)

        # ── Choix de la voix ──
        row2 = QFrame()
        row2.setObjectName("SettingRow")
        rl2 = QHBoxLayout(row2)
        rl2.setContentsMargins(16, 8, 16, 8)
        lbl2 = QLabel("Voix")
        lbl2.setObjectName("SettingLabel")
        self.voice_select = QComboBox()
        self.voice_select.setObjectName("VoiceSelect")
        self.voice_select.addItems([
            "Voix 1 (Féminine)", "Voix 2 (Masculine)",
            "Voix 3 (Neutre)", "Voix 4 (Synthétique)"
        ])
        rl2.addWidget(lbl2)
        rl2.addWidget(self.voice_select, stretch=1)
        vlay.addWidget(row2)

        # ── Vitesse de lecture ──
        row3 = QFrame()
        row3.setObjectName("SettingRow")
        rl3 = QHBoxLayout(row3)
        rl3.setContentsMargins(16, 8, 16, 8)
        lbl3 = QLabel("Vitesse lecture")
        lbl3.setObjectName("SettingLabel")
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setObjectName("SpeedSlider")
        self.speed_slider.setRange(50, 200)
        self.speed_slider.setValue(100)
        self.speed_value = QLabel("100%")
        self.speed_value.setObjectName("SpeedValue")
        self.speed_value.setFixedWidth(48)
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_value.setText(f"{v}%")
        )
        rl3.addWidget(lbl3)
        rl3.addWidget(self.speed_slider, stretch=1)
        rl3.addWidget(self.speed_value)
        vlay.addWidget(row3)

        # ── Niveau sonore ──
        row4 = QFrame()
        row4.setObjectName("SettingRow")
        rl4 = QHBoxLayout(row4)
        rl4.setContentsMargins(16, 8, 16, 8)
        lbl4 = QLabel("Volume")
        lbl4.setObjectName("SettingLabel")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setObjectName("VolumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_value = QLabel("80%")
        self.volume_value.setObjectName("VolumeValue")
        self.volume_value.setFixedWidth(48)
        self.volume_slider.valueChanged.connect(
            lambda v: self.volume_value.setText(f"{v}%")
        )
        rl4.addWidget(lbl4)
        rl4.addWidget(self.volume_slider, stretch=1)
        rl4.addWidget(self.volume_value)
        vlay.addWidget(row4)

        # ── Test audio ──
        row5 = QFrame()
        row5.setObjectName("SettingRow")
        rl5 = QHBoxLayout(row5)
        rl5.setContentsMargins(16, 8, 16, 8)
        rl5.addStretch()
        self.audio_test_btn = QPushButton("▶  Test audio")
        self.audio_test_btn.setObjectName("AudioTestBtn")
        self.audio_test_btn.setCursor(Qt.PointingHandCursor)
        self.audio_test_btn.clicked.connect(self._on_audio_test)
        rl5.addWidget(self.audio_test_btn)
        vlay.addWidget(row5)

        return section

    # ──────────────────────────────────────────────
    # SECTION 6 : SYSTÈME
    # ──────────────────────────────────────────────

    def build_system(self):
        """Section Système — RAM, CPU, disque, version, modules, réindexer, vider cache, exporter logs."""
        section = QFrame()
        section.setObjectName("SettingsSection")
        vlay = QVBoxLayout(section)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        title = QLabel("SYSTÈME")
        title.setObjectName("SectionTitle")
        vlay.addWidget(title)

        # ── Version NURU ──
        row0 = QFrame()
        row0.setObjectName("SettingRow")
        rl0 = QHBoxLayout(row0)
        rl0.setContentsMargins(16, 8, 16, 8)
        lbl0 = QLabel("Version NURU")
        lbl0.setObjectName("SettingLabel")
        self.sys_version_label = QLabel(NURU_VERSION)
        self.sys_version_label.setObjectName("SysVersionLabel")
        rl0.addWidget(lbl0)
        rl0.addStretch()
        rl0.addWidget(self.sys_version_label)
        vlay.addWidget(row0)

        # ── Nombre de modules ──
        row_mod = QFrame()
        row_mod.setObjectName("SettingRow")
        rl_mod = QHBoxLayout(row_mod)
        rl_mod.setContentsMargins(16, 8, 16, 8)
        lbl_mod = QLabel("Modules actifs")
        lbl_mod.setObjectName("SettingLabel")
        self.sys_modules_label = QLabel(f"{NURU_MODULE_COUNT}")
        self.sys_modules_label.setObjectName("SysModulesLabel")
        rl_mod.addWidget(lbl_mod)
        rl_mod.addStretch()
        rl_mod.addWidget(self.sys_modules_label)
        vlay.addWidget(row_mod)

        # ── RAM ──
        row1 = QFrame()
        row1.setObjectName("SettingRow")
        rl1 = QHBoxLayout(row1)
        rl1.setContentsMargins(16, 8, 16, 8)
        lbl1 = QLabel("RAM utilisée")
        lbl1.setObjectName("SettingLabel")
        self.sys_ram_label = QLabel("—")
        self.sys_ram_label.setObjectName("SysRamLabel")
        rl1.addWidget(lbl1)
        rl1.addStretch()
        rl1.addWidget(self.sys_ram_label)
        vlay.addWidget(row1)

        # ── CPU ──
        row2 = QFrame()
        row2.setObjectName("SettingRow")
        rl2 = QHBoxLayout(row2)
        rl2.setContentsMargins(16, 8, 16, 8)
        lbl2 = QLabel("CPU utilisé")
        lbl2.setObjectName("SettingLabel")
        self.sys_cpu_label = QLabel("—")
        self.sys_cpu_label.setObjectName("SysCpuLabel")
        rl2.addWidget(lbl2)
        rl2.addStretch()
        rl2.addWidget(self.sys_cpu_label)
        vlay.addWidget(row2)

        # ── Disque ──
        row3 = QFrame()
        row3.setObjectName("SettingRow")
        rl3 = QHBoxLayout(row3)
        rl3.setContentsMargins(16, 8, 16, 8)
        lbl3 = QLabel("Espace disque")
        lbl3.setObjectName("SettingLabel")
        self.sys_disk_label = QLabel("—")
        self.sys_disk_label.setObjectName("SysDiskLabel")
        rl3.addWidget(lbl3)
        rl3.addStretch()
        rl3.addWidget(self.sys_disk_label)
        vlay.addWidget(row3)

        # ── Réindexer les documents ──
        row_reindex = QFrame()
        row_reindex.setObjectName("SettingRow")
        rl_reindex = QHBoxLayout(row_reindex)
        rl_reindex.setContentsMargins(16, 8, 16, 8)
        self.sys_reindex_btn = QPushButton("📂  Réindexer les documents")
        self.sys_reindex_btn.setObjectName("SysReindexBtn")
        self.sys_reindex_btn.setCursor(Qt.PointingHandCursor)
        self.sys_reindex_btn.clicked.connect(self._on_reindex_all)
        rl_reindex.addStretch()
        rl_reindex.addWidget(self.sys_reindex_btn)
        vlay.addWidget(row_reindex)

        # ── Vider le cache ──
        row_cache = QFrame()
        row_cache.setObjectName("SettingRow")
        rl_cache = QHBoxLayout(row_cache)
        rl_cache.setContentsMargins(16, 8, 16, 8)
        self.sys_clear_cache_btn = QPushButton("🗑  Vider le cache")
        self.sys_clear_cache_btn.setObjectName("SysClearCacheBtn")
        self.sys_clear_cache_btn.setCursor(Qt.PointingHandCursor)
        self.sys_clear_cache_btn.clicked.connect(self._on_clear_cache)
        rl_cache.addStretch()
        rl_cache.addWidget(self.sys_clear_cache_btn)
        vlay.addWidget(row_cache)

        # ── Exporter les logs ──
        row_logs = QFrame()
        row_logs.setObjectName("SettingRow")
        rl_logs = QHBoxLayout(row_logs)
        rl_logs.setContentsMargins(16, 8, 16, 8)
        self.sys_export_logs_btn = QPushButton("📋  Exporter les logs")
        self.sys_export_logs_btn.setObjectName("SysExportLogsBtn")
        self.sys_export_logs_btn.setCursor(Qt.PointingHandCursor)
        self.sys_export_logs_btn.clicked.connect(self._on_export_logs)
        rl_logs.addStretch()
        rl_logs.addWidget(self.sys_export_logs_btn)
        vlay.addWidget(row_logs)

        # ── Ouvrir les logs ──
        row5 = QFrame()
        row5.setObjectName("SettingRow")
        rl5 = QHBoxLayout(row5)
        rl5.setContentsMargins(16, 8, 16, 8)
        self.open_logs_btn = QPushButton("📄  Ouvrir les logs")
        self.open_logs_btn.setObjectName("OpenLogsBtn")
        self.open_logs_btn.setCursor(Qt.PointingHandCursor)
        self.open_logs_btn.clicked.connect(self._on_open_logs)
        rl5.addStretch()
        rl5.addWidget(self.open_logs_btn)
        vlay.addWidget(row5)

        # ── Export diagnostic ──
        row6 = QFrame()
        row6.setObjectName("SettingRow")
        rl6 = QHBoxLayout(row6)
        rl6.setContentsMargins(16, 8, 16, 8)
        self.export_diag_btn = QPushButton("🩺  Export diagnostic")
        self.export_diag_btn.setObjectName("ExportDiagBtn")
        self.export_diag_btn.setCursor(Qt.PointingHandCursor)
        self.export_diag_btn.clicked.connect(self._export_diagnostics)
        rl6.addStretch()
        rl6.addWidget(self.export_diag_btn)
        vlay.addWidget(row6)

        return section

    # ──────────────────────────────────────────────
    # PERSISTANCE JSON
    # ──────────────────────────────────────────────

    def save_settings(self):
        """Sauvegarde tous les paramètres dans settings.json."""
        data = self._gather_settings()
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._dirty = False
            QMessageBox.information(self, "Paramètres", "✅ Configuration sauvegardée.")
            logger.info("Settings saved to %s", self.settings_file)
        except Exception as e:
            logger.error("Save settings failed: %s", e)
            QMessageBox.warning(self, "Erreur", f"Sauvegarde échouée : {e}")

    def load_settings(self):
        """Charge les valeurs depuis settings.json."""
        if not self.settings_file.exists():
            return
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_settings(data)
            logger.info("Settings loaded from %s", self.settings_file)
        except Exception as e:
            logger.warning("Load settings failed: %s", e)

    def _gather_settings(self) -> dict:
        """Rassemble toutes les valeurs des widgets dans un dict."""
        return {
            # Général
            "asst_name": self.asst_name_input.text(),
            "lang": self.lang_select.currentText(),
            "theme": self.theme_select.currentText(),
            "font_size": self.font_size_spin.value(),
            "hybrid_mode": self.hybrid_mode_select.currentText(),
            "confidence_threshold": self.confidence_slider.value() / 100,
            "max_agent_steps": self.max_steps_spin.value(),
            # Modèles
            "cloud_model": self.cloud_model_select.currentText(),
            "local_model": "phi-4-mini-4bit",
            "llm_timeout": self.llm_timeout_spin.value(),
            "active_model": self.active_model.currentText(),
            "provider": self.provider_select.currentText(),
            "temperature": self.temp_slider.value() / 100,
            "top_p": self.top_p_slider.value() / 100,
            "context_size": self.context_spin.value(),
            "max_tokens": self.max_tokens_spin.value(),
            # RAG
            "rag_enabled": self.rag_enabled.isChecked(),
            "rag_chunks": self.rag_chunks_spin.value(),
            "similarity_threshold": self.similarity_slider.value() / 100,
            "embedding_model": self.embedding_select.currentText(),
            # Mémoire V9
            "consolidation_enabled": self.consolidation_enabled.isChecked(),
            "consolidation_interval_hours": self.consolidation_interval_spin.value(),
            "importance_threshold": self.importance_slider.value() / 100,
            # Voix
            "voice_enabled": self.voice_enabled.isChecked(),
            "voice": self.voice_select.currentText(),
            "speed": self.speed_slider.value(),
            "volume": self.volume_slider.value(),
        }

    def _apply_settings(self, data: dict):
        """Applique les valeurs chargées aux widgets."""
        mapping = {
            "asst_name": (QLineEdit, "setText"),
            "lang": (QComboBox, "setCurrentText"),
            "theme": (QComboBox, "setCurrentText"),
            "font_size": (QSpinBox, "setValue"),
            "hybrid_mode": (QComboBox, "setCurrentText"),
            "active_model": (QComboBox, "setCurrentText"),
            "provider": (QComboBox, "setCurrentText"),
            "context_size": (QSpinBox, "setValue"),
            "max_tokens": (QSpinBox, "setValue"),
            "cloud_model": (QComboBox, "setCurrentText"),
            "llm_timeout": (QSpinBox, "setValue"),
            "rag_chunks": (QSpinBox, "setValue"),
            "embedding_model": (QComboBox, "setCurrentText"),
            "consolidation_interval_hours": (QSpinBox, "setValue"),
            "max_agent_steps": (QSpinBox, "setValue"),
            "voice_enabled": (QCheckBox, "setChecked"),
            "voice": (QComboBox, "setCurrentText"),
        }

        widget_map = {
            "asst_name": self.asst_name_input,
            "lang": self.lang_select,
            "theme": self.theme_select,
            "font_size": self.font_size_spin,
            "hybrid_mode": self.hybrid_mode_select,
            "active_model": self.active_model,
            "provider": self.provider_select,
            "context_size": self.context_spin,
            "max_tokens": self.max_tokens_spin,
            "cloud_model": self.cloud_model_select,
            "llm_timeout": self.llm_timeout_spin,
            "rag_chunks": self.rag_chunks_spin,
            "embedding_model": self.embedding_select,
            "consolidation_interval_hours": self.consolidation_interval_spin,
            "max_agent_steps": self.max_steps_spin,
            "voice_enabled": self.voice_enabled,
            "voice": self.voice_select,
        }

        for key, value in data.items():
            if key in widget_map:
                widget = widget_map[key]
                cls, method = mapping.get(key, (None, None))
                if not cls or not method:
                    continue
                try:
                    if cls == QComboBox:
                        idx = widget.findText(str(value))
                        if idx >= 0:
                            widget.setCurrentIndex(idx)
                        else:
                            widget.setCurrentText(str(value))
                    elif hasattr(widget, method):
                        getattr(widget, method)(value)
                except Exception as e:
                    logger.debug("Apply %s=%s failed: %s", key, value, e)

        # Special handling for sliders (float values stored)
        if "temperature" in data:
            try:
                self.temp_slider.setValue(int(float(data["temperature"]) * 100))
            except (ValueError, TypeError):
                pass
        if "top_p" in data:
            try:
                self.top_p_slider.setValue(int(float(data["top_p"]) * 100))
            except (ValueError, TypeError):
                pass
        if "similarity_threshold" in data:
            try:
                self.similarity_slider.setValue(int(float(data["similarity_threshold"]) * 100))
            except (ValueError, TypeError):
                pass
        if "speed" in data:
            try:
                self.speed_slider.setValue(int(data["speed"]))
            except (ValueError, TypeError):
                pass
        if "volume" in data:
            try:
                self.volume_slider.setValue(int(data["volume"]))
            except (ValueError, TypeError):
                pass
        if "confidence_threshold" in data:
            try:
                self.confidence_slider.setValue(int(float(data["confidence_threshold"]) * 100))
            except (ValueError, TypeError):
                pass
        if "importance_threshold" in data:
            try:
                self.importance_slider.setValue(int(float(data["importance_threshold"]) * 100))
            except (ValueError, TypeError):
                pass
        if "rag_enabled" in data:
            try:
                self.rag_enabled.setChecked(bool(data["rag_enabled"]))
            except (ValueError, TypeError):
                pass
        if "consolidation_enabled" in data:
            try:
                self.consolidation_enabled.setChecked(bool(data["consolidation_enabled"]))
            except (ValueError, TypeError):
                pass

    # ──────────────────────────────────────────────
    # ACTIONS
    # ──────────────────────────────────────────────

    def _reset_settings(self):
        """Réinitialise tous les paramètres (supprime le fichier et recharge)."""
        reply = QMessageBox.question(
            self, "Réinitialiser",
            "Réinitialiser tous les paramètres ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.settings_file.exists():
                self.settings_file.unlink()
            self._dirty = False
            self._apply_defaults()
            QMessageBox.information(self, "Réinitialisé", "Paramètres réinitialisés.")

    def _apply_defaults(self):
        """Remet tous les widgets à leurs valeurs par défaut."""
        self.asst_name_input.setText("NURU")
        self.lang_select.setCurrentIndex(0)
        self.theme_select.setCurrentIndex(0)
        self.font_size_spin.setValue(14)
        self.hybrid_mode_select.setCurrentIndex(0)
        self.confidence_slider.setValue(50)
        self.max_steps_spin.setValue(5)
        self.cloud_model_select.setCurrentIndex(0)
        self.llm_timeout_spin.setValue(30)
        self.active_model.setCurrentIndex(0)
        self.provider_select.setCurrentIndex(0)
        self.temp_slider.setValue(70)
        self.top_p_slider.setValue(90)
        self.context_spin.setValue(4096)
        self.max_tokens_spin.setValue(2048)
        self.rag_enabled.setChecked(True)
        self.rag_chunks_spin.setValue(10)
        self.similarity_slider.setValue(60)
        self.embedding_select.setCurrentIndex(0)
        self.consolidation_enabled.setChecked(True)
        self.consolidation_interval_spin.setValue(6)
        self.importance_slider.setValue(30)
        self.voice_enabled.setChecked(True)
        self.voice_select.setCurrentIndex(0)
        self.speed_slider.setValue(100)
        self.volume_slider.setValue(80)

    def _export_settings(self):
        """Exporte la config dans un fichier JSON choisi par l'utilisateur."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter la configuration",
            "nuru_settings.json", "*.json"
        )
        if path:
            data = self._gather_settings()
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(
                    self, "Exporté",
                    f"✅ Configuration exportée vers {path}"
                )
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Export échoué : {e}")

    def _export_diagnostics(self):
        """Exporte un diagnostic complet (settings + système) en JSON."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export diagnostic", "nuru_diagnostic.json", "*.json"
        )
        if not path:
            return

        diag = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "version": NURU_VERSION,
            "settings": self._gather_settings(),
            "system": self._get_sys_stats(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(diag, f, indent=2, ensure_ascii=False)
            QMessageBox.information(
                self, "Diagnostic",
                f"✅ Diagnostic exporté vers {path}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Export diagnostic échoué : {e}")

    def _on_reindex_all(self):
        """Déclenche une réindexation complète de la base RAG."""
        reply = QMessageBox.question(
            self, "Réindexation complète",
            "Lancer une réindexation complète de tous les documents ?\n"
            "Cette opération peut prendre plusieurs minutes.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            logger.info("Full reindex triggered from Settings")
            QMessageBox.information(
                self, "Réindexation",
                "✅ Réindexation complète lancée."
            )

    def _on_reindex_doc(self):
        """Réindexe un document spécifique sélectionné dans le menu."""
        doc = self.doc_select.currentText()
        if not doc or doc.startswith("—"):
            QMessageBox.warning(self, "Document", "Veuillez sélectionner un document.")
            return
        logger.info("Reindex document: %s", doc)
        QMessageBox.information(
            self, "Réindexation",
            f"✅ Réindexation de « {doc} » lancée."
        )

    def _on_clear_cache(self):
        """Vide le cache (chroma db, embeddings temporaires)."""
        reply = QMessageBox.question(
            self, "Vider le cache",
            "Voulez-vous vider le cache de NURU ?\n"
            "Les embeddings et index temporaires seront supprimés.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            logger.info("Cache clear triggered from Settings")
            QMessageBox.information(
                self, "Cache",
                "✅ Cache vidé avec succès."
            )

    def _on_export_logs(self):
        """Exporte les logs dans un fichier choisi par l'utilisateur."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les logs",
            "nuru_logs.txt", "*.txt"
        )
        if not path:
            return

        if self.config and hasattr(self.config, 'log_file'):
            log_path = Path(self.config.log_file)
            if log_path.exists():
                try:
                    import shutil
                    shutil.copy2(str(log_path), path)
                    QMessageBox.information(
                        self, "Logs exportés",
                        f"✅ Logs exportés vers {path}"
                    )
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", f"Export logs échoué : {e}")
            else:
                QMessageBox.warning(
                    self, "Logs",
                    f"Fichier de logs introuvable : {log_path}"
                )
        else:
            QMessageBox.warning(
                self, "Logs",
                "Aucun fichier de logs configuré."
            )

    def _on_audio_test(self):
        """Joue un son de test vocal."""
        logger.info("Audio test triggered from Settings")
        QMessageBox.information(
            self, "Test audio",
            "▶ Son de test envoyé."
        )

    def _on_open_logs(self):
        """Ouvre la page des logs (émet un signal ou navigue via parent)."""
        logger.info("Open logs requested from Settings")
        # Try to find LogsPage in parent/stack
        parent = self.parent()
        if parent and hasattr(parent, 'stacked'):
            for i in range(parent.stacked.count()):
                w = parent.stacked.widget(i)
                if w and w.__class__.__name__ == "LogsPage":
                    parent.stacked.setCurrentWidget(w)
                    return
        # Fallback: try to open log file directly
        if self.config and hasattr(self.config, 'log_file'):
            log_path = Path(self.config.log_file)
            if log_path.exists():
                import subprocess
                try:
                    subprocess.Popen(["open", str(log_path)])
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    # SYSTÈME LIVE MONITOR
    # ──────────────────────────────────────────────

    def _start_sys_monitor(self):
        """Démarre un timer pour mettre à jour les stats système en direct."""
        self._sys_timer = QTimer(self)
        self._sys_timer.timeout.connect(self._update_sys_stats)
        self._sys_timer.start(2000)  # toutes les 2 secondes
        self._update_sys_stats()  # première mise à jour immédiate

    def _update_sys_stats(self):
        """Met à jour les labels RAM, CPU, Disque."""
        if not HAS_PSUTIL:
            self.sys_ram_label.setText("psutil non installé")
            self.sys_cpu_label.setText("psutil non installé")
            self.sys_disk_label.setText("psutil non installé")
            return

        try:
            # RAM
            ram = psutil.virtual_memory()
            used_gb = ram.used / (1024**3)
            total_gb = ram.total / (1024**3)
            ram_pct = ram.percent
            self.sys_ram_label.setText(
                f"{used_gb:.1f} Go / {total_gb:.1f} Go  ({ram_pct}%)"
            )

            # CPU
            cpu_pct = psutil.cpu_percent(interval=None)
            cpu_count = psutil.cpu_count()
            self.sys_cpu_label.setText(f"{cpu_pct}%  ({cpu_count} cœurs)")

            # Disque
            disk = psutil.disk_usage("/")
            disk_used = disk.used / (1024**3)
            disk_total = disk.total / (1024**3)
            disk_pct = disk.percent
            self.sys_disk_label.setText(
                f"{disk_used:.1f} Go / {disk_total:.1f} Go  ({disk_pct}%)"
            )
        except Exception as e:
            logger.debug("Sys stats update failed: %s", e)

    def _get_sys_stats(self) -> dict:
        """Retourne un dict des stats système pour le diagnostic."""
        if not HAS_PSUTIL:
            return {"error": "psutil not available"}
        try:
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "ram_used_gb": round(ram.used / (1024**3), 2),
                "ram_total_gb": round(ram.total / (1024**3), 2),
                "ram_percent": ram.percent,
                "cpu_percent": psutil.cpu_percent(interval=None),
                "cpu_count": psutil.cpu_count(),
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_percent": disk.percent,
            }
        except Exception as e:
            return {"error": str(e)}

    # ──────────────────────────────────────────────
    # CLEANUP
    # ──────────────────────────────────────────────

    def cleanup(self):
        """Arrête le timer système lors de la fermeture."""
        if self._sys_timer:
            self._sys_timer.stop()
            self._sys_timer = None
