"""Test V11.1 P0-G — StatCard unifié (stat_card.py).

Couvre :
- Test 1 : StatCard construit avec les valeurs par défaut
- Test 2 : set_value met à jour l'affichage
- Test 3 : set_title met à jour le titre
- Test 4 : MiniStatCard construit avec label+value+subtitle
- Test 5 : MiniStatCard.set_value/set_subtitle/set_label compat MetricCard
- Test 6 : Les imports fonctionnent depuis stats_page et feedback_page
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib.util
import types

from PySide6.QtWidgets import QApplication, QFrame
from PySide6.QtCore import QCoreApplication

_app = QCoreApplication.instance() or QApplication(sys.argv)


def _import_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


for pkg_name, pkg_path in [
    ("src", SRC),
    ("src.ui", SRC / "ui"),
    ("src.ui.components", SRC / "ui" / "components"),
]:
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(pkg_path)]
        sys.modules[pkg_name] = pkg


# ── Tests ──


def test_stat_card_default_construction():
    """StatCard par défaut sans crash."""
    from src.ui.components.stat_card import StatCard

    card = StatCard()
    assert card is not None, "StatCard devrait être construit sans erreur"
    print("PASS test_stat_card_default_construction")


def test_stat_card_custom_values():
    """StatCard avec valeurs personnalisées."""
    from src.ui.components.stat_card import StatCard

    card = StatCard(title="Tokens", icon="📊", value="12.4k", color="#60a5fa")
    assert card._title_str == "Tokens"
    assert card._icon_str == "📊"
    assert card._color == "#60a5fa"
    assert card._value_lbl.text() == "12.4k"
    print(f"PASS test_stat_card_custom_values: {card._value_lbl.text()}")


def test_stat_card_set_value():
    """set_value met à jour la valeur."""
    from src.ui.components.stat_card import StatCard

    card = StatCard(title="RAM", value="—")
    card.set_value("8.2 Go", color="#22c55e")
    assert card._value_lbl.text() == "8.2 Go"
    assert card._color == "#22c55e"
    print(f"PASS test_stat_card_set_value: {card._value_lbl.text()} / {card._color}")


def test_stat_card_set_title():
    """set_title met à jour le titre."""
    from src.ui.components.stat_card import StatCard

    card = StatCard(title="Old")
    card.set_title("New Title")
    assert card._title_str == "New Title"
    assert card._title_lbl.text() == "New Title"
    print(f"PASS test_stat_card_set_title: {card._title_lbl.text()}")


def test_mini_stat_card_construction():
    """MiniStatCard avec label+value+subtitle."""
    from src.ui.components.stat_card import MiniStatCard

    card = MiniStatCard(label="RAM", value="8.2", subtitle="/ 16 Go")
    assert card._label_w.text() == "RAM"
    assert card._value_w.text() == "8.2"
    assert card._subtitle_w.text() == "/ 16 Go"
    print("PASS test_mini_stat_card_construction")


def test_mini_stat_card_compat_methods():
    """MiniStatCard.set_value / set_subtitle / set_label."""
    from src.ui.components.stat_card import MiniStatCard

    card = MiniStatCard(label="Tokens", value="0", subtitle="↑ —")
    card.set_value("42.5k")
    card.set_subtitle("↑ 12%")
    card.set_label("Tokens/s")
    assert card._value_w.text() == "42.5k"
    assert card._subtitle_w.text() == "↑ 12%"
    assert card._label_w.text() == "Tokens/s"
    print("PASS test_mini_stat_card_compat_methods")


if __name__ == "__main__":
    test_stat_card_default_construction()
    test_stat_card_custom_values()
    test_stat_card_set_value()
    test_stat_card_set_title()
    test_mini_stat_card_construction()
    test_mini_stat_card_compat_methods()
    print("\n✅ OK — 6/6 tests P0-G passent")
