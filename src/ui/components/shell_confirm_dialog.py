"""
NURU V11.2 — ShellConfirmDialog : Dialogue d'approbation humaine PySide6.

Dialogue modal qui permet à l'utilisateur d'approuver ou refuser
une commande shell avant son exécution. Thème cyberpunk NURU.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Palette NURU ──────────────────────────────────────────────────
BG_DARK = "#0A0E17"
BG_SURFACE = "#151B26"
BG_CARD = "rgba(10, 14, 23, 0.95)"
BORDER_DIM = "#1A2332"
BORDER_ACCENT = "#2A2A4E"
TEXT_PRIMARY = "#E2E8F0"
TEXT_SECONDARY = "#8899AA"
TEXT_DIM = "#4A6080"
ACCENT_CYAN = "#00D4FF"
COLOR_DANGER = "#F87171"
COLOR_WARNING = "#FBBF24"
COLOR_SAFE = "#4ADE80"
COLOR_READ = "#60A5FA"
COLOR_NETWORK = "#A855F7"
COLOR_INSTALL = "#F59E0B"

# ── Mapping risques ──────────────────────────────────────────────
RISK_COLORS: dict[str, str] = {
    "SAFE": COLOR_SAFE,
    "READ": COLOR_READ,
    "WRITE": COLOR_WARNING,
    "DESTRUCTIVE": COLOR_DANGER,
    "NETWORK": COLOR_NETWORK,
    "INSTALL": COLOR_INSTALL,
}

RISK_ICONS: dict[str, str] = {
    "SAFE": "🛡️",
    "READ": "👁️",
    "WRITE": "✏️",
    "DESTRUCTIVE": "💥",
    "NETWORK": "🌐",
    "INSTALL": "📦",
}

RISK_LABELS: dict[str, str] = {
    "SAFE": "Sans danger",
    "READ": "Lecture seule",
    "WRITE": "Écriture",
    "DESTRUCTIVE": "Destructif",
    "NETWORK": "Réseau",
    "INSTALL": "Installation",
}


class ShellConfirmDialog(QDialog):
    """Dialogue modal d'approbation humaine pour commandes shell.

    Paramètres
    ----------
    command : str
        Commande shell à afficher pour approbation.
    cwd : str | None
        Répertoire de travail où la commande sera exécutée.
    risk_category : str
        Catégorie de risque : SAFE, READ, WRITE, DESTRUCTIVE, NETWORK, INSTALL.
    risk_level : int
        Niveau de risque (0-10, 0=aucun risque, 10=très risqué).
    parent : QWidget | None
        Widget parent pour le centrage du dialogue.
    """

    def __init__(
        self,
        command: str,
        cwd: str | None,
        risk_category: str,
        risk_level: int,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._command = command
        self._cwd = cwd
        self._risk_category = risk_category.upper() if risk_category else "SAFE"
        self._risk_level = risk_level
        self._dry_run = ""  # dry-run output text, settable externally
        self._request_id = uuid.uuid4().hex[:12]
        self._detail_visible = False

        # Configuration du dialogue
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumSize(560, 320)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("ShellConfirmDialog")

        self._build_ui()

        # Centrer sur le parent
        if parent is not None:
            self._center_on_parent()

    # ── Construction UI ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Construit l'ensemble de l'interface du dialogue."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Cadre principal avec fond et bordure
        frame = QFrame()
        frame.setObjectName("ShellDialogFrame")
        frame.setStyleSheet(f"""
            #ShellDialogFrame {{
                background: {BG_CARD};
                border: 1px solid {BORDER_ACCENT};
                border-radius: 12px;
            }}
        """)

        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(20, 16, 20, 16)
        frame_layout.setSpacing(12)

        # 1. Titre + icône
        title_widget = self._build_title()
        frame_layout.addWidget(title_widget)

        # 2. Commande (monospace, fond sombre)
        cmd_widget = self._build_command_display()
        frame_layout.addWidget(cmd_widget)

        # 3. Barre d'info : CWD + Risque + Timeout
        info_bar = self._build_info_bar()
        frame_layout.addWidget(info_bar)

        # 4. Dry-run expandable (optionnel, caché par défaut)
        self._detail_panel = self._build_detail_panel()
        self._detail_panel.setVisible(False)
        frame_layout.addWidget(self._detail_panel)

        # 5. Boutons
        btn_bar = self._build_buttons()
        frame_layout.addWidget(btn_bar)

        outer_layout.addWidget(frame)

        # Style global du dialogue
        self.setStyleSheet(f"""
            #ShellConfirmDialog {{
                background: transparent;
            }}
        """)

    def _build_title(self) -> QWidget:
        """Barre de titre avec icône et texte."""
        container = QWidget()
        container.setObjectName("DialogTitleBar")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        icon_label = QLabel("🔒")
        icon_label.setStyleSheet(
            f"font-size: 20px; background: transparent;"
        )
        layout.addWidget(icon_label)

        title_label = QLabel("Commande shell — Approbation requise")
        title_label.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-size: 15px; font-weight: 700;"
            f" background: transparent; letter-spacing: 0.3px;"
        )
        layout.addWidget(title_label, stretch=1)

        # ID de requête discret
        req_label = QLabel(f"#{self._request_id}")
        req_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; background: transparent;"
            f" font-family: monospace;"
        )
        layout.addWidget(req_label)

        return container

    def _build_command_display(self) -> QWidget:
        """Zone d'affichage de la commande en lecture seule."""
        container = QWidget()
        container.setObjectName("CommandDisplay")
        container.setStyleSheet(f"""
            #CommandDisplay {{
                background: {BG_SURFACE};
                border: 1px solid {BORDER_ACCENT};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Label "Commande"
        lbl = QLabel("💻  Commande à exécuter")
        lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;"
            f" background: transparent; letter-spacing: 0.5px;"
        )
        layout.addWidget(lbl)

        # QTextEdit en lecture seule
        self._cmd_edit = QTextEdit()
        self._cmd_edit.setPlainText(self._command)
        self._cmd_edit.setReadOnly(True)
        self._cmd_edit.setObjectName("ShellCommandText")
        self._cmd_edit.setStyleSheet(f"""
            #ShellCommandText {{
                background: {BG_SURFACE};
                color: {TEXT_PRIMARY};
                border: none;
                font-family: 'Menlo', 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                padding: 4px 0;
                selection-background-color: {ACCENT_CYAN};
                selection-color: {BG_DARK};
            }}
        """)
        self._cmd_edit.setMinimumHeight(48)
        self._cmd_edit.setMaximumHeight(120)
        self._cmd_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._cmd_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._cmd_edit.setTabChangesFocus(False)
        layout.addWidget(self._cmd_edit)

        return container

    def _build_info_bar(self) -> QWidget:
        """Barre d'information : CWD, Risque, Timeout."""
        container = QFrame()
        container.setObjectName("InfoBar")
        container.setStyleSheet(f"""
            #InfoBar {{
                background: transparent;
                border: none;
            }}
        """)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(16)

        # ── CWD ──
        cwd_widget = QWidget()
        cwd_widget.setObjectName("InfoCwd")
        cwd_layout = QHBoxLayout(cwd_widget)
        cwd_layout.setContentsMargins(0, 0, 0, 0)
        cwd_layout.setSpacing(6)

        cwd_icon = QLabel("📂")
        cwd_icon.setStyleSheet("font-size: 12px; background: transparent;")
        cwd_layout.addWidget(cwd_icon)

        cwd_text = self._cwd or "—"
        cwd_label = QLabel(cwd_text)
        cwd_label.setObjectName("CwdLabel")
        cwd_label.setStyleSheet(f"""
            #CwdLabel {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                background: transparent;
                font-family: 'Menlo', 'Consolas', monospace;
            }}
        """)
        cwd_label.setWordWrap(False)
        cwd_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cwd_layout.addWidget(cwd_label, stretch=1)

        layout.addWidget(cwd_widget, stretch=1)

        # ── Risque ──
        badge = self._build_risk_badge(self._risk_category)
        layout.addWidget(badge)

        # ── Niveau de risque (progress-like) ──
        level_widget = QWidget()
        level_layout = QHBoxLayout(level_widget)
        level_layout.setContentsMargins(0, 0, 0, 0)
        level_layout.setSpacing(4)

        level_icon = QLabel("⚡")
        level_icon.setStyleSheet("font-size: 11px; background: transparent;")
        level_layout.addWidget(level_icon)

        # Barre de niveau colorée
        level_value = min(max(self._risk_level, 0), 10)
        bar_color = self._risk_color(self._risk_level)
        bar_blocks = "■" * level_value + "□" * (10 - level_value)
        level_label = QLabel(f"{level_value}/10")
        level_label.setStyleSheet(
            f"color: {bar_color}; font-size: 11px; font-weight: 700;"
            f" background: transparent; font-family: monospace;"
        )
        level_layout.addWidget(level_label)

        layout.addWidget(level_widget)

        # ── Timeout (simulé, statique) ──
        timeout_widget = QWidget()
        timeout_layout = QHBoxLayout(timeout_widget)
        timeout_layout.setContentsMargins(0, 0, 0, 0)
        timeout_layout.setSpacing(4)

        timeout_icon = QLabel("⏱️")
        timeout_icon.setStyleSheet("font-size: 11px; background: transparent;")
        timeout_layout.addWidget(timeout_icon)

        timeout_label = QLabel("30s")
        timeout_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;"
            f" font-family: monospace;"
        )
        timeout_layout.addWidget(timeout_label)

        layout.addWidget(timeout_widget)

        return container

    def _build_risk_badge(self, category: str) -> QLabel:
        """Badge de catégorie de risque avec icône et couleur.

        Args:
            category: Catégorie parmi SAFE, READ, WRITE, DESTRUCTIVE, NETWORK, INSTALL.

        Returns:
            QLabel formaté avec fond coloré.
        """
        cat = category.upper() if category else "SAFE"
        color = RISK_COLORS.get(cat, TEXT_SECONDARY)
        icon = RISK_ICONS.get(cat, "❓")
        label = RISK_LABELS.get(cat, cat)

        badge = QLabel(f"{icon} {label}")
        badge.setObjectName(f"RiskBadge_{cat}")
        badge.setStyleSheet(f"""
            #RiskBadge_{cat} {{
                color: {color};
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid {color};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 700;
            }}
        """)
        return badge

    def _build_buttons(self) -> QWidget:
        """Barre de boutons d'action."""
        container = QWidget()
        container.setObjectName("ButtonBar")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        # Bouton "Voir détail" (dry-run expandable)
        self._detail_btn = QPushButton("🔍  Voir détail")
        self._detail_btn.setObjectName("DetailBtn")
        self._detail_btn.setCursor(Qt.PointingHandCursor)
        self._detail_btn.setStyleSheet(f"""
            #DetailBtn {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_ACCENT};
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            #DetailBtn:hover {{
                background: rgba(255, 255, 255, 0.05);
                color: {TEXT_PRIMARY};
                border-color: {TEXT_SECONDARY};
            }}
            #DetailBtn:pressed {{
                background: rgba(255, 255, 255, 0.08);
            }}
        """)
        self._detail_btn.clicked.connect(self._on_toggle_detail)
        layout.addWidget(self._detail_btn)

        layout.addStretch()

        # Bouton "Refuser"
        self._reject_btn = QPushButton("❌  Refuser")
        self._reject_btn.setObjectName("RejectBtn")
        self._reject_btn.setCursor(Qt.PointingHandCursor)
        self._reject_btn.setStyleSheet(f"""
            #RejectBtn {{
                background: rgba(248, 113, 113, 0.15);
                color: {COLOR_DANGER};
                border: 1px solid {COLOR_DANGER};
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 700;
            }}
            #RejectBtn:hover {{
                background: rgba(248, 113, 113, 0.25);
            }}
            #RejectBtn:pressed {{
                background: rgba(248, 113, 113, 0.35);
            }}
        """)
        self._reject_btn.clicked.connect(self._on_reject)
        layout.addWidget(self._reject_btn)

        # Bouton "Approuver"
        self._approve_btn = QPushButton("✅  Approuver")
        self._approve_btn.setObjectName("ApproveBtn")
        self._approve_btn.setCursor(Qt.PointingHandCursor)
        self._approve_btn.setDefault(True)
        self._approve_btn.setStyleSheet(f"""
            #ApproveBtn {{
                background: {ACCENT_CYAN};
                color: {BG_DARK};
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 700;
            }}
            #ApproveBtn:hover {{
                background: #33DDFF;
            }}
            #ApproveBtn:pressed {{
                background: #00B8E6;
            }}
        """)
        self._approve_btn.clicked.connect(self._on_approve)
        layout.addWidget(self._approve_btn)

        return container

    def _build_detail_panel(self) -> QFrame:
        """Panneau dépliable avec le dry-run output."""
        panel = QFrame()
        panel.setObjectName("DetailPanel")
        panel.setStyleSheet(f"""
            #DetailPanel {{
                background: {BG_SURFACE};
                border: 1px solid {BORDER_ACCENT};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Titre du panneau
        detail_title = QLabel("📋  Dry-run output")
        detail_title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;"
            f" background: transparent; letter-spacing: 0.5px;"
        )
        layout.addWidget(detail_title)

        # Zone de texte pour le dry-run
        self._detail_edit = QTextEdit()
        self._detail_edit.setObjectName("DryRunOutput")
        self._detail_edit.setPlainText(self._dry_run or "Aucun détail disponible.")
        self._detail_edit.setReadOnly(True)
        self._detail_edit.setStyleSheet(f"""
            #DryRunOutput {{
                background: rgba(0, 0, 0, 0.3);
                color: {TEXT_SECONDARY};
                border: none;
                font-family: 'Menlo', 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                padding: 6px;
                selection-background-color: {ACCENT_CYAN};
                selection-color: {BG_DARK};
            }}
        """)
        self._detail_edit.setMinimumHeight(60)
        self._detail_edit.setMaximumHeight(180)
        self._detail_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._detail_edit.setTabChangesFocus(False)
        layout.addWidget(self._detail_edit)

        return panel

    # ── Handlers ────────────────────────────────────────────────────

    def _on_approve(self) -> None:
        """Valide la commande et ferme le dialogue avec accept()."""
        logger.debug(
            "Shell command approved | request=%s | category=%s | level=%d",
            self._request_id,
            self._risk_category,
            self._risk_level,
        )
        self.accept()

    def _on_reject(self) -> None:
        """Refuse la commande et ferme le dialogue avec reject()."""
        logger.debug(
            "Shell command rejected | request=%s | category=%s | level=%d",
            self._request_id,
            self._risk_category,
            self._risk_level,
        )
        self.reject()

    def _on_toggle_detail(self) -> None:
        """Bascule la visibilité du panneau dry-run avec animation."""
        self._detail_visible = not self._detail_visible
        self._detail_panel.setVisible(self._detail_visible)

        if self._detail_visible:
            self._detail_btn.setText("🔍  Masquer détail")
            # Remplir le contenu si absent
            if not self._dry_run:
                self._detail_edit.setPlainText("Aucun détail disponible.")
            self.adjustSize()
        else:
            self._detail_btn.setText("🔍  Voir détail")
            self.adjustSize()

    # ── API publique ────────────────────────────────────────────────

    def set_dry_run_output(self, text: str) -> None:
        """Définit le texte du dry-run output.

        Args:
            text: Texte à afficher dans le panneau détail.
        """
        self._dry_run = text
        if hasattr(self, "_detail_edit"):
            self._detail_edit.setPlainText(text)

    def decision_result(self) -> dict:
        """Retourne le résultat structuré de la décision.

        À appeler après exec() (ou après accept/reject).

        Returns:
            dict avec les clés :
            - approved (bool): True si approuvé, False si refusé
            - request_id (str): Identifiant unique de la requête
            - timestamp (float): Timestamp Unix de la décision
        """
        return {
            "approved": self.result() == QDialog.DialogCode.Accepted,
            "request_id": self._request_id,
            "timestamp": time.time(),
        }

    # ── Helpers internes ────────────────────────────────────────────

    def _center_on_parent(self) -> None:
        """Centre le dialogue sur son parent."""
        if self.parent() is None:
            return
        parent_rect = self.parent().geometry()
        dialog_rect = self.geometry()
        x = parent_rect.x() + (parent_rect.width() - dialog_rect.width()) // 2
        y = parent_rect.y() + (parent_rect.height() - dialog_rect.height()) // 2
        self.move(x, y)

    @staticmethod
    def _risk_color(level: int) -> str:
        """Retourne une couleur hex en fonction du niveau de risque."""
        if level <= 3:
            return COLOR_SAFE
        elif level <= 6:
            return COLOR_WARNING
        elif level <= 8:
            return COLOR_DANGER
        else:
            return "#EF4444"  # Rouge vif pour très risqué
