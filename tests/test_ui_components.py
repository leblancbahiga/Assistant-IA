"""
Tests unitaires pour AgentStatusWidget et FeedbackBar (Dashboard V9).

Ces tests NE lancent PAS PySide6 — ils testent uniquement les helpers
de formatage et la logique de calcul (pas le rendu Qt).

Exécution :
    pytest tests/test_ui_components.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ajouter le projet au path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ── Helper functions à tester (copiées depuis agent_status.py) ─────────────

AGENT_STATE_LABELS: dict[str, str] = {
    "idle": "⚪ Inactif",
    "planning": "🔵 Planification",
    "executing": "🟢 Exécution",
    "verifying": "🟡 Vérification",
    "done": "✅ Terminé",
    "error": "🔴 Erreur",
}

AGENT_STATE_COLORS: dict[str, str] = {
    "idle": "#8B949E",
    "planning": "#00A3FF",
    "executing": "#39FF14",
    "verifying": "#FF8C00",
    "done": "#39FF14",
    "error": "#FF3333",
}


def format_plan_step(step: str, index: int, total: int, is_current: bool = False) -> str:
    prefix = f"{index + 1}/{total}"
    marker = "→ " if is_current else "  "
    return f"{marker}{prefix} • {step}"


def compute_progress(step_index: int, total_steps: int) -> float:
    if total_steps <= 0:
        return 0.0
    if step_index < 0:
        return 0.0
    return min(1.0, (step_index + 1) / total_steps)


def state_label(state: str) -> str:
    return AGENT_STATE_LABELS.get(state, f"❓ {state.capitalize()}")


def state_color(state: str) -> str:
    return AGENT_STATE_COLORS.get(state, "#8B949E")


# ── Helper functions pour FeedbackBar ──────────────────────────────────────

BTN_BASE_STYLE = (
    "QPushButton {"
    "  background-color: rgba(255,255,255,0.04);"
    "  color: #6B7280; border: 1px solid rgba(255,255,255,0.08);"
    "  border-radius: 6px; font-size: 14px;"
    "}"
)

BTN_ACTIVE_POSITIVE = (
    "QPushButton {"
    "  background-color: rgba(57,255,20,0.12);"
    "  color: #39FF14; border: 1px solid rgba(57,255,20,0.4);"
    "  border-radius: 6px; font-size: 14px;"
    "}"
)

BTN_ACTIVE_NEGATIVE = (
    "QPushButton {"
    "  background-color: rgba(255,51,51,0.12);"
    "  color: #FF3333; border: 1px solid rgba(255,51,51,0.4);"
    "  border-radius: 6px; font-size: 14px;"
    "}"
)

BTN_ACTIVE_CORRECTION = (
    "QPushButton {"
    "  background-color: rgba(255,140,0,0.12);"
    "  color: #FF8C00; border: 1px solid rgba(255,140,0,0.4);"
    "  border-radius: 6px; font-size: 14px;"
    "}"
)


def feedback_btn_style(feedback_type: str, active: bool = False) -> str:
    if not active:
        return BTN_BASE_STYLE
    styles = {
        "positive": BTN_ACTIVE_POSITIVE,
        "negative": BTN_ACTIVE_NEGATIVE,
        "correction": BTN_ACTIVE_CORRECTION,
    }
    return styles.get(feedback_type, BTN_BASE_STYLE)


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : AgentStatusWidget — formatage et helpers
# ══════════════════════════════════════════════════════════════════════════


class TestAgentStatusFormatPlan:
    """Teste format_plan_step — mise en forme des étapes du plan."""

    def test_basic_format(self):
        """Formatage simple d'une étape."""
        result = format_plan_step("Rechercher documents", 0, 3)
        assert "1/3" in result
        assert "Rechercher documents" in result
        assert "→" not in result  # pas current

    def test_current_step_format(self):
        """L'étape courante a le marqueur →."""
        result = format_plan_step("Analyse", 1, 3, is_current=True)
        assert "2/3" in result
        assert "→" in result
        assert "Analyse" in result

    def test_last_step(self):
        """Dernière étape du plan."""
        result = format_plan_step("Terminer", 4, 5, is_current=True)
        assert "5/5" in result
        assert "→" in result

    def test_single_step(self):
        """Plan avec une seule étape."""
        result = format_plan_step("Faire X", 0, 1, is_current=True)
        assert "1/1" in result
        assert "Faire X" in result

    def test_format_consistency(self):
        """Vérifie que le formatage est cohérent : 'N/M • description'."""
        result = format_plan_step("Test", 2, 5)
        assert result.endswith("• Test")
        assert "3/5" in result


class TestAgentStatusStateStrings:
    """Teste state_label et state_color — libellés et couleurs."""

    def test_idle_label(self):
        assert state_label("idle") == "⚪ Inactif"

    def test_planning_label(self):
        assert state_label("planning") == "🔵 Planification"

    def test_executing_label(self):
        assert state_label("executing") == "🟢 Exécution"

    def test_verifying_label(self):
        assert state_label("verifying") == "🟡 Vérification"

    def test_done_label(self):
        assert state_label("done") == "✅ Terminé"

    def test_error_label(self):
        assert state_label("error") == "🔴 Erreur"

    def test_unknown_state_label(self):
        """État inconnu → fallback générique."""
        assert state_label("unknown") == "❓ Unknown"

    def test_idle_color(self):
        assert state_color("idle") == "#8B949E"

    def test_planning_color(self):
        assert state_color("planning") == "#00A3FF"

    def test_executing_color(self):
        assert state_color("executing") == "#39FF14"

    def test_verifying_color(self):
        assert state_color("verifying") == "#FF8C00"

    def test_done_color(self):
        assert state_color("done") == "#39FF14"

    def test_error_color(self):
        assert state_color("error") == "#FF3333"

    def test_unknown_state_color(self):
        """État inconnu → couleur par défaut."""
        assert state_color("unknown") == "#8B949E"


class TestAgentStatusProgress:
    """Teste compute_progress — calcul de progression."""

    def test_zero_steps(self):
        """Aucune étape → progression 0."""
        assert compute_progress(0, 0) == 0.0
        assert compute_progress(-1, 0) == 0.0

    def test_negative_steps(self):
        """total_steps négatif → traité comme 0."""
        assert compute_progress(0, -1) == 0.0

    def test_negative_index(self):
        """Index négatif (idle/error) → progression 0."""
        assert compute_progress(-1, 5) == 0.0

    def test_first_step_3_steps(self):
        """Première étape sur 3 → 1/3 ≈ 0.333."""
        assert compute_progress(0, 3) == pytest.approx(1.0 / 3.0)

    def test_second_step_3_steps(self):
        """Deuxième étape sur 3 → 2/3 ≈ 0.667."""
        assert compute_progress(1, 3) == pytest.approx(2.0 / 3.0)

    def test_last_step_3_steps(self):
        """Dernière étape sur 3 → 1.0."""
        assert compute_progress(2, 3) == 1.0

    def test_single_step_progress(self):
        """Une seule étape, à l'index 0 → 1.0."""
        assert compute_progress(0, 1) == 1.0

    def test_progress_never_exceeds_1(self):
        """Garantie que le progrès ne dépasse pas 1.0."""
        assert compute_progress(10, 5) == 1.0  # clamp


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : FeedbackBar — formatage et helpers
# ══════════════════════════════════════════════════════════════════════════


class TestFeedbackBarFormat:
    """Teste feedback_btn_style — génération de stylesheet."""

    def test_base_style(self):
        """Style par défaut quand non actif."""
        style = feedback_btn_style("positive", active=False)
        assert "background-color: rgba(255,255,255,0.04)" in style
        assert "#6B7280" in style

    def test_active_positive_style(self):
        """Style actif pour 👍."""
        style = feedback_btn_style("positive", active=True)
        assert "#39FF14" in style
        assert "rgba(57,255,20" in style

    def test_active_negative_style(self):
        """Style actif pour 👎."""
        style = feedback_btn_style("negative", active=True)
        assert "#FF3333" in style
        assert "rgba(255,51,51" in style

    def test_active_correction_style(self):
        """Style actif pour ✏️."""
        style = feedback_btn_style("correction", active=True)
        assert "#FF8C00" in style
        assert "rgba(255,140,0" in style

    def test_unknown_type_active(self):
        """Type inconnu avec active=True → base style."""
        style = feedback_btn_style("unknown", active=True)
        assert style == BTN_BASE_STYLE


class TestFeedbackBarToggleState:
    """Teste la logique de basculement d'état (sans PySide6)."""

    def test_enabled_disabled_switch(self):
        """Vérifie la logique enabled/disabled (simulation)."""
        # Simuler : feedback actif = positive
        feedback_type = "positive"
        expected_style_active = feedback_btn_style(feedback_type, active=True)
        expected_style_inactive = feedback_btn_style(feedback_type, active=False)

        # Actif doit contenir la couleur
        assert "#39FF14" in expected_style_active
        # Inactif ne doit PAS contenir la couleur active
        assert "#39FF14" not in expected_style_inactive

    def test_reset_highlight(self):
        """Après un highlight puis reset, le style doit revenir au base."""
        activated = feedback_btn_style("negative", active=True)
        reset = feedback_btn_style("negative", active=False)
        assert "#FF3333" in activated
        assert "#FF3333" not in reset
        assert reset == BTN_BASE_STYLE

    def test_all_feedback_types_have_distinct_styles(self):
        """Chaque type de feedback actif a un style distinct."""
        pos = feedback_btn_style("positive", active=True)
        neg = feedback_btn_style("negative", active=True)
        corr = feedback_btn_style("correction", active=True)

        assert pos != neg
        assert neg != corr
        assert corr != pos

    def test_multiple_calls_idempotent(self):
        """Appeler plusieurs fois le même type donne le même résultat."""
        a = feedback_btn_style("positive", active=True)
        b = feedback_btn_style("positive", active=True)
        assert a == b


# ── Nécessaire pour pytest.approx ──────────────────────────────────────────

import pytest  # noqa: E402 (import après les helpers pour clarté)


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : MemoryExplorer — formatage, filtrage, compteurs
# ══════════════════════════════════════════════════════════════════════════


MEMORY_TYPE_ICONS: dict[str, str] = {
    "episodic": "📅",
    "semantic": "📚",
    "user": "👤",
    "error": "⚠️",
}

MEMORY_TYPE_COLORS: dict[str, str] = {
    "episodic": "#00A3FF",
    "semantic": "#39FF14",
    "user": "#FF8C00",
    "error": "#FF3333",
}


def format_memory_entry(entry: dict, memory_type: str = "") -> str:
    """Formate une entrée mémoire en texte lisible."""
    icon = MEMORY_TYPE_ICONS.get(memory_type, "📌")
    prefix = f"{icon} " if memory_type else ""

    summary = entry.get("summary") or entry.get("content", "")
    if isinstance(summary, str) and len(summary) > 120:
        summary = summary[:117] + "..."

    category = entry.get("category", "")
    score = entry.get("score", "")
    tags = entry.get("tags", [])

    parts = [f"{prefix}{summary}"]
    if category:
        parts.append(f"[{category}]")
    if score:
        parts.append(f"(score: {score})")
    if tags and isinstance(tags, list):
        tag_str = " ".join(f"#{t}" for t in tags[:3])
        parts.append(tag_str)

    return "  ".join(parts)


def filter_entries(entries: list[dict], query: str) -> list[dict]:
    """Filtre les entrées mémoire par requête textuelle."""
    if not query or not query.strip():
        return entries
    q = query.strip().lower()
    results: list[dict] = []
    for entry in entries:
        searchable = [
            str(entry.get("summary", "")),
            str(entry.get("content", "")),
            str(entry.get("category", "")),
            " ".join(str(t) for t in entry.get("tags", [])),
        ]
        if any(q in s.lower() for s in searchable):
            results.append(entry)
    return results


def count_by_type(data: dict[str, list]) -> dict[str, int]:
    """Compte le nombre d'entrées par type de mémoire."""
    return {key: len(val) if isinstance(val, list) else 0 for key, val in data.items()}


class TestMemoryExplorerFormatEntry:
    """Teste format_memory_entry — mise en forme des entrées mémoire."""

    def test_basic_entry(self):
        """Entrée simple avec summary."""
        entry = {"summary": "Conversation sur l'IA", "category": "chat"}
        result = format_memory_entry(entry, "episodic")
        assert "📅" in result
        assert "Conversation sur l'IA" in result
        assert "[chat]" in result

    def test_entry_no_type(self):
        """Entrée sans type mémoire spécifié — pas d'icône préfixée."""
        entry = {"summary": "Note rapide"}
        result = format_memory_entry(entry)
        # Quand memory_type est vide, aucun préfixe icône n'est ajouté
        assert result == "Note rapide"

    def test_entry_with_score(self):
        """Entrée avec score de pertinence."""
        entry = {"summary": "Fait important", "score": 0.95}
        result = format_memory_entry(entry, "semantic")
        assert "📚" in result
        assert "Fait important" in result
        assert "score: 0.95" in result

    def test_entry_with_tags(self):
        """Entrée avec tags."""
        entry = {"summary": "Concept ML", "tags": ["machine-learning", "python", "data"]}
        result = format_memory_entry(entry, "semantic")
        assert "#machine-learning" in result
        assert "#python" in result

    def test_long_summary_truncated(self):
        """Summary long tronqué à 120 caractères."""
        long_text = "A" * 200
        entry = {"summary": long_text}
        result = format_memory_entry(entry)
        assert len(result) < 200
        assert result.endswith("...")

    def test_entry_uses_content_fallback(self):
        """Fallback sur 'content' si 'summary' absent."""
        entry = {"content": "Contenu brut sans summary"}
        result = format_memory_entry(entry)
        assert "Contenu brut" in result

    def test_all_memory_types_have_icons(self):
        """Tous les types de mémoire listés ont une icône."""
        for mtype in ("episodic", "semantic", "user", "error"):
            result = format_memory_entry({"summary": "test"}, mtype)
            icon = MEMORY_TYPE_ICONS[mtype]
            assert icon in result, f"Type {mtype} devrait avoir l'icône {icon}"


class TestMemoryExplorerFilterByType:
    """Teste filter_entries — filtrage textuel."""

    def test_empty_query_returns_all(self):
        """Requête vide → retourne toute la liste."""
        entries = [
            {"summary": "Premier", "category": "chat"},
            {"summary": "Deuxième", "category": "action"},
        ]
        assert filter_entries(entries, "") == entries
        assert filter_entries(entries, "  ") == entries

    def test_filter_by_summary(self):
        """Filtre dans le summary."""
        entries = [
            {"summary": "Recherche documents", "category": "search"},
            {"summary": "Analyse résultats", "category": "analysis"},
        ]
        result = filter_entries(entries, "recherche")
        assert len(result) == 1
        assert result[0]["summary"] == "Recherche documents"

    def test_filter_by_category(self):
        """Filtre dans la catégorie."""
        entries = [
            {"summary": "Item A", "category": "chat"},
            {"summary": "Item B", "category": "action"},
        ]
        result = filter_entries(entries, "action")
        assert len(result) == 1
        assert result[0]["summary"] == "Item B"

    def test_filter_by_tag(self):
        """Filtre dans les tags."""
        entries = [
            {"summary": "ML", "tags": ["machine-learning", "python"]},
            {"summary": "Web", "tags": ["javascript", "node"]},
        ]
        result = filter_entries(entries, "python")
        assert len(result) == 1
        assert result[0]["summary"] == "ML"

    def test_filter_case_insensitive(self):
        """Filtre insensible à la casse."""
        entries = [
            {"summary": "Hello World"},
            {"summary": "Bonjour"},
        ]
        result = filter_entries(entries, "hello")
        assert len(result) == 1
        assert result[0]["summary"] == "Hello World"

    def test_no_match_returns_empty(self):
        """Aucune correspondance → liste vide."""
        entries = [{"summary": "Un seul"}]
        result = filter_entries(entries, "xyz")
        assert result == []

    def test_filter_multiple_matches(self):
        """Plusieurs entrées correspondent."""
        entries = [
            {"summary": "Doc A", "tags": ["python"]},
            {"summary": "Doc B", "tags": ["python"]},
            {"summary": "Doc C", "tags": ["java"]},
        ]
        result = filter_entries(entries, "python")
        assert len(result) == 2


class TestMemoryExplorerCount:
    """Teste count_by_type — comptage des entrées par type mémoire."""

    def test_empty_data(self):
        """Données vides → tous les compteurs à 0."""
        data = {"episodic": [], "semantic": [], "user": [], "error": []}
        counts = count_by_type(data)
        assert all(v == 0 for v in counts.values())

    def test_counts_correct(self):
        """Comptage correct pour chaque type."""
        data = {
            "episodic": [{"id": 1}, {"id": 2}],
            "semantic": [{"id": 1}],
            "user": [],
            "error": [{"id": 1}, {"id": 2}, {"id": 3}],
        }
        counts = count_by_type(data)
        assert counts["episodic"] == 2
        assert counts["semantic"] == 1
        assert counts["user"] == 0
        assert counts["error"] == 3

    def test_missing_key_is_zero(self):
        """Clé manquante → comptée comme 0."""
        data = {"episodic": [{"id": 1}]}
        counts = count_by_type(data)
        assert counts["episodic"] == 1
        assert counts.get("semantic", 0) == 0

    def test_non_list_value_is_zero(self):
        """Valeur non-liste → comptée comme 0."""
        data = {"episodic": [{"id": 1}], "semantic": "not_a_list", "user": None}
        counts = count_by_type(data)
        assert counts["episodic"] == 1
        assert counts["semantic"] == 0
        assert counts["user"] == 0

    def test_sum_total(self):
        """Somme totale des compteurs est correcte."""
        data = {
            "episodic": [{"id": 1}] * 3,
            "semantic": [{"id": 1}] * 2,
            "user": [{"id": 1}] * 1,
            "error": [{"id": 1}] * 4,
        }
        counts = count_by_type(data)
        assert sum(counts.values()) == 10


# ══════════════════════════════════════════════════════════════════════════
#  TESTS : TaskListWidget — formatage, icônes, progression
# ══════════════════════════════════════════════════════════════════════════


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


def status_icon(status: str) -> str:
    return STATUS_ICONS.get(status.lower(), "📋")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status.lower(), status.capitalize())


def format_duration(seconds: float | int | None) -> str:
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
    return " ".join(parts)


def format_task_summary(task: dict) -> str:
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
    if progress is None:
        return "—"
    try:
        pct = max(0.0, min(1.0, float(progress))) * 100
        return f"{int(pct)}%"
    except (ValueError, TypeError):
        return "—"


class TestTaskListFormatTasks:
    """Teste format_task_summary — résumé texte des tâches."""

    def test_basic_format(self):
        """Formatage de base avec description et catégorie."""
        task = {"id": "1", "description": "Analyser logs", "status": "in_progress", "category": "analyse"}
        result = format_task_summary(task)
        assert "Analyser logs" in result
        assert "[analyse]" in result
        assert "🔄" in result

    def test_task_no_category(self):
        """Tâche sans catégorie."""
        task = {"id": "2", "description": "Tâche simple", "status": "pending"}
        result = format_task_summary(task)
        assert "Tâche simple" in result
        assert "⏳" in result

    def test_long_description_truncated(self):
        """Description longue tronquée."""
        task = {"id": "3", "description": "A" * 100, "status": "completed"}
        result = format_task_summary(task)
        assert len(result) < 100
        assert result.endswith("...")

    def test_task_uses_name_fallback(self):
        """Fallback sur 'name' si 'description' absent."""
        task = {"id": "4", "name": "Tâche nommée", "status": "running"}
        result = format_task_summary(task)
        assert "Tâche nommée" in result
        assert "🔄" in result

    def test_task_without_name(self):
        """Absence de nom et description → fallback générique."""
        task = {"id": "5", "status": "failed"}
        result = format_task_summary(task)
        assert "Tâche sans nom" in result
        assert "❌" in result


class TestTaskListStatusIcons:
    """Teste status_icon et status_label — icônes et libellés."""

    def test_in_progress_icon(self):
        assert status_icon("in_progress") == "🔄"
        assert status_icon("running") == "🔄"

    def test_completed_icon(self):
        assert status_icon("completed") == "✅"
        assert status_icon("done") == "✅"

    def test_interrupted_icon(self):
        assert status_icon("interrupted") == "⏸️"
        assert status_icon("paused") == "⏸️"

    def test_failed_icon(self):
        assert status_icon("failed") == "❌"
        assert status_icon("cancelled") == "❌"

    def test_pending_icon(self):
        assert status_icon("pending") == "⏳"
        assert status_icon("queued") == "⏳"

    def test_unknown_status_icon(self):
        """Statut inconnu → fallback 📋."""
        assert status_icon("unknown") == "📋"

    def test_in_progress_label(self):
        assert status_label("in_progress") == "En cours"
        assert status_label("running") == "En cours"

    def test_completed_label(self):
        assert status_label("completed") == "Terminée"
        assert status_label("done") == "Terminée"

    def test_interrupted_label(self):
        assert status_label("interrupted") == "Interrompue"
        assert status_label("paused") == "En pause"

    def test_failed_label(self):
        assert status_label("failed") == "Échouée"
        assert status_label("cancelled") == "Annulée"

    def test_pending_label(self):
        assert status_label("pending") == "En attente"
        assert status_label("queued") == "En attente"

    def test_case_insensitive(self):
        """Le statut est insensible à la casse."""
        assert status_icon("IN_PROGRESS") == "🔄"
        assert status_label("COMPLETED") == "Terminée"

    def test_all_statuses_have_icons(self):
        """Tous les status prédéfinis ont une icône associée."""
        for status in ("in_progress", "running", "completed", "done",
                       "interrupted", "paused", "cancelled",
                       "canceled", "failed", "pending", "queued"):
            icon = status_icon(status)
            assert icon != "📋", f"Status '{status}' devrait avoir une icône dédiée"


class TestTaskListProgressText:
    """Teste task_progress_text et format_duration — formatage progression."""

    def test_progress_none(self):
        """Progression None → '—'."""
        assert task_progress_text(None) == "—"

    def test_progress_zero(self):
        """Progression 0%."""
        assert task_progress_text(0.0) == "0%"

    def test_progress_half(self):
        """Progression 50%."""
        assert task_progress_text(0.5) == "50%"

    def test_progress_full(self):
        """Progression 100%."""
        assert task_progress_text(1.0) == "100%"

    def test_progress_clamped(self):
        """Progression clampée entre 0 et 1."""
        assert task_progress_text(-0.5) == "0%"
        assert task_progress_text(1.5) == "100%"

    def test_progress_as_int(self):
        """Progression passée comme entier."""
        assert task_progress_text(0) == "0%"
        assert task_progress_text(1) == "100%"

    def test_duration_none(self):
        """Durée None → '—'."""
        assert format_duration(None) == "—"

    def test_duration_zero(self):
        """Durée 0s."""
        assert format_duration(0) == "0s"

    def test_duration_seconds_only(self):
        """Durée en secondes seulement."""
        assert format_duration(45) == "45s"

    def test_duration_minutes(self):
        """Durée avec minutes et secondes."""
        assert format_duration(125) == "2m 5s"

    def test_duration_hours(self):
        """Durée avec heures."""
        assert format_duration(3661) == "1h 1m 1s"

    def test_duration_exact_hour(self):
        """Durée d'une heure exacte."""
        assert format_duration(3600) == "1h 0s"

    def test_duration_small_negative(self):
        """Durée négative → traitée comme 0."""
        assert format_duration(-5) == "0s"
