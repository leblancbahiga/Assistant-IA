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
from PySide6.QtCore import Qt
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
    ("gemini",      "Google Gemini"),
    ("brave",       "Brave Search"),
    ("tavily",      "Tavily Search"),
    ("nvidia",      "NVIDIA"),
]

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
        # 5 — Stockage
        self._build_storage()
        # 6 — À propos
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

        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["groq", "openrouter", "deepseek", "local"])
        idx = self._provider_combo.findText(config.cloud_provider)
        if idx >= 0:
            self._provider_combo.setCurrentIndex(idx)
        self._provider_combo.setStyleSheet(self._combo_style())
        card.add_row("Fournisseur cloud", self._provider_combo)

        self._cloud_model = QLineEdit(config.cloud_model)
        self._cloud_model.setStyleSheet(self._input_style())
        card.add_row("Modèle cloud", self._cloud_model)

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
        config._save_yaml_key("cloud_provider")
        config._save_yaml_key("cloud_model")
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
