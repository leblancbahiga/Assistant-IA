"""V11.1 P0-G — StatCard unifié.

Remplace MetricCard (right_panel), StatCard (feedback_page), StatCard (stats_page).
Style Aether Dashboard sombre, compatible theme existant.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

# ── Constantes de style (copiées de right_panel.py pour autonomie) ──
ACCENT_BLUE = "#1A6A9A"
TEXT_PRIMARY = "#E8EAF0"
TEXT_SECONDARY = "#4A6080"
TEXT_DIM = "#2D4052"
CARD_BG = "rgba(10, 14, 20, 0.9)"
CARD_BORDER = "#1A2332"


class StatCard(QFrame):
    """Carte métrique unifiée, style Aether sombre.

    Paramètres
    ----------
    title : str
        Libellé de la métrique (affiché en haut, < 1em, uppercase).
    value : str, optional
        Valeur initiale (grand texte coloré).
    icon : str, optional
        Émoji ou icône textuelle (par défaut "◆").
    color : str, optional
        Couleur hex de l'icône et de la valeur.
    parent : QWidget, optional

    Signaux
    -------
    Aucun (composant passif).

    Exemple
    -------
        card = StatCard(title="Tokens", value="12.4k", icon="📊", color="#60a5fa")
        card.set_value("15.1k", color="#22c55e")
    """

    def __init__(
        self,
        title: str = "",
        icon: str = "◆",
        value: str = "—",
        color: str = ACCENT_BLUE,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self._color = color
        self._icon_str = icon
        self._title_str = title

        # Carte arrondie, fond semi-transparent
        self.setStyleSheet(f"""
            #StatCard {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 8px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # ── Header (icône + titre) ──
        header = QHBoxLayout()
        header.setSpacing(6)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setStyleSheet(
            f"color: {color}; font-size: 14px; background: transparent;"
        )
        header.addWidget(self._icon_lbl)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 9px; font-weight: bold;"
            f" letter-spacing: 0.8px; background: transparent;"
        )
        header.addWidget(self._title_lbl)
        header.addStretch()
        layout.addLayout(header)

        # ── Valeur ──
        self._value_lbl = QLabel(value)
        self._value_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._update_value_style()
        layout.addWidget(self._value_lbl)

    # ── API publique ──

    def set_value(self, value: str, color: str | None = None) -> None:
        """Met à jour la valeur affichée et optionnellement la couleur."""
        self._value_lbl.setText(value)
        if color is not None:
            self._color = color
            self._icon_lbl.setStyleSheet(
                f"color: {color}; font-size: 14px; background: transparent;"
            )
            self._update_value_style()

    def set_title(self, title: str) -> None:
        """Met à jour le titre."""
        self._title_str = title
        self._title_lbl.setText(title)

    # ── Internes ──

    def _update_value_style(self) -> None:
        self._value_lbl.setStyleSheet(
            f"color: {self._color}; font-size: 22px; font-weight: 700;"
            f" background: transparent;"
        )

    def __repr__(self) -> str:
        return (
            f"StatCard(title={self._title_str!r}, "
            f"value={self._value_lbl.text()!r}, color={self._color!r})"
        )


# ── mini version compacte (MetricCard legacy compat) ──


class MiniStatCard(QWidget):
    """Carte métrique compacte (62px fixe) pour grilles denses.

    Correspond à l'ancien MetricCard de right_panel.py.
    """

    def __init__(
        self,
        label: str = "",
        value: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFixedHeight(62)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._label_w = QLabel(label)
        self._label_w.setStyleSheet(
            "font-size: 9px; color: #2D4052; letter-spacing: 0.10em;"
            " text-transform: uppercase; background: transparent;"
        )
        layout.addWidget(self._label_w)

        self._value_w = QLabel(value)
        self._value_w.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #E8EAF0;"
            " background: transparent;"
        )
        layout.addWidget(self._value_w)

        self._subtitle_w = QLabel(subtitle)
        self._subtitle_w.setStyleSheet(
            "font-size: 10px; color: #4A6080; background: transparent;"
        )
        self._subtitle_w.setVisible(bool(subtitle))
        layout.addWidget(self._subtitle_w)

    # ── API publique (compat MetricCard) ──

    def set_value(self, value: str) -> None:
        """Met à jour la valeur."""
        self._value_w.setText(value)

    def set_subtitle(self, subtitle: str) -> None:
        """Met à jour le sous-titre."""
        self._subtitle_w.setText(subtitle)
        self._subtitle_w.setVisible(bool(subtitle))

    def set_label(self, label: str) -> None:
        """Met à jour le label."""
        self._label_w.setText(label)
