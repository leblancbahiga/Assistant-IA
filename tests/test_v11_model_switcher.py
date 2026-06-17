"""Test V11.1 P0-E — Model switcher dans ChatHeader.

Couvre :
- Test 1 : ChatHeader a un QComboBox avec les modèles par défaut
- Test 2 : set_model() sélectionne le bon index
- Test 3 : current_model retourne le modèle actif
- Test 4 : model_changed émis quand l'utilisateur change de modèle
- Test 5 : ConsolePage.model_changed relayé depuis ChatHeader
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib
import importlib.util
import types

from PySide6.QtWidgets import QApplication, QWidget, QComboBox
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


def test_chat_header_has_model_combobox():
    """ChatHeader doit avoir un QComboBox avec les modèles."""
    from src.ui.components.console_page import ChatHeader

    header = ChatHeader()
    combo = header.findChild(QComboBox)
    assert combo is not None, "Un QComboBox doit être présent dans ChatHeader"
    assert combo.count() >= 3, (
        f"Au moins 3 modèles, trouvé {combo.count()}"
    )
    print(f"PASS test_chat_header_has_model_combobox ({combo.count()} modèles)")


def test_set_model_selects_correct_index():
    """set_model('deepseek-chat') sélectionne le bon item."""
    from src.ui.components.console_page import ChatHeader

    header = ChatHeader()
    header.set_model("deepseek-chat")
    assert header.current_model == "deepseek-chat", (
        f"expected deepseek-chat, got {header.current_model}"
    )
    print(f"PASS test_set_model_selects_correct_index: {header.current_model}")


def test_set_model_unknown_keeps_current():
    """set_model('inexistant') ne change pas la sélection."""
    from src.ui.components.console_page import ChatHeader

    header = ChatHeader()
    default = header.current_model
    header.set_model("modèle-inconnu-xyz")
    assert header.current_model == default, (
        f"devrait rester sur '{default}', a changé vers '{header.current_model}'"
    )
    print(f"PASS test_set_model_unknown_keeps_current: toujours '{default}'")


def test_model_changed_signal_emitted():
    """Changer le modèle émet model_changed(str)."""
    from src.ui.components.console_page import ChatHeader

    header = ChatHeader()
    received = []

    def on_change(model: str):
        received.append(model)

    header.model_changed.connect(on_change)
    header.set_model("llama-3.3-70b (groq)")
    assert len(received) == 1, f"attendu 1 émission, eu {len(received)}"
    assert received[0] == "llama-3.3-70b (groq)", (
        f"attendu 'llama-3.3-70b (groq)', eu {received[0]}"
    )
    print("PASS test_model_changed_signal_emitted")


def test_console_page_relays_model_changed():
    """ConsolePage.model_changed relayé depuis ChatHeader."""
    from src.ui.components.console_page import ConsolePage

    page = ConsolePage()
    received = []

    def on_change(model: str):
        received.append(model)

    page.model_changed.connect(on_change)
    page.header.set_model("deepseek-chat")
    assert len(received) == 1, f"attendu 1 émission, eu {len(received)}"
    assert received[0] == "deepseek-chat", (
        f"attendu 'deepseek-chat', eu {received[0]}"
    )
    print("PASS test_console_page_relays_model_changed")


if __name__ == "__main__":
    test_chat_header_has_model_combobox()
    test_set_model_selects_correct_index()
    test_set_model_unknown_keeps_current()
    test_model_changed_signal_emitted()
    test_console_page_relays_model_changed()
    print("\n✅ OK — 5/5 tests P0-E passent")
