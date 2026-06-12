"""
AgentStatusWidget — État de l'agent en temps réel pour NURU Dashboard V9.

Affiche : état (idle/planning/executing/verifying/done/error),
objectif en cours, plan d'étapes, progression, étape courante.

Design cyberpunk NURU : fond sombre, accents cyan/vert.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QWidget,
    QSizePolicy,
)

# ── Constantes de thème cyberpunk NURU ──────────────────────────────────────

BG_DARK = "#0D1117"
BG_PANEL = "#161b22"
ACCENT_BLUE = "#00A3FF"
ACCENT_GREEN = "#39FF14"
ACCENT_ORANGE = "#FF8C00"
ACCENT_RED = "#FF3333"
ACCENT_PURPLE = "#A855F7"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"

PANEL_STYLE = f"background-color: {BG_PANEL}; border-radius: 8px; padding: 12px;"

# ── Constantes de mapping d'état ───────────────────────────────────────────

AGENT_STATE_LABELS: dict[str, str] = {
    "idle": "⚪ Prêt — en attente de tâche",
    "planning": "🔵 Planification",
    "executing": "🟢 Exécution",
    "verifying": "🟡 Vérification",
    "done": "✅ Terminé",
    "error": "🔴 Erreur",
}

AGENT_STATE_COLORS: dict[str, str] = {
    "idle": TEXT_SECONDARY,
    "planning": ACCENT_BLUE,
    "executing": ACCENT_GREEN,
    "verifying": ACCENT_ORANGE,
    "done": ACCENT_GREEN,
    "error": ACCENT_RED,
}

AGENT_STATE_ORDER: list[str] = [
    "idle", "planning", "executing", "verifying", "done", "error",
]


def format_plan_step(step: str, index: int, total: int, is_current: bool = False) -> str:
    """Formate une étape de plan pour affichage.

    Args:
        step: Description textuelle de l'étape.
        index: Index de l'étape (0-based).
        total: Nombre total d'étapes.
        is_current: Si True, l'étape est en cours.

    Returns:
        Chaine formatée : "N/M • étape" avec indicateur si en cours.
    """
    prefix = f"{index + 1}/{total}"
    marker = "→ " if is_current else "  "
    return f"{marker}{prefix} • {step}"


def compute_progress(step_index: int, total_steps: int) -> float:
    """Calcule le pourcentage de progression.

    Args:
        step_index: Index de l'étape actuelle (0-based, -1 si idle/error).
        total_steps: Nombre total d'étapes.

    Returns:
        Pourcentage entre 0.0 et 1.0.
    """
    if total_steps <= 0:
        return 0.0
    if step_index < 0:
        return 0.0
    return min(1.0, (step_index + 1) / total_steps)


def state_label(state: str) -> str:
    """Retourne le libellé affichable pour un état donné.

    Args:
        state: Identifiant de l'état (idle, planning, executing, etc.)

    Returns:
        Libellé formaté avec emoji.
    """
    return AGENT_STATE_LABELS.get(state, f"❓ {state.capitalize()}")


def state_color(state: str) -> str:
    """Retourne la couleur hex associée à un état.

    Args:
        state: Identifiant de l'état.

    Returns:
        Code hex couleur.
    """
    return AGENT_STATE_COLORS.get(state, TEXT_SECONDARY)


# ── Widget principal ───────────────────────────────────────────────────────


class AgentStatusWidget(QFrame):
    """Affiche l'état de l'agent en temps réel.

    États supportés : idle | planning | executing | verifying | done | error.
    Affiche l'objectif en cours, un plan d'étapes, une barre de progression,
    et l'étape courante mise en évidence.

    Si aucun état n'est fourni, affiche "Agent inactif".
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("AgentStatusWidget")
        self.setStyleSheet(f"#AgentStatusWidget {{ {PANEL_STYLE} }}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._state: str = "idle"
        self._objective: str = ""
        self._steps: list[str] = []
        self._current_step_index: int = -1

        # ── Layout principal ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # ── En-tête : icône état + objectif ──
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self._state_icon = QLabel("⚪")
        self._state_icon.setFixedWidth(24)
        self._state_icon.setAlignment(Qt.AlignCenter)
        self._state_icon.setStyleSheet("font-size: 16px;")
        header_layout.addWidget(self._state_icon)

        self._state_label = QLabel("Prêt — en attente de tâche")
        self._state_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold;"
        )
        header_layout.addWidget(self._state_label)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # ── Objectif ──
        self._objective_label = QLabel()
        self._objective_label.setWordWrap(True)
        self._objective_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; padding-left: 32px;"
        )
        self._objective_label.setVisible(False)
        layout.addWidget(self._objective_label)

        # ── Barre de progression ──
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: rgba(255,255,255,0.06);
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {ACCENT_BLUE};
                border-radius: 2px;
            }}
            """
        )
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # ── Conteneur d'étapes (plan) ──
        self._steps_container = QVBoxLayout()
        self._steps_container.setSpacing(3)
        self._steps_container.setContentsMargins(32, 4, 0, 0)
        layout.addLayout(self._steps_container)

        # ── État initial ──
        self.set_idle()

    # ── API publique ─────────────────────────────────────────────────────

    def update_state(self, agent_state: dict) -> None:
        """Met à jour l'affichage depuis un dictionnaire AgentState.

        Le dictionnaire peut contenir :
            - state (str) : identifiant d'état
            - objective (str) : objectif en cours
            - steps (list[str]) : liste des étapes du plan
            - current_step (int) : index de l'étape courante (0-based)
        """
        state = agent_state.get("state", "idle")
        objective = agent_state.get("objective", "")
        steps = agent_state.get("steps", [])
        current_step = agent_state.get("current_step", -1)

        self._state = state
        self._objective = objective
        self._steps = list(steps)
        self._current_step_index = current_step

        self._render()

    def set_idle(self) -> None:
        """Remet à l'état inactif."""
        self._state = "idle"
        self._objective = ""
        self._steps = []
        self._current_step_index = -1
        self._render()

    def clear(self) -> None:
        """Vide complètement l'affichage."""
        self._state = "idle"
        self._objective = ""
        self._steps = []
        self._current_step_index = -1
        self._state_label.clear()
        self._state_icon.setText("")
        self._objective_label.setVisible(False)
        self._objective_label.clear()
        self._progress_bar.setVisible(False)
        self._progress_bar.setValue(0)
        self._clear_steps()

    # ── Affichage ────────────────────────────────────────────────────────

    def _render(self) -> None:
        """Re-rend l'intégralité du widget à partir de l'état interne."""
        # État + icône
        label = state_label(self._state)
        color = state_color(self._state)

        self._state_label.setText(label)
        self._state_label.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: bold;"
        )

        # Objectif
        if self._objective:
            self._objective_label.setText(f"🎯 {self._objective}")
            self._objective_label.setVisible(True)
        else:
            self._objective_label.setVisible(False)

        # Progression
        has_plan = len(self._steps) > 0 and self._state not in ("idle", "error")
        if has_plan:
            progress = compute_progress(self._current_step_index, len(self._steps))
            self._progress_bar.setValue(int(progress * 100))
            self._progress_bar.setVisible(True)
        else:
            self._progress_bar.setVisible(False)
            self._progress_bar.setValue(0)

        # Étapes
        self._render_steps()

    def _render_steps(self) -> None:
        """Affiche ou masque la liste des étapes du plan."""
        self._clear_steps()

        if not self._steps or self._state in ("idle", "error"):
            return

        for i, step in enumerate(self._steps):
            is_current = (i == self._current_step_index)
            formatted = format_plan_step(step, i, len(self._steps), is_current)

            step_label = QLabel(formatted)
            if is_current:
                step_label.setStyleSheet(
                    f"color: {ACCENT_BLUE}; font-size: 11px; font-weight: bold; "
                    f"background-color: rgba(0, 163, 255, 0.08); "
                    f"border-radius: 4px; padding: 2px 6px;"
                )
            else:
                done = i < self._current_step_index
                c = ACCENT_GREEN if done else TEXT_SECONDARY
                step_label.setStyleSheet(
                    f"color: {c}; font-size: 11px; padding: 2px 6px;"
                )

            self._steps_container.addWidget(step_label)

    def _clear_steps(self) -> None:
        """Supprime tous les labels d'étapes du conteneur."""
        while self._steps_container.count():
            item = self._steps_container.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
