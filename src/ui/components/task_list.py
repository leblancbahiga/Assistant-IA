"""
TaskListWidget — Liste des tâches avec reprise (Dashboard V9).

Affiche : tâches en cours, terminées, interrompues.
Permet de reprendre une tâche interrompue.

Design cyberpunk NURU : bg #0D1117, accent #00A3FF.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

# ── Constantes de thème ────────────────────────────────────────────────────

BG_PANEL = "#161b22"
ACCENT_BLUE = "#00A3FF"
ACCENT_GREEN = "#39FF14"
ACCENT_RED = "#FF3333"
ACCENT_ORANGE = "#FF8C00"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
BORDER_COLOR = "rgba(255,255,255,0.08)"

PANEL_STYLE = f"""
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
"""

BTN_RESUME_STYLE = f"""
    QPushButton {{
        background-color: rgba(0,163,255,0.1);
        color: {ACCENT_BLUE};
        border: 1px solid rgba(0,163,255,0.3);
        border-radius: 4px;
        padding: 4px 10px;
        font-size: 10px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: rgba(0,163,255,0.2);
        border: 1px solid {ACCENT_BLUE};
    }}
"""

BTN_CANCEL_STYLE = f"""
    QPushButton {{
        background-color: transparent;
        color: {TEXT_SECONDARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 4px;
        padding: 4px 10px;
        font-size: 10px;
    }}
    QPushButton:hover {{
        color: {ACCENT_RED};
        border: 1px solid rgba(255,51,51,0.3);
    }}
"""

# ── Status icons & labels ──────────────────────────────────────────────────

STATUS_ICONS: dict[str, str] = {
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

STATUS_LABELS: dict[str, str] = {
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

STATUS_COLORS: dict[str, str] = {
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


def status_icon(status: str) -> str:
    """Retourne l'icône pour un statut de tâche.

    Args:
        status: Statut de la tâche (in_progress, completed, interrupted, etc.).

    Returns:
        Emoji représentant le statut.
    """
    return STATUS_ICONS.get(status.lower(), "📋")


def status_label(status: str) -> str:
    """Retourne le libellé lisible pour un statut.

    Args:
        status: Statut de la tâche.

    Returns:
        Libellé en français.
    """
    return STATUS_LABELS.get(status.lower(), status.capitalize())


def status_color(status: str) -> str:
    """Retourne la couleur hex pour un statut.

    Args:
        status: Statut de la tâche.

    Returns:
        Couleur hexadécimale.
    """
    return STATUS_COLORS.get(status.lower(), TEXT_SECONDARY)


def format_duration(seconds: float | int | None) -> str:
    """Formate une durée en secondes en texte lisible.

    Args:
        seconds: Durée en secondes (peut être None).

    Returns:
        Chaîne formatée comme "2m 30s" ou "1h 15m".
    """
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


def format_task_summary(task: dict[str, Any]) -> str:
    """Formate un résumé de tâche pour affichage.

    Args:
        task: Dictionnaire de tâche.
              Champs typiques : id, description, status, progress, duration, category.

    Returns:
        Chaîne résumée.
    """
    desc = task.get("description", task.get("name", "Tâche sans nom"))
    if isinstance(desc, str) and len(desc) > 80:
        desc = desc[:77] + "..."

    category = task.get("category", task.get("type", ""))
    status = task.get("status", "pending")
    icon = status_icon(status)

    parts = [f"{icon} {desc}"]
    if category:
        parts.append(f"[{category}]")

    return "  ".join(parts)


def task_progress_text(progress: float | int | None) -> str:
    """Formate la progression d'une tâche en texte.

    Args:
        progress: Valeur entre 0.0 et 1.0 (ou None).

    Returns:
        Chaîne comme "75%" ou "—".
    """
    if progress is None:
        return "—"
    try:
        pct = max(0.0, min(1.0, float(progress))) * 100
        return f"{int(pct)}%"
    except (ValueError, TypeError):
        return "—"


# ── Widget principal ───────────────────────────────────────────────────────


class TaskListWidget(QFrame):
    """Liste des tâches avec reprise.

    Affiche : tâches en cours, terminées, interrompues.
    Permet de reprendre une tâche interrompue.

    Signaux :
        resume_task(task_id: str) — émis quand l'utilisateur clique "Reprendre"
        cancel_task(task_id: str) — émis quand l'utilisateur clique "Annuler"

    API publique :
        set_tasks(tasks: list[dict]) — met à jour la liste
        add_task(task: dict) — ajoute une tâche
        update_task(task_id: str, status: str) — met à jour le statut
        clear_completed() — vide les tâches terminées
    """

    resume_task = Signal(str)
    cancel_task = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TaskListWidget")
        self.setStyleSheet(f"#TaskListWidget {{ {PANEL_STYLE} }}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ── Données ──
        self._tasks: list[dict[str, Any]] = []

        # ── Layout principal ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── En-tête ──
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("📋 Tâches")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: bold;")
        header.addWidget(title)

        self._count_label = QLabel("0")
        self._count_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            f"background: rgba(255,255,255,0.04); padding: 2px 8px; "
            f"border-radius: 4px;"
        )
        header.addWidget(self._count_label)

        header.addStretch()

        self._clear_completed_btn = QPushButton("Nettoyer")
        self._clear_completed_btn.setCursor(Qt.PointingHandCursor)
        self._clear_completed_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; "
            f"border: 1px solid {BORDER_COLOR}; border-radius: 4px; "
            f"padding: 2px 8px; font-size: 10px; }}"
            f"QPushButton:hover {{ color: {ACCENT_GREEN}; "
            f"border: 1px solid rgba(57,255,20,0.3); }}"
        )
        self._clear_completed_btn.clicked.connect(self.clear_completed)
        header.addWidget(self._clear_completed_btn)

        layout.addLayout(header)

        # ── Zone scrollable ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {ACCENT_BLUE}; "
            f"border-radius: 2px; min-height: 20px; }}"
        )

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll)

        # ── État vide ──
        self._empty_label = QLabel("    Aucune tâche en cours.")
        self._empty_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; padding: 20px 0px;"
        )
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setVisible(True)
        self._list_layout.insertWidget(0, self._empty_label)

    # ── API publique ─────────────────────────────────────────────────────

    def set_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Remplace toutes les tâches.

        Args:
            tasks: Liste de dictionnaires de tâches.
        """
        self._tasks = list(tasks)
        self._rebuild_list()

    def add_task(self, task: dict[str, Any]) -> None:
        """Ajoute une tâche à la liste.

        Args:
            task: Dictionnaire de la tâche à ajouter.
        """
        self._tasks.append(task)
        self._rebuild_list()

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
        self._rebuild_list()

    def clear_completed(self) -> None:
        """Supprime toutes les tâches terminées/annulées de la liste."""
        completed_statuses = {"completed", "done", "cancelled", "canceled", "failed"}
        self._tasks = [
            t for t in self._tasks
            if t.get("status", "").lower() not in completed_statuses
        ]
        self._rebuild_list()

    # ── Méthodes privées ─────────────────────────────────────────────────

    def _rebuild_list(self) -> None:
        """Reconstruit l'affichage complet de la liste des tâches."""
        # Vider les éléments sauf le stretch et le label vide
        while self._list_layout.count() > 2:  # 0=empty_label, last=stretch
            item = self._list_layout.takeAt(1)  # entre label et stretch
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # Afficher ou masquer le label vide
        if not self._tasks:
            self._empty_label.setVisible(True)
            self._count_label.setText("0")
            return

        self._empty_label.setVisible(False)
        self._count_label.setText(str(len(self._tasks)))

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

        sorted_tasks = sorted(self._tasks, key=_sort_key)

        for task in sorted_tasks:
            task_card = self._build_task_card(task)
            # Insérer avant le stretch (dernier élément)
            self._list_layout.insertWidget(
                self._list_layout.count() - 1, task_card
            )

    def _build_task_card(self, task: dict[str, Any]) -> QFrame:
        """Construit une carte visuelle pour une tâche.

        Args:
            task: Dictionnaire de la tâche.

        Returns:
            QFrame représentant la carte tâche.
        """
        card = QFrame()
        card.setObjectName(f"TaskCard_{task.get('id', 'unknown')}")
        card.setStyleSheet(
            f"#TaskCard_{task.get('id', 'unknown')} {{"
            f"  background-color: rgba(255,255,255,0.02);"
            f"  border: 1px solid {BORDER_COLOR};"
            f"  border-radius: 6px;"
            f"}}"
        )
        card.setFixedHeight(64)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setSpacing(8)

        # ── Statut (icône) ──
        status = task.get("status", "pending").lower()
        icon_lbl = QLabel(status_icon(status))
        icon_lbl.setFixedWidth(24)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(f"font-size: 16px;")
        card_layout.addWidget(icon_lbl)

        # ── Infos tâche ──
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # Description
        desc = task.get("description", task.get("name", "Sans nom"))
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: bold;"
        )
        desc_lbl.setWordWrap(True)
        info_layout.addWidget(desc_lbl)

        # Ligne statut + progression + durée
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(8)

        status_lbl = QLabel(status_label(status))
        status_lbl.setStyleSheet(
            f"color: {status_color(status)}; font-size: 10px;"
        )
        meta_layout.addWidget(status_lbl)

        progress = task.get("progress")
        if progress is not None:
            progress_lbl = QLabel(task_progress_text(progress))
            progress_lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px;"
            )
            meta_layout.addWidget(progress_lbl)

        duration = task.get("duration")
        if duration is not None:
            duration_lbl = QLabel(format_duration(duration))
            duration_lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px;"
            )
            meta_layout.addWidget(duration_lbl)

        meta_layout.addStretch()
        info_layout.addLayout(meta_layout)

        # ── Barre de progression ──
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
                f"QProgressBar {{ background: rgba(255,255,255,0.04); "
                f"border: none; border-radius: 2px; }}"
                f"QProgressBar::chunk {{ background-color: {status_color(status)}; "
                f"border-radius: 2px; }}"
            )
            info_layout.addWidget(pbar)

        card_layout.addLayout(info_layout, stretch=1)

        # ── Boutons d'action ──
        if status in ("interrupted", "paused"):
            resume_btn = QPushButton("▶ Reprendre")
            resume_btn.setCursor(Qt.PointingHandCursor)
            resume_btn.setStyleSheet(BTN_RESUME_STYLE)
            resume_btn.setFixedHeight(26)
            task_id = task.get("id", "")
            resume_btn.clicked.connect(
                lambda checked=False, tid=task_id: self.resume_task.emit(tid)
            )
            card_layout.addWidget(resume_btn)

        cancel_btn = QPushButton("✕")
        cancel_btn.setFixedSize(24, 24)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; "
            f"border: none; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {ACCENT_RED}; }}"
        )
        task_id = task.get("id", "")
        cancel_btn.clicked.connect(
            lambda checked=False, tid=task_id: self.cancel_task.emit(tid)
        )
        card_layout.addWidget(cancel_btn)

        return card
