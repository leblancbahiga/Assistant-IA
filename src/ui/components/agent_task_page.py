"""
AgentTaskPage — Page unifiée fusionnant AgentStatusWidget + TaskListWidget.

Affiche en une seule vue scrollable :
  1. État de l'agent (en haut) — icône, objectif, progression, plan d'étapes
  2. Séparateur horizontal
  3. Liste des tâches (en bas) — compteur, filtres, cartes tâche

Design cyberpunk NURU P1-F : fond #0D1220, panels #121620, bordures #2A2A4E,
accent #3b82f6 / #818cf8.

États agent supportés : idle | planning | executing | verifying | done | error.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# ── Constantes de thème cyberpunk NURU (P1-F) ──────────────────────────────

BG_DARK = "#0D1220"
BG_PANEL = "#121620"
BORDER_COLOR = "#2A2A4E"
ACCENT_BLUE = "#3b82f6"
ACCENT_PURPLE = "#818cf8"
ACCENT_GREEN = "#39FF14"
ACCENT_ORANGE = "#FF8C00"
ACCENT_RED = "#FF3333"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"

PANEL_STYLE = f"""
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
"""

# ── Constantes agent ───────────────────────────────────────────────────────

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

# ── Constantes tâche ───────────────────────────────────────────────────────

TASK_STATUS_ICONS: dict[str, str] = {
    "in_progress": "🔄",
    "running": "🔄",
    "completed": "✅",
    "done": "✅",
    "interrupted": "⏸️",
    "paused": "⏸️",
    "cancelled": "❌",
    "canceled": "❌",
    "failed": "❌",
    "pending": "⏳",
    "queued": "⏳",
}

TASK_STATUS_LABELS: dict[str, str] = {
    "in_progress": "En cours",
    "running": "En cours",
    "completed": "Terminée",
    "done": "Terminée",
    "interrupted": "Interrompue",
    "paused": "En pause",
    "cancelled": "Annulée",
    "canceled": "Annulée",
    "failed": "Échouée",
    "pending": "En attente",
    "queued": "En attente",
}

TASK_STATUS_COLORS: dict[str, str] = {
    "in_progress": ACCENT_BLUE,
    "running": ACCENT_BLUE,
    "completed": ACCENT_GREEN,
    "done": ACCENT_GREEN,
    "interrupted": ACCENT_ORANGE,
    "paused": ACCENT_ORANGE,
    "cancelled": ACCENT_RED,
    "canceled": ACCENT_RED,
    "failed": ACCENT_RED,
    "pending": TEXT_SECONDARY,
    "queued": TEXT_SECONDARY,
}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _agent_state_label(state: str) -> str:
    return AGENT_STATE_LABELS.get(state, f"❓ {state.capitalize()}")


def _agent_state_color(state: str) -> str:
    return AGENT_STATE_COLORS.get(state, TEXT_SECONDARY)


def _compute_progress(step_index: int, total_steps: int) -> float:
    if total_steps <= 0 or step_index < 0:
        return 0.0
    return min(1.0, (step_index + 1) / total_steps)


def _task_status_icon(status: str) -> str:
    return TASK_STATUS_ICONS.get(status.lower(), "📋")


def _task_status_label(status: str) -> str:
    return TASK_STATUS_LABELS.get(status.lower(), status.capitalize())


def _task_status_color(status: str) -> str:
    return TASK_STATUS_COLORS.get(status.lower(), TEXT_SECONDARY)


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    secs = max(0, int(seconds))
    hours, remainder = divmod(secs, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts) if parts else "0s"


def _task_progress_text(progress: float | int | None) -> str:
    if progress is None:
        return "—"
    try:
        pct = max(0.0, min(1.0, float(progress))) * 100
        return f"{int(pct)}%"
    except (ValueError, TypeError):
        return "—"


# ── AgentTaskPage ──────────────────────────────────────────────────────────


class AgentTaskPage(QScrollArea):
    """Page unifiée : statut agent + liste des tâches.

    Signaux
    -------
    resume_task(str) : émis quand l'utilisateur clique \"Reprendre\" sur une tâche.
    cancel_task(str) : émis quand l'utilisateur clique \"Annuler\" sur une tâche.
    """

    resume_task = Signal(str)
    cancel_task = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AgentTaskPage")
        self.setWidgetResizable(True)
        self.setStyleSheet(
            f"#AgentTaskPage {{ background-color: {BG_DARK}; border: none; }}"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {ACCENT_PURPLE}; "
            "border-radius: 2px; min-height: 20px; }"
        )

        # ── Données internes ──
        self._tasks: list[dict[str, Any]] = []
        self._filter_mode: str = "all"  # all | active | done

        # ── Widget conteneur ──
        container = QWidget()
        container.setObjectName("AgentTaskPageContainer")
        container.setStyleSheet(f"#AgentTaskPageContainer {{ background: transparent; }}")
        self._root = QVBoxLayout(container)
        self._root.setContentsMargins(20, 20, 20, 20)
        self._root.setSpacing(16)

        self.setWidget(container)

        # ── Construire les sections ──
        self._build_agent_section()
        self._build_divider()
        self._build_tasks_section()

        self._root.addStretch()

    # ── Construction Agent (section haut) ─────────────────────────────────

    def _build_agent_section(self) -> None:
        """Construit le bloc d'état de l'agent."""
        self._agent_frame = QFrame()
        self._agent_frame.setObjectName("AgentSectionFrame")
        self._agent_frame.setStyleSheet(
            f"#AgentSectionFrame {{ {PANEL_STYLE} }}"
        )

        layout = QVBoxLayout(self._agent_frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # ── Titre section ──
        section_title = QLabel("🤖 Agent")
        section_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        layout.addWidget(section_title)

        # ── En-tête : icône état + texte ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self._state_icon = QLabel("⚪")
        self._state_icon.setFixedWidth(24)
        self._state_icon.setAlignment(Qt.AlignCenter)
        self._state_icon.setStyleSheet("font-size: 16px; background: transparent;")
        header_row.addWidget(self._state_icon)

        self._state_label = QLabel("Prêt — en attente de tâche")
        self._state_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold; "
            "background: transparent;"
        )
        header_row.addWidget(self._state_label)

        header_row.addStretch()
        layout.addLayout(header_row)

        # ── Objectif ──
        self._objective_label = QLabel()
        self._objective_label.setWordWrap(True)
        self._objective_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; padding-left: 32px; "
            "background: transparent;"
        )
        self._objective_label.setVisible(False)
        layout.addWidget(self._objective_label)

        # ── Barre de progression agent ──
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(
            "QProgressBar {"
            "  background-color: rgba(255,255,255,0.06);"
            "  border: none; border-radius: 2px;"
            "}"
            f"QProgressBar::chunk {{ background-color: {ACCENT_BLUE}; "
            "border-radius: 2px; }"
        )
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # ── Conteneur d'étapes du plan ──
        self._steps_container = QVBoxLayout()
        self._steps_container.setSpacing(3)
        self._steps_container.setContentsMargins(32, 4, 0, 0)
        layout.addLayout(self._steps_container)

        self._root.addWidget(self._agent_frame)

    # ── Divider ──────────────────────────────────────────────────────────

    def _build_divider(self) -> None:
        """Construit le séparateur horizontal entre agent et tâches."""
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        divider.setStyleSheet(
            f"background-color: {BORDER_COLOR}; max-height: 1px; border: none;"
        )
        self._root.addWidget(divider)

    # ── Construction Tâches (section bas) ────────────────────────────────

    def _build_tasks_section(self) -> None:
        """Construit le bloc de liste des tâches."""
        self._tasks_frame = QFrame()
        self._tasks_frame.setObjectName("TasksSectionFrame")
        self._tasks_frame.setStyleSheet(
            f"#TasksSectionFrame {{ {PANEL_STYLE} }}"
        )

        layout = QVBoxLayout(self._tasks_frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # ── En-tête : titre + compteur + filtres ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title = QLabel("📋 Tâches")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold; "
            "background: transparent;"
        )
        header_row.addWidget(title)

        self._count_label = QLabel("0")
        self._count_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            f"background: rgba(255,255,255,0.04); padding: 2px 8px; "
            "border-radius: 4px;"
        )
        header_row.addWidget(self._count_label)

        header_row.addStretch()

        # ── Filtres ──
        self._filter_btns: dict[str, QPushButton] = {}
        for f_key, f_label in [("all", "Toutes"), ("active", "En cours"), ("done", "Terminées")]:
            btn = QPushButton(f_label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _checked=False, mode=f_key: self._set_filter(mode))
            self._filter_btns[f_key] = btn
            header_row.addWidget(btn)

        # Bouton "Nettoyer"
        self._clear_completed_btn = QPushButton("Nettoyer")
        self._clear_completed_btn.setCursor(Qt.PointingHandCursor)
        self._clear_completed_btn.setStyleSheet(
            "QPushButton { background: transparent; "
            f"color: {TEXT_SECONDARY}; "
            f"border: 1px solid {BORDER_COLOR}; "
            "border-radius: 4px; padding: 2px 8px; font-size: 10px; }"
            f"QPushButton:hover {{ color: {ACCENT_GREEN}; "
            "border: 1px solid rgba(57,255,20,0.3); }"
        )
        self._clear_completed_btn.clicked.connect(self.clear_completed)
        header_row.addWidget(self._clear_completed_btn)

        layout.addLayout(header_row)

        # ── Style des boutons de filtre ──
        self._update_filter_styles()

        # ── Zone de liste des tâches (scrollable interne) ──
        # Utilise un QScrollArea pour que la page extérieure ne scroll pas les tâches
        # mais on veut que les tâches soient dans le scroll de la page principale.
        # On utilise donc un simple layout avec une empty label.
        self._task_list_layout = QVBoxLayout()
        self._task_list_layout.setContentsMargins(0, 0, 0, 0)
        self._task_list_layout.setSpacing(6)

        self._empty_label = QLabel("    Aucune tâche en cours.")
        self._empty_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; padding: 20px 0px; "
            "background: transparent;"
        )
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._task_list_layout.addWidget(self._empty_label)

        layout.addLayout(self._task_list_layout)

        self._root.addWidget(self._tasks_frame)

    # ── API publique ─────────────────────────────────────────────────────

    def set_state(self, state: str, goal: str = "",
                  plan: Optional[list[str]] = None,
                  step_index: int = -1) -> None:
        """Met à jour l'affichage de l'état de l'agent.

        Args:
            state: Identifiant d'état (idle, planning, executing, verifying, done, error).
            goal: Objectif en cours.
            plan: Liste des étapes du plan.
            step_index: Index de l'étape courante (0-based).
        """
        label = _agent_state_label(state)
        color = _agent_state_color(state)

        self._state_label.setText(label)
        self._state_label.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: bold; background: transparent;"
        )

        # Objectif
        if goal:
            self._objective_label.setText(f"🎯 {goal}")
            self._objective_label.setVisible(True)
        else:
            self._objective_label.setVisible(False)

        # Progression
        steps = plan or []
        has_plan = len(steps) > 0 and state not in ("idle", "error")
        if has_plan:
            progress = _compute_progress(step_index, len(steps))
            self._progress_bar.setValue(int(progress * 100))
            self._progress_bar.setVisible(True)
        else:
            self._progress_bar.setVisible(False)
            self._progress_bar.setValue(0)

        # Étapes du plan
        self._clear_steps()
        if has_plan:
            for i, step in enumerate(steps):
                is_current = (i == step_index)
                prefix = f"{i + 1}/{len(steps)}"
                marker = "→ " if is_current else "  "
                formatted = f"{marker}{prefix} • {step}"

                step_label = QLabel(formatted)
                if is_current:
                    step_label.setStyleSheet(
                        f"color: {ACCENT_BLUE}; font-size: 11px; font-weight: bold; "
                        f"background-color: rgba(59, 130, 246, 0.08); "
                        "border-radius: 4px; padding: 2px 6px;"
                    )
                else:
                    done = i < step_index
                    c = ACCENT_GREEN if done else TEXT_SECONDARY
                    step_label.setStyleSheet(
                        f"color: {c}; font-size: 11px; padding: 2px 6px;"
                    )
                self._steps_container.addWidget(step_label)

    def set_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Remplace toutes les tâches affichées.

        Args:
            tasks: Liste de dictionnaires de tâches.
        """
        self._tasks = list(tasks)
        self._rebuild_task_list()

    def add_task(self, task: dict[str, Any]) -> None:
        """Ajoute une tâche à la liste.

        Args:
            task: Dictionnaire de la tâche à ajouter.
        """
        self._tasks.append(task)
        self._rebuild_task_list()

    def update_task(self, task_id: str, status: str) -> None:
        """Met à jour le statut d'une tâche.

        Args:
            task_id: Identifiant de la tâche.
            status: Nouveau statut.
        """
        for task in self._tasks:
            if task.get("id") == task_id:
                task["status"] = status
                break
        self._rebuild_task_list()

    def remove_task(self, task_id: str) -> None:
        """Supprime une tâche de la liste.

        Args:
            task_id: Identifiant de la tâche à supprimer.
        """
        self._tasks = [t for t in self._tasks if t.get("id") != task_id]
        self._rebuild_task_list()

    def clear_completed(self) -> None:
        """Supprime toutes les tâches terminées/annulées."""
        completed_statuses = {"completed", "done", "cancelled", "canceled", "failed"}
        self._tasks = [
            t for t in self._tasks
            if t.get("status", "").lower() not in completed_statuses
        ]
        self._rebuild_task_list()

    def refresh(self) -> None:
        """Rafraîchit entièrement l'affichage (appelé lors du changement de page)."""
        self._rebuild_task_list()

    def set_core(self, core: Any) -> None:
        """Lien optionnel vers NuruCore pour récupérer des données temps réel.

        Args:
            core: Instance de NuruCore.
        """
        # Stocké pour usage futur — la connexion réelle sera implémentée
        # quand NuruCore sera disponible.
        self._core = core

    # ── Filtres ──────────────────────────────────────────────────────────

    def _set_filter(self, mode: str) -> None:
        """Change le filtre actif sur la liste des tâches.

        Args:
            mode: 'all', 'active', ou 'done'.
        """
        self._filter_mode = mode
        self._update_filter_styles()
        self._rebuild_task_list()

    def _update_filter_styles(self) -> None:
        """Met à jour le style des boutons de filtre selon le mode actif."""
        for mode, btn in self._filter_btns.items():
            active = mode == self._filter_mode
            btn.setChecked(active)
            if active:
                btn.setStyleSheet(
                    f"QPushButton {{ background: rgba(59, 130, 246, 0.15); "
                    f"color: {ACCENT_BLUE}; border: 1px solid {ACCENT_BLUE}; "
                    "border-radius: 4px; padding: 2px 10px; font-size: 10px; "
                    "font-weight: bold; }"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; "
                    f"border: 1px solid {BORDER_COLOR}; border-radius: 4px; "
                    "padding: 2px 10px; font-size: 10px; }"
                    f"QPushButton:hover {{ color: {TEXT_PRIMARY}; "
                    f"border: 1px solid {ACCENT_PURPLE}; }}"
                )

    # ── Reconstruction de la liste des tâches ────────────────────────────

    def _rebuild_task_list(self) -> None:
        """Reconstruit l'affichage des cartes tâche selon le filtre actif."""
        # Vider les anciennes cartes (tout sauf le label vide)
        self._clear_task_cards()

        # Filtrer
        filtered = self._filter_tasks(self._tasks)

        # Mise à jour compteur
        self._count_label.setText(str(len(filtered)))

        if not filtered:
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(False)

        # Trier : en cours d'abord, interrompues ensuite, terminées en dernier
        def _sort_key(t: dict[str, Any]) -> int:
            s = t.get("status", "pending").lower()
            if s in ("in_progress", "running"):
                return 0
            if s in ("interrupted", "paused"):
                return 1
            if s in ("pending", "queued"):
                return 2
            return 3

        sorted_tasks = sorted(filtered, key=_sort_key)

        for task in sorted_tasks:
            card = self._build_task_card(task)
            self._task_list_layout.addWidget(card)

    def _filter_tasks(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filtre les tâches selon le mode actif.

        Args:
            tasks: Liste complète des tâches.

        Returns:
            Liste filtrée.
        """
        if self._filter_mode == "all":
            return tasks
        if self._filter_mode == "active":
            active_statuses = {"in_progress", "running", "pending", "queued",
                               "interrupted", "paused"}
            return [t for t in tasks if t.get("status", "").lower() in active_statuses]
        if self._filter_mode == "done":
            done_statuses = {"completed", "done", "cancelled", "canceled", "failed"}
            return [t for t in tasks if t.get("status", "").lower() in done_statuses]
        return tasks

    # ── Cartes tâche ─────────────────────────────────────────────────────

    def _build_task_card(self, task: dict[str, Any]) -> QFrame:
        """Construit une carte visuelle pour une tâche.

        Args:
            task: Dictionnaire de la tâche.

        Returns:
            QFrame représentant la carte tâche.
        """
        task_id = task.get("id", "unknown")
        card = QFrame()
        card.setObjectName(f"AgentTaskCard_{task_id}")
        card.setStyleSheet(
            f"#AgentTaskCard_{task_id} {{"
            "  background-color: rgba(255,255,255,0.02);"
            f"  border: 1px solid {BORDER_COLOR};"
            "  border-radius: 6px;"
            "}"
        )

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(8)

        status = task.get("status", "pending").lower()

        # ── Icône statut ──
        icon_lbl = QLabel(_task_status_icon(status))
        icon_lbl.setFixedWidth(24)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 16px; background: transparent;")
        card_layout.addWidget(icon_lbl)

        # ── Infos ──
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        desc = task.get("description", task.get("name", "Sans nom"))
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: bold; "
            "background: transparent;"
        )
        desc_lbl.setWordWrap(True)
        info_layout.addWidget(desc_lbl)

        # Ligne meta : statut + progression + durée
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        status_lbl = QLabel(_task_status_label(status))
        status_lbl.setStyleSheet(
            f"color: {_task_status_color(status)}; font-size: 10px; "
            "background: transparent;"
        )
        meta_row.addWidget(status_lbl)

        progress = task.get("progress")
        if progress is not None:
            progress_lbl = QLabel(_task_progress_text(progress))
            progress_lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;"
            )
            meta_row.addWidget(progress_lbl)

        duration = task.get("duration")
        if duration is not None:
            duration_lbl = QLabel(_format_duration(duration))
            duration_lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;"
            )
            meta_row.addWidget(duration_lbl)

        meta_row.addStretch()
        info_layout.addLayout(meta_row)

        # Barre de progression
        if progress is not None:
            pbar = QProgressBar()
            pbar.setFixedHeight(4)
            pbar.setRange(0, 100)
            try:
                pbar.setValue(int(float(progress) * 100))
            except (ValueError, TypeError):
                pbar.setValue(0)
            pbar.setTextVisible(False)
            pbar.setStyleSheet(
                "QProgressBar { background: rgba(255,255,255,0.04); "
                "border: none; border-radius: 2px; }"
                f"QProgressBar::chunk {{ background-color: {_task_status_color(status)}; "
                "border-radius: 2px; }"
            )
            info_layout.addWidget(pbar)

        card_layout.addLayout(info_layout, stretch=1)

        # ── Boutons d'action ──
        if status in ("interrupted", "paused"):
            resume_btn = QPushButton("▶ Reprendre")
            resume_btn.setCursor(Qt.PointingHandCursor)
            resume_btn.setStyleSheet(
                "QPushButton {"
                f"  background-color: rgba(59,130,246,0.1);"
                f"  color: {ACCENT_BLUE};"
                f"  border: 1px solid rgba(59,130,246,0.3);"
                "  border-radius: 4px; padding: 4px 10px; font-size: 10px;"
                "  font-weight: bold;"
                "}"
                "QPushButton:hover {"
                "  background-color: rgba(59,130,246,0.2);"
                f"  border: 1px solid {ACCENT_BLUE};"
                "}"
            )
            resume_btn.setFixedHeight(26)
            resume_btn.clicked.connect(
                lambda _checked=False, tid=task_id: self.resume_task.emit(tid)
            )
            card_layout.addWidget(resume_btn)

        cancel_btn = QPushButton("✕")
        cancel_btn.setFixedSize(24, 24)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; "
            f"color: {TEXT_SECONDARY}; border: none; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {ACCENT_RED}; }}"
        )
        cancel_btn.clicked.connect(
            lambda _checked=False, tid=task_id: self.cancel_task.emit(tid)
        )
        card_layout.addWidget(cancel_btn)

        return card

    # ── Utilitaires ──────────────────────────────────────────────────────

    def _clear_steps(self) -> None:
        """Supprime tous les labels d'étapes du conteneur."""
        while self._steps_container.count():
            item = self._steps_container.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _clear_task_cards(self) -> None:
        """Supprime toutes les cartes tâche du layout (sauf le label vide)."""
        while self._task_list_layout.count() > 1:  # index 0 = empty_label
            item = self._task_list_layout.takeAt(1)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
