"""
FeedbackBar — Barre de feedback sous chaque réponse pour NURU Dashboard V9.

Boutons : 👍 (positif), 👎 (négatif), ✏️ (correction).
Émet des signaux avec le message_id pour liaison au ViewModel.

Design cyberpunk NURU.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QSizePolicy,
    QLineEdit,
)

# ── Constantes de thème ────────────────────────────────────────────────────

BG_PANEL = "#161b22"
ACCENT_BLUE = "#00A3FF"
ACCENT_GREEN = "#39FF14"
ACCENT_RED = "#FF3333"
ACCENT_ORANGE = "#FF8C00"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"

BTN_BASE_STYLE = (
    "QPushButton {"
    "  background-color: rgba(255,255,255,0.04);"
    "  color: #6B7280;"
    "  border: 1px solid rgba(255,255,255,0.08);"
    "  border-radius: 6px;"
    "  font-size: 14px;"
    "}"
    "QPushButton:hover {"
    "  background-color: rgba(127,119,221,0.15);"
    "  color: #7f77dd;"
    "  border: 1px solid rgba(127,119,221,0.3);"
    "}"
)

BTN_ACTIVE_POSITIVE = (
    "QPushButton {"
    "  background-color: rgba(57,255,20,0.12);"
    "  color: #39FF14;"
    "  border: 1px solid rgba(57,255,20,0.4);"
    "  border-radius: 6px;"
    "  font-size: 14px;"
    "}"
)

BTN_ACTIVE_NEGATIVE = (
    "QPushButton {"
    "  background-color: rgba(255,51,51,0.12);"
    "  color: #FF3333;"
    "  border: 1px solid rgba(255,51,51,0.4);"
    "  border-radius: 6px;"
    "  font-size: 14px;"
    "}"
)

BTN_ACTIVE_CORRECTION = (
    "QPushButton {"
    "  background-color: rgba(255,140,0,0.12);"
    "  color: #FF8C00;"
    "  border: 1px solid rgba(255,140,0,0.4);"
    "  border-radius: 6px;"
    "  font-size: 14px;"
    "}"
)


def feedback_btn_style(feedback_type: str, active: bool = False) -> str:
    """Génère le stylesheet pour un bouton de feedback.

    Args:
        feedback_type: "positive", "negative", ou "correction".
        active: Si True, retourne le style actif.

    Returns:
        Chaine de style QSS.
    """
    if not active:
        return BTN_BASE_STYLE
    styles = {
        "positive": BTN_ACTIVE_POSITIVE,
        "negative": BTN_ACTIVE_NEGATIVE,
        "correction": BTN_ACTIVE_CORRECTION,
    }
    return styles.get(feedback_type, BTN_BASE_STYLE)


# ── Widget principal ───────────────────────────────────────────────────────


class FeedbackBar(QFrame):
    """Barre de feedback sous chaque réponse.

    Propose trois actions :
        👍 — feedback positif
        👎 — feedback négatif
        ✏️ — ouvrir un champ de correction

    Signaux :
        feedback_positive(message_id) — émis quand 👍 est cliqué
        feedback_negative(message_id) — émis quand 👎 est cliqué
        feedback_correction(message_id, correction) — émis quand une correction est soumise

    L'appelant doit connecter ces signaux au ViewModel pour la persistance.
    """

    feedback_positive = Signal(str)  # message_id
    feedback_negative = Signal(str)  # message_id
    feedback_correction = Signal(str, str)  # message_id, correction

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("FeedbackBar")
        self.setStyleSheet(
            f"#FeedbackBar {{ background-color: transparent; }}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setFixedHeight(36)

        self._message_id: str = ""
        self._enabled: bool = True
        self._active_feedback: str = ""  # "positive", "negative", "correction", ""
        self._correction_active: bool = False

        # ── Layout principal ──
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Bouton 👍 ──
        self._btn_positive = QPushButton("👍")
        self._btn_positive.setObjectName("FeedbackBtnPositive")
        self._btn_positive.setFixedSize(30, 30)
        self._btn_positive.setCursor(Qt.PointingHandCursor)
        self._btn_positive.setToolTip("Réponse utile")
        self._btn_positive.setStyleSheet(BTN_BASE_STYLE)
        self._btn_positive.clicked.connect(self._on_positive)
        layout.addWidget(self._btn_positive)

        # ── Bouton 👎 ──
        self._btn_negative = QPushButton("👎")
        self._btn_negative.setObjectName("FeedbackBtnNegative")
        self._btn_negative.setFixedSize(30, 30)
        self._btn_negative.setCursor(Qt.PointingHandCursor)
        self._btn_negative.setToolTip("Pas utile")
        self._btn_negative.setStyleSheet(BTN_BASE_STYLE)
        self._btn_negative.clicked.connect(self._on_negative)
        layout.addWidget(self._btn_negative)

        # ── Bouton ✏️ (correction) ──
        self._btn_correction = QPushButton("✏️")
        self._btn_correction.setObjectName("FeedbackBtnCorrection")
        self._btn_correction.setFixedSize(30, 30)
        self._btn_correction.setCursor(Qt.PointingHandCursor)
        self._btn_correction.setToolTip("Proposer une correction")
        self._btn_correction.setStyleSheet(BTN_BASE_STYLE)
        self._btn_correction.clicked.connect(self._on_correction)
        layout.addWidget(self._btn_correction)

        layout.addStretch()

        # ── Champ de correction (caché par défaut) ──
        self._correction_input = QLineEdit()
        self._correction_input.setObjectName("FeedbackCorrectionInput")
        self._correction_input.setPlaceholderText("✏️ Saisissez votre correction...")
        self._correction_input.setStyleSheet(
            f"""
            #FeedbackCorrectionInput {{
                background-color: rgba(255,255,255,0.04);
                color: {TEXT_PRIMARY};
                border: 1px solid rgba(255,140,0,0.4);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                min-height: 22px;
            }}
            #FeedbackCorrectionInput:focus {{
                border: 1px solid {ACCENT_ORANGE};
            }}
            """
        )
        self._correction_input.setVisible(False)
        self._correction_input.returnPressed.connect(self._submit_correction)
        layout.addWidget(self._correction_input)

    # ── API publique ─────────────────────────────────────────────────────

    def set_message_id(self, message_id: str) -> None:
        """Associe un identifiant de message à cette barre.

        Args:
            message_id: Identifiant unique du message.
        """
        self._message_id = message_id

    def set_feedback_enabled(self, enabled: bool) -> None:
        """Active ou désactive les boutons de feedback.

        Args:
            enabled: True pour activer, False pour désactiver.
        """
        self._enabled = enabled
        for btn in (self._btn_positive, self._btn_negative, self._btn_correction):
            btn.setEnabled(enabled)

    def highlight_feedback(self, feedback_type: str) -> None:
        """Applique un style visuel après avoir cliqué sur un bouton.

        Args:
            feedback_type: "positive", "negative", "correction", ou "" pour reset.
        """
        # Reset all
        self._btn_positive.setStyleSheet(BTN_BASE_STYLE)
        self._btn_negative.setStyleSheet(BTN_BASE_STYLE)
        self._btn_correction.setStyleSheet(BTN_BASE_STYLE)

        if feedback_type == "positive":
            self._btn_positive.setStyleSheet(feedback_btn_style("positive", active=True))
        elif feedback_type == "negative":
            self._btn_negative.setStyleSheet(feedback_btn_style("negative", active=True))
        elif feedback_type == "correction":
            self._btn_correction.setStyleSheet(feedback_btn_style("correction", active=True))

        self._active_feedback = feedback_type

    # ── Handlers internes ────────────────────────────────────────────────

    def _on_positive(self) -> None:
        if not self._enabled or not self._message_id:
            return
        self.highlight_feedback("positive")
        self.feedback_positive.emit(self._message_id)

    def _on_negative(self) -> None:
        if not self._enabled or not self._message_id:
            return
        self.highlight_feedback("negative")
        self.feedback_negative.emit(self._message_id)

    def _on_correction(self) -> None:
        if not self._enabled:
            return
        if self._correction_active:
            # Masquer le champ
            self._correction_input.setVisible(False)
            self._correction_input.clear()
            self._correction_active = False
            return
        # Afficher le champ
        self._correction_input.setVisible(True)
        self._correction_input.setFocus()
        self._correction_active = True
        self.highlight_feedback("correction")

    def _submit_correction(self) -> None:
        text = self._correction_input.text().strip()
        if not text or not self._message_id:
            return
        self.feedback_correction.emit(self._message_id, text)
        # Reset UI
        self._correction_input.clear()
        self._correction_input.setVisible(False)
        self._correction_active = False
        self.highlight_feedback("correction")
