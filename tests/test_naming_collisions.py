"""NURU V15 Phase 6 — Test anti-collision de noms de classes (Item 45, P0 #13).

Vérifie que chaque nom de classe défini dans src/ est unique — pas de collisions
entre modules qui créeraient des shadowing silencieux.

Scanne récursivement src/, extrait les définitions de classes Python,
signale les doublons.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"


def _extract_classes(path: Path) -> list[tuple[str, str]]:
    """Retourne [(nom_classe, chemin_module), ...] pour un fichier."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    classes: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Ignorer les classes importées (héritage externe) — seule la définition compte
            classes.append((node.name, str(path)))
    return classes


def _collect_all_classes() -> dict[str, list[str]]:
    """Collecte toutes les définitions de classes → {nom: [chemins...]}."""
    registry: dict[str, list[str]] = {}
    py_files = sorted(SRC.rglob("*.py"))
    for pyf in py_files:
        for name, path in _extract_classes(pyf):
            registry.setdefault(name, []).append(path)
    return registry


# Collisions connues et documentées — retirer de cette liste au fur et à mesure
# des refactorings. Toute collision NON listée ici fait échouer le test.
_KNOWN_COLLISIONS: dict[str, set[str]] = {
    "DocSection": {"document.py", "doc_vision.py"},
    "DynamicPromptBuilder": {"dynamic_prompt.py", "prompt_builder.py"},
    "EvalResult": {"__init__.py", "self_eval.py"},
    "MetricProgress": {"performance_page.py", "stats_page.py"},
    "SearchResult": {"types.py", "web.py"},
    "SectionHeader": {"performance_page.py", "stats_page.py"},
}


def _filename(path: str) -> str:
    return Path(path).name


def test_no_class_name_collisions() -> None:
    """Alerte sur les collisions connues, ÉCHOUE sur les nouvelles."""
    registry = _collect_all_classes()
    collisions = {name: paths for name, paths in registry.items() if len(paths) > 1}

    new_collisions: dict[str, list[str]] = {}
    known_issues: list[str] = []

    for name, paths in sorted(collisions.items()):
        filenames = {_filename(p) for p in paths}
        known = _KNOWN_COLLISIONS.get(name, set())
        if filenames == known:
            known_issues.append(f"  ⚠️  {name} (connue) : {', '.join(sorted(paths))}")
        else:
            new_collisions[name] = paths

    # Journaliser les connues
    if known_issues:
        print("\n📦 Collisions connues (à refactorer) :")
        for line in known_issues:
            print(line)

    # Échouer sur les nouvelles
    if new_collisions:
        msg_lines = ["❌ NOUVELLES collisions de noms de classes :"]
        for name, paths in sorted(new_collisions.items()):
            msg_lines.append(f"  - {name} dans :")
            for p in paths:
                msg_lines.append(f"      {p}")
        pytest.fail("\n".join(msg_lines))


def test_known_class_count() -> None:
    """Vérifie que le nombre total de classes est cohérent (détection de régression)."""
    registry = _collect_all_classes()
    total = len(registry)
    # Seuil minimal — doit être >= 50 classes dans un projet de cette taille
    assert total >= 50, f"Trop peu de classes ({total}) — scan peut-être incomplet"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
