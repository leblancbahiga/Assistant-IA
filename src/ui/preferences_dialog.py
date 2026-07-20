"""
NURU V12 — Fenêtre Préférences (DM-1 "Deep Cyan").

Fenêtre modale organisée en sections scrollables :
  - Général (thème, langue, nom)
  - IA & Modèles (provider, température, timeout)
  - API Keys (via Keychain macOS)
  - Recherche & RAG
  - Stockage & Chemins
  - À propos

Utilise le singleton `config` pour lire/écrire dans config/settings.yaml
et keyring pour les clés API.
"""

import logging
import os
import sys
from pathlib import Path

import keyring
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QWidget, QLineEdit,
    QComboBox, QSpinBox, QSlider, QCheckBox, QMessageBox,
    QFileDialog, QSizePolicy,
)

from src.ui.tokens import Color, Typography, Radius, Spacing
from src.config import config

logger = logging.getLogger(__name__)

# ── Clés API connues ──
API_KEYS = [
    ("groq",        "Groq Cloud"),
    ("deepseek",    "DeepSeek"),
    ("openrouter",  "OpenRouter"),
    ("opencode_zen","OpenCode Zen"),
    ("gemini",      "Google Gemini"),
    ("openai",      "OpenAI"),
    ("qwen",        "Qwen (DashScope)"),
    ("together",    "Together AI"),
    ("mistral",     "Mistral AI"),
    ("xai",         "xAI (Grok)"),
    ("nvidia",      "NVIDIA NIM"),
    ("brave",       "Brave Search"),
    ("tavily",      "Tavily Search"),
]

# Table des fournisseurs : nom → (base_url, modèle_par_défaut, besoin_clé)
PROVIDER_REGISTRY = {
    "opencode_zen": ("https://opencode.ai/zen/v1", "deepseek-v4-flash-free", True),
    "groq":         ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", True),
    "openrouter":   ("https://openrouter.ai/api/v1", "deepseek/deepseek-v4-flash", True),
    "deepseek":     ("https://api.deepseek.com", "deepseek-chat", True),
    "qwen":         ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", True),
    "openai":       ("https://api.openai.com/v1", "gpt-4o-mini", True),
    "gemini":       ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", True),
    "together":     ("https://api.together.xyz/v1", "mistralai/Mixtral-8x22B-Instruct-v0.1", True),
    "mistral":      ("https://api.mistral.ai/v1", "mistral-small-latest", True),
    "xai":          ("https://api.x.ai/v1", "grok-2", True),
    "nvidia":       ("https://integrate.api.nvidia.com/v1", "nvidia/llama-3.1-nemotron-70b-instruct", True),
    "ollama":       ("http://localhost:11434/v1", "llama3", False),
    "local":        ("", "phi-4-mini", False),
}

NURU_VERSION = "V12"


class SectionCard(QFrame):
    """Carte de section DM-1 avec titre + contenu."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("PrefSectionCard")
        self.setStyleSheet(f"""
            #PrefSectionCard {{
                background: {Color.BG_SURFACE1};
                border: 1px solid {Color.BORDER};
                border-radius: {Radius.WIDGET}px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("PrefSectionHeader")
        hdr.setStyleSheet(f"""
            #PrefSectionHeader {{
                background: transparent;
                border-bottom: 1px solid {Color.BORDER};
            }}
        """)
        hdr.setFixedHeight(42)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)
        t = QLabel(title)
        t.setStyleSheet(f"""
            color: {Color.CYAN}; font-size: {Typography.SIZE_HEADING_2}pt;
            font-weight: {Typography.WEIGHT_SEMIBOLD}; background: transparent;
        """)
        hl.addWidget(t)
        hl.addStretch()
        layout.addWidget(hdr)

        # Body
        self.body = QVBoxLayout()
        self.body.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.MD)
        self.body.setSpacing(8)
        layout.addLayout(self.body)

    def add_row(self, label: str, widget: QWidget):
        """Ajoute une ligne label + widget."""
        row = QFrame()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 4, 0, 4)
        rl.setSpacing(12)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"""
            color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}pt;
            background: transparent; min-width: 140px;
        """)
        rl.addWidget(lbl)
        rl.addWidget(widget, stretch=1)
        self.body.addWidget(row)

    def add_separator(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Color.BORDER};")
        self.body.addWidget(sep)

    def add_stretch(self):
        self.body.addStretch()


class PreferencesDialog(QDialog):
    """Fenêtre modale Préférences NURU V12 — DM-1."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Préférences NURU")
        self.setFixedSize(680, 620)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowTitleHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # Fond global
        self.setStyleSheet(f"""
            PreferencesDialog {{
                background: {Color.BG_DEEP};
            }}
        """)

        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ──
        header = self._build_header()
        main_layout.addWidget(header)

        # ── Scroll area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: rgba(0,212,255,0.05); width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0,212,255,0.25); border-radius: 3px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self._content_layout.setSpacing(Spacing.MD)

        self._build_sections()

        self._content_layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll, stretch=1)

        # ── Footer ──
        footer = self._build_footer()
        main_layout.addWidget(footer)

    # ── Header ──

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(f"""
            background: {Color.BG_SURFACE1};
            border-bottom: 1px solid {Color.BORDER};
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)

        title = QLabel("⚙  Préférences")
        title.setStyleSheet(f"""
            color: {Color.TEXT_PRIMARY}; font-size: {Typography.SIZE_HEADING_2}pt;
            font-weight: {Typography.WEIGHT_SEMIBOLD}; background: transparent;
        """)
        hl.addWidget(title)
        hl.addStretch()
        return header

    # ── Sections ──

    def _build_sections(self):
        cl = self._content_layout

        # 1 — Général
        self._build_general()
        # 2 — IA & Modèles
        self._build_models()
        # 3 — API Keys
        self._build_apikeys()
        # 4 — Recherche & RAG
        self._build_rag()
        # 5 — Indexation
        self._build_indexing()
        # 6 — Stockage
        self._build_storage()
        # 7 — À propos
        self._build_about()

    def _build_general(self):
        card = SectionCard("GÉNÉRAL")
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Sombre", "Clair"])
        self._theme_combo.setCurrentIndex(0)
        self._theme_combo.setStyleSheet(self._combo_style())
        card.add_row("Thème", self._theme_combo)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Français", "English"])
        self._lang_combo.setStyleSheet(self._combo_style())
        card.add_row("Langue", self._lang_combo)

        self._name_input = QLineEdit("NURU")
        self._name_input.setStyleSheet(self._input_style())
        card.add_row("Nom assistant", self._name_input)

        self._hybrid_combo = QComboBox()
        self._hybrid_combo.addItems(["cloud_first", "local_first", "offline_only"])
        self._hybrid_combo.setStyleSheet(self._combo_style())
        card.add_row("Mode hybride", self._hybrid_combo)

        self._context_spin = QSpinBox()
        self._context_spin.setRange(1024, 32768)
        self._context_spin.setValue(config.rag_max_context_tokens)
        self._context_spin.setSingleStep(1024)
        self._context_spin.setStyleSheet(self._spin_style())
        card.add_row("Max tokens contexte", self._context_spin)

        cl = self._content_layout
        cl.addWidget(card)

    def _build_models(self):
        card = SectionCard("IA & MODÈLES")

        # Provider principal
        self._provider_combo = QComboBox()
        # Tous les providers, en commençant par le principal configuré
        providers = sorted(PROVIDER_REGISTRY.keys())
        self._provider_combo.addItems(providers)
        idx = self._provider_combo.findText(config.cloud_provider)
        if idx >= 0:
            self._provider_combo.setCurrentIndex(idx)
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self._provider_combo.setStyleSheet(self._combo_style())
        card.add_row("Fournisseur cloud", self._provider_combo)

        # Label info URL
        self._provider_url = QLabel("")
        self._provider_url.setStyleSheet(f"""
            color: {Color.TEXT_MUTED}; font-size: 7.5pt;
            padding-left: 140px; background: transparent;
        """)
        card.add_row("", self._provider_url)
        self._update_provider_url(config.cloud_provider)

        self._cloud_model = QLineEdit(config.cloud_model)
        self._cloud_model.setStyleSheet(self._input_style())
        card.add_row("Modèle cloud", self._cloud_model)

        # Fallback fournisseur
        self._fallback_combo = QComboBox()
        # Extraire la partie provider du fallback actuel (format "provider/model")
        current_fallback = config.cloud_fallback
        fallback_parts = current_fallback.split("/", 1)
        fallback_provider = fallback_parts[0] if len(fallback_parts) > 0 else "openrouter"
        fallback_providers = [p for p in providers if p != config.cloud_provider and p != "local"]
        self._fallback_combo.addItems(fallback_providers)
        idx_fb = self._fallback_combo.findText(fallback_provider)
        if idx_fb >= 0:
            self._fallback_combo.setCurrentIndex(idx_fb)
        self._fallback_combo.currentTextChanged.connect(self._on_fallback_changed)
        self._fallback_combo.setStyleSheet(self._combo_style())
        card.add_row("Fallback (si indispo)", self._fallback_combo)

        self._fallback_model = QLineEdit(
            fallback_parts[1] if len(fallback_parts) > 1 else "deepseek/deepseek-v4-flash"
        )
        self._fallback_model.setStyleSheet(self._input_style())
        card.add_row("Modèle fallback", self._fallback_model)

        self._local_model = QLineEdit(config.local_model)
        self._local_model.setStyleSheet(self._input_style())
        card.add_row("Modèle local", self._local_model)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(10, 300)
        self._timeout_spin.setValue(30)
        self._timeout_spin.setSuffix(" s")
        self._timeout_spin.setStyleSheet(self._spin_style())
        card.add_row("Timeout LLM", self._timeout_spin)

        # Température
        temp_row = QFrame()
        temp_row.setStyleSheet("background: transparent;")
        temp_rl = QHBoxLayout(temp_row)
        temp_rl.setContentsMargins(0, 4, 0, 4)
        temp_rl.setSpacing(12)
        temp_lbl = QLabel("Température")
        temp_lbl.setStyleSheet(f"""
            color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}pt;
            background: transparent; min-width: 140px;
        """)
        self._temp_slider = QSlider(Qt.Horizontal)
        self._temp_slider.setRange(0, 200)
        self._temp_slider.setValue(70)
        self._temp_slider.setStyleSheet(self._slider_style())
        self._temp_val = QLabel("0.70")
        self._temp_val.setFixedWidth(36)
        self._temp_val.setStyleSheet(f"""
            color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}pt;
            background: transparent;
        """)
        self._temp_slider.valueChanged.connect(
            lambda v: self._temp_val.setText(f"{v/100:.2f}")
        )
        temp_rl.addWidget(temp_lbl)
        temp_rl.addWidget(self._temp_slider, stretch=1)
        temp_rl.addWidget(self._temp_val)
        card.add_row("Température", temp_row)

        cl = self._content_layout
        cl.addWidget(card)

    def _build_apikeys(self):
        card = SectionCard("CLÉS API (stockées dans le trousseau macOS)")

        self._api_inputs = {}
        for key_id, key_label in API_KEYS:
            inp = QLineEdit()
            inp.setPlaceholderText("Non configurée")
            inp.setEchoMode(QLineEdit.EchoMode.Password)
            inp.setStyleSheet(self._input_style())
            # Remplir depuis le Keychain — marqueur visuel
            stored = keyring.get_password("com.nuru.assistant", key_id)
            if stored:
                inp.setText("••••••••")
            card.add_row(key_label, inp)
            self._api_inputs[key_id] = inp

        cl = self._content_layout
        cl.addWidget(card)

    def _build_rag(self):
        card = SectionCard("RECHERCHE & RAG")

        self._rag_k_spin = QSpinBox()
        self._rag_k_spin.setRange(1, 20)
        self._rag_k_spin.setValue(config.rag_k)
        self._rag_k_spin.setStyleSheet(self._spin_style())
        card.add_row("Documents (k)", self._rag_k_spin)

        self._rag_thresh_slider = QSlider(Qt.Horizontal)
        self._rag_thresh_slider.setRange(0, 100)
        self._rag_thresh_slider.setValue(int(config.rag_score_threshold * 100))
        self._rag_thresh_slider.setStyleSheet(self._slider_style())
        self._rag_thresh_val = QLabel(f"{config.rag_score_threshold:.2f}")
        self._rag_thresh_val.setFixedWidth(36)
        self._rag_thresh_val.setStyleSheet(f"""
            color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}pt;
            background: transparent;
        """)
        self._rag_thresh_slider.valueChanged.connect(
            lambda v: self._rag_thresh_val.setText(f"{v/100:.2f}")
        )

        thresh_row = QFrame()
        thresh_row.setStyleSheet("background: transparent;")
        thresh_rl = QHBoxLayout(thresh_row)
        thresh_rl.setContentsMargins(0, 4, 0, 4)
        thresh_rl.setSpacing(12)
        thresh_lbl = QLabel("Seuil score")
        thresh_lbl.setStyleSheet(f"""
            color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}pt;
            background: transparent; min-width: 140px;
        """)
        thresh_rl.addWidget(thresh_lbl)
        thresh_rl.addWidget(self._rag_thresh_slider, stretch=1)
        thresh_rl.addWidget(self._rag_thresh_val)
        card.add_row("", thresh_row)

        self._tj_check = QCheckBox("Compression TokenJuice")
        self._tj_check.setChecked(config.token_juice_enabled)
        self._tj_check.setStyleSheet(self._check_style())
        card.add_row("", self._tj_check)

        self._learning_check = QCheckBox("Apprentissage continu")
        self._learning_check.setChecked(config.learning_enabled)
        self._learning_check.setStyleSheet(self._check_style())
        card.add_row("", self._learning_check)

        cl = self._content_layout
        cl.addWidget(card)

    # ── Indexation ──

    def _build_indexing(self):
        """Section Indexation — choisir dossiers à indexer et lancer une analyse."""
        card = SectionCard("INDEXATION")

        # Dossiers surveillés
        dirs_frame = QFrame()
        dirs_frame.setStyleSheet("background: transparent;")
        dirs_layout = QVBoxLayout(dirs_frame)
        dirs_layout.setContentsMargins(0, 0, 0, 0)
        dirs_layout.setSpacing(6)

        self._index_dirs = [
            str(Path.home() / "Downloads" / "Assistant IA" / "documents"),
            str(Path.home() / "Documents"),
            str(Path.home() / "Desktop"),
        ]
        self._index_checks = []
        for d in self._index_dirs:
            cb = QCheckBox(d)
            cb.setChecked(Path(d).exists())
            cb.setStyleSheet(self._check_style())
            self._index_checks.append(cb)
            dirs_layout.addWidget(cb)

        card.add_row("Dossiers", dirs_frame)

        # Exclusions
        excl_frame = QFrame()
        excl_frame.setStyleSheet("background: transparent;")
        excl_layout = QHBoxLayout(excl_frame)
        excl_layout.setContentsMargins(0, 0, 0, 0)
        excl_layout.setSpacing(6)
        excl_lbl = QLabel("Exclure motifs :")
        excl_lbl.setStyleSheet(f"color: {Color.TEXT_MUTED}; background: transparent;")
        self._exclude_pattern = QLineEdit("*.tmp,*.log,__pycache__")
        self._exclude_pattern.setStyleSheet(self._input_style())
        excl_layout.addWidget(excl_lbl)
        excl_layout.addWidget(self._exclude_pattern, stretch=1)
        card.add_row("", excl_frame)

        # Boutons d'action
        actions = QFrame()
        actions.setStyleSheet("background: transparent;")
        act_layout = QHBoxLayout(actions)
        act_layout.setContentsMargins(0, 0, 0, 0)
        act_layout.setSpacing(8)

        scan_btn = QPushButton("🔍 Analyser maintenant")
        scan_btn.setStyleSheet(self._btn_style())
        scan_btn.clicked.connect(self._on_scan_now)
        act_layout.addWidget(scan_btn)

        reindex_btn = QPushButton("🔄 Réindexer tout")
        reindex_btn.setStyleSheet(self._btn_style())
        reindex_btn.clicked.connect(self._on_reindex_all)
        act_layout.addWidget(reindex_btn)

        reset_idx_btn = QPushButton("🗑️ Vider l'index")
        reset_idx_btn.setStyleSheet(self._btn_danger_style())
        reset_idx_btn.clicked.connect(self._on_reset_index)
        act_layout.addWidget(reset_idx_btn)

        card.add_row("", actions)

        cl = self._content_layout
        cl.addWidget(card)

    def _on_scan_now(self):
        """Lance une analyse des dossiers cochés via le script dédié."""
        dirs = [cb.text() for cb in self._index_checks if cb.isChecked()]
        if not dirs:
            self._set_status("❌ Aucun dossier sélectionné")
            return
        self._set_status("🔍 Indexation lancée en arrière-plan (scripts/reindex_v17.py)...")
        # Lancer le script de ré-indexation via QProcess (non-bloquant)
        self._run_reindex_script()

    def _on_reindex_all(self):
        """Vide l'index existant et relance une analyse complète."""
        from src.ingestion import reset_index
        reset_index()
        self._set_status("🔄 Index vidé, réindexation complète en cours...")
        self._run_reindex_script(force_full=True)

    def _on_reset_index(self):
        """Vide l'index sans relancer d'analyse."""
        from src.ingestion import reset_index
        reset_index()
        self._set_status("🗑️ Index vidé. Utilisez « Analyser maintenant » pour réindexer")

    def _run_reindex_script(self, force_full: bool = False) -> None:
        """Lance scripts/reindex_v17.py via QProcess en arrière-plan."""
        import shlex
        try:
            from PySide6.QtCore import QProcess
        except ImportError:
            self._set_status("❌ QProcess non disponible — relance manuelle via terminal")
            return
        
        self._reindex_process = QProcess(self)
        self._reindex_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        
        script_path = Path(__file__).parents[2] / "scripts" / "reindex_v17.py"
        if not script_path.exists():
            self._set_status(f"❌ Script introuvable: {script_path}")
            return
        
        venv_python = Path(__file__).parents[2] / ".venv" / "bin" / "python3"
        python = str(venv_python) if venv_python.exists() else "python3"
        
        self._reindex_process.finished.connect(
            lambda exit_code, status: self._set_status(
                f"✅ Indexation terminée (exit {exit_code})"
                if exit_code == 0
                else f"❌ Indexation échouée (exit {exit_code})"
            )
        )
        self._reindex_process.started.connect(
            lambda: self._set_status("🔍 Ré-indexation en cours...")
        )
        
        self._reindex_process.start(python, [str(script_path)])

    def _set_status(self, msg: str):
        """Affiche un message dans le footer."""
        status = self.findChild(QLabel, "pref_status")
        if status:
            status.setText(msg)
            QTimer.singleShot(5000, lambda: status.setText(""))

    @staticmethod
    def _btn_style():
        return f"""
            QPushButton {{
                background: {Color.BG_SURFACE2}; color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER}; border-radius: 6px;
                padding: 6px 16px; font-size: 11pt;
            }}
            QPushButton:hover {{ background: {Color.CYAN_GLOW}; border-color: {Color.CYAN}; }}
        """

    @staticmethod
    def _btn_danger_style():
        return f"""
            QPushButton {{
                background: rgba(255,77,106,0.15); color: {Color.ROSE};
                border: 1px solid rgba(255,77,106,0.3); border-radius: 6px;
                padding: 6px 16px; font-size: 11pt;
            }}
            QPushButton:hover {{ background: rgba(255,77,106,0.25); }}
        """

    # ── Helpers fournisseurs ──

    def _update_provider_url(self, provider: str) -> None:
        info = PROVIDER_REGISTRY.get(provider)
        if info:
            url = info[0]
            needs_key = info[2]
            txt = f"🔗 {url}"
            if needs_key:
                stored = keyring.get_password("com.nuru.assistant", provider)
                txt += " 🔑✅" if stored else " 🔑❌"
            self._provider_url.setText(txt)

    def _on_provider_changed(self, provider: str) -> None:
        self._update_provider_url(provider)
        # Suggérer un modèle par défaut si le champ est vide
        info = PROVIDER_REGISTRY.get(provider)
        if info and not self._cloud_model.text().strip():
            self._cloud_model.setText(info[1])
        # Mettre à jour la liste des fallbacks (exclure le provider courant)
        providers = sorted(PROVIDER_REGISTRY.keys())
        fallback_candidates = [p for p in providers if p != provider and p != "local"]
        self._fallback_combo.clear()
        self._fallback_combo.addItems(fallback_candidates)

    def _on_fallback_changed(self, provider: str) -> None:
        info = PROVIDER_REGISTRY.get(provider)
        if info and not self._fallback_model.text().strip():
            self._fallback_model.setText(info[1])

    # ── Stockage ──

    def _build_storage(self):
        card = SectionCard("STOCKAGE & CHEMINS")

        self._data_path = QLineEdit(str(config.data_dir))
        self._data_path.setStyleSheet(self._input_style())
        browse_btn = QPushButton("…")
        browse_btn.setFixedSize(28, 28)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.BG_SURFACE2}; color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER}; border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {Color.CYAN_GLOW}; }}
        """)
        browse_btn.clicked.connect(lambda: self._browse_path("_data_path"))
        row = QFrame()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        rl.addWidget(self._data_path, stretch=1)
        rl.addWidget(browse_btn)
        card.add_row("Données", row)

        self._brain_path = QLineEdit(config.nuru_brain_path)
        self._brain_path.setStyleSheet(self._input_style())
        browse_btn2 = QPushButton("…")
        browse_btn2.setFixedSize(28, 28)
        browse_btn2.setStyleSheet(browse_btn.styleSheet())
        browse_btn2.clicked.connect(lambda: self._browse_path("_brain_path"))
        row2 = QFrame()
        row2.setStyleSheet("background: transparent;")
        rl2 = QHBoxLayout(row2)
        rl2.setContentsMargins(0, 0, 0, 0)
        rl2.setSpacing(4)
        rl2.addWidget(self._brain_path, stretch=1)
        rl2.addWidget(browse_btn2)
        card.add_row("Nuru_Brain", row2)

        cl = self._content_layout
        cl.addWidget(card)

    def _build_about(self):
        card = SectionCard(f"À PROPOS — NURU {NURU_VERSION}")

        import psutil as psu
        try:
            proc = psu.Process()
            mem_mb = proc.memory_info().rss / (1024 ** 2)
        except Exception:
            mem_mb = 0

        info_lines = [
            f"Version : NURU {NURU_VERSION} (DM-1 Deep Cyan)",
            f"Python : {sys.version.split()[0]}",
            f"PySide6 : 6.11.1",
            f"RAM processus : {mem_mb:.0f} Mo" if mem_mb else "RAM : N/A",
            f"Provider cloud : {config.cloud_provider}/{config.cloud_model}",
            f"Modèle local : {config.local_model}",
            f"Mode hybride : {config.hybrid_mode}",
            f"RAG k={config.rag_k}  seuil={config.rag_score_threshold}",
        ]
        info = QLabel("\n".join(info_lines))
        info.setStyleSheet(f"""
            color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_CAPTION}pt;
            background: transparent; padding: 8px;
        """)
        card.body.addWidget(info)

        cl = self._content_layout
        cl.addWidget(card)

    # ── Footer ──

    def _build_footer(self):
        footer = QFrame()
        footer.setFixedHeight(56)
        footer.setStyleSheet(f"""
            background: {Color.BG_SURFACE1};
            border-top: 1px solid {Color.BORDER};
        """)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)

        status = QLabel("")
        status.setObjectName("pref_status")
        status.setStyleSheet(f"color: {Color.TEXT_MUTED}; background: transparent; font-size: 11px;")
        fl.addWidget(status)

        fl.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet(self._btn_ghost_style())
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("💾  Sauvegarder")
        save_btn.setStyleSheet(self._btn_primary_style())
        save_btn.clicked.connect(self._save_and_close)

        fl.addWidget(cancel_btn)
        fl.addWidget(save_btn)

        self._status_label = status
        return footer

    # ── Actions ──

    def _browse_path(self, attr: str):
        path = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
        if path:
            getattr(self, attr).setText(path)

    def _save_and_close(self):
        """Sauvegarde tous les paramètres et ferme la fenêtre."""
        try:
            self._save_general()
            self._save_models()
            self._save_apikeys()
            self._save_rag()
            self._save_storage()
            self._status_label.setText("✅ Sauvegardé")
            QMessageBox.information(self, "NURU", "Paramètres sauvegardés.\nRedémarrez l'application pour appliquer certains changements.")
            self.accept()
        except Exception as e:
            logger.error(f"Erreur sauvegarde préférences: {e}")
            self._status_label.setText(f"❌ Erreur: {e}")

    def _save_general(self):
        theme = self._theme_combo.currentText()
        config.hybrid_mode = self._hybrid_combo.currentText()
        config.rag_max_context_tokens = self._context_spin.value()
        config._save_yaml_key("hybrid_mode")
        config._save_yaml_key("rag_max_context_tokens")

    def _save_models(self):
        config.cloud_provider = self._provider_combo.currentText()
        config.cloud_model = self._cloud_model.text().strip()
        config.local_model = self._local_model.text().strip()
        # Construire cloud_fallback au format "provider/model"
        fb_provider = self._fallback_combo.currentText()
        fb_model = self._fallback_model.text().strip()
        config.cloud_fallback = f"{fb_provider}/{fb_model}" if fb_model else fb_provider
        config._save_yaml_key("cloud_provider")
        config._save_yaml_key("cloud_model")
        config._save_yaml_key("cloud_fallback")
        config._save_yaml_key("local_model")

    def _save_apikeys(self):
        for key_id, inp in self._api_inputs.items():
            text = inp.text()
            if text and text != "••••••••":
                keyring.set_password("com.nuru.assistant", key_id, text)
                logger.info(f"Clé API {key_id} sauvegardée dans le trousseau")

    def _save_rag(self):
        config.rag_k = self._rag_k_spin.value()
        config.rag_score_threshold = self._rag_thresh_slider.value() / 100.0
        config.token_juice_enabled = self._tj_check.isChecked()
        config.learning_enabled = self._learning_check.isChecked()
        config._save_yaml_key("rag_k")
        config._save_yaml_key("rag_score_threshold")
        config._save_yaml_key("token_juice_enabled")
        config._save_yaml_key("learning_enabled")

    def _save_storage(self):
        data_dir = self._data_path.text().strip()
        brain_dir = self._brain_path.text().strip()
        if data_dir:
            config.data_dir = Path(data_dir)
        if brain_dir:
            config.nuru_brain_path = brain_dir

    # ── Styles ──

    @staticmethod
    def _input_style() -> str:
        return f"""
            QLineEdit {{
                background: {Color.BG_SURFACE2}; color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER}; border-radius: 4px;
                padding: 6px 10px; font-size: {Typography.SIZE_BODY}pt;
            }}
            QLineEdit:focus {{ border-color: {Color.CYAN}; }}
        """

    @staticmethod
    def _combo_style() -> str:
        return f"""
            QComboBox {{
                background: {Color.BG_SURFACE2}; color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER}; border-radius: 4px;
                padding: 6px 10px; font-size: {Typography.SIZE_BODY}pt;
                min-width: 180px;
            }}
            QComboBox:focus {{ border-color: {Color.CYAN}; }}
            QComboBox::drop-down {{
                border: none; width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none; border: none;
            }}
            QComboBox QAbstractItemView {{
                background: {Color.BG_SURFACE1}; color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER}; border-radius: 4px;
                selection-background-color: {Color.CYAN_GLOW};
                selection-color: {Color.CYAN};
            }}
        """

    @staticmethod
    def _spin_style() -> str:
        return f"""
            QSpinBox {{
                background: {Color.BG_SURFACE2}; color: {Color.TEXT_PRIMARY};
                border: 1px solid {Color.BORDER}; border-radius: 4px;
                padding: 6px 10px; font-size: {Typography.SIZE_BODY}pt;
                min-width: 100px;
            }}
            QSpinBox:focus {{ border-color: {Color.CYAN}; }}
        """

    @staticmethod
    def _slider_style() -> str:
        return f"""
            QSlider::groove:horizontal {{
                background: {Color.BG_DEEP}; height: 4px; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {Color.CYAN}; width: 14px; height: 14px;
                margin: -5px 0; border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Color.CYAN}; border-radius: 2px;
            }}
        """

    @staticmethod
    def _check_style() -> str:
        return f"""
            QCheckBox {{
                color: {Color.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}pt;
                background: transparent; spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 3px;
                border: 1px solid {Color.BORDER};
                background: {Color.BG_SURFACE2};
            }}
            QCheckBox::indicator:checked {{
                background: {Color.CYAN}; border-color: {Color.CYAN};
            }}
        """

    @staticmethod
    def _btn_primary_style() -> str:
        return f"""
            QPushButton {{
                background: {Color.CYAN}; color: #0A0E17;
                border: none; border-radius: 6px;
                padding: 8px 20px; font-weight: bold; font-size: 12px;
            }}
            QPushButton:hover {{ background: rgba(0,212,255,0.8); }}
            QPushButton:pressed {{ background: rgba(0,180,200,0.9); }}
        """

    @staticmethod
    def _btn_ghost_style() -> str:
        return f"""
            QPushButton {{
                background: transparent; color: {Color.TEXT_SECONDARY};
                border: 1px solid {Color.BORDER}; border-radius: 6px;
                padding: 8px 20px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {Color.BG_SURFACE2}; color: {Color.TEXT_PRIMARY}; }}
        """

    # ── Key ──

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        super().keyPressEvent(event)
