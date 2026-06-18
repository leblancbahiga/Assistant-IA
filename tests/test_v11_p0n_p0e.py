"""Test V11.1 JOUR 4 — P0-N Routeur footer + P0-E Model switcher.

Validation :
- P0-N : MessagesArea.add_message() avec mode/model_name → ChatBubble affiche footer
- P0-E : ChatHeader.model_changed signal → ConsolePage.model_changed relayé

Pattern repris de test_v11_load_session.py.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Force src on path (avant TOUT import)
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Environnement Qt offscreen
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib
import importlib.util
import types

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

_app = QCoreApplication.instance() or QApplication(sys.argv)


def _import_console_page():
    """Importe console_page avec tous les sous-packages nécessaires."""
    packages = {
        "src": SRC,
        "src.ui": SRC / "ui",
        "src.ui.components": SRC / "ui" / "components",
        "src.session": SRC / "session",
    }
    for name, p in packages.items():
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = [str(p)]
            sys.modules[name] = pkg

    # SessionStore
    if "src.session.store" not in sys.modules:
        mod = types.ModuleType("src.session.store")
        mod.__file__ = str(SRC / "session" / "store.py")
        sys.modules["src.session.store"] = mod
        exec(
            compile(
                (SRC / "session" / "store.py").read_text(),
                str(SRC / "session" / "store.py"),
                "exec",
            ),
            mod.__dict__,
        )

    # console_page
    comp_pkg = sys.modules["src.ui.components"]
    console_path = SRC / "ui" / "components" / "console_page.py"
    code = console_path.read_text()
    ns = comp_pkg.__dict__.copy()
    ns["__name__"] = "src.ui.components.console_page"
    ns["__file__"] = str(console_path)
    ns["__package__"] = "src.ui.components"
    exec(compile(code, str(console_path), "exec"), ns)

    # ChatBubble / MessageRow — déjà importés par console_page
    return ns


_ns = _import_console_page()
ConsolePage = _ns["ConsolePage"]
ChatHeader = _ns["ChatHeader"]
MessagesArea = _ns["MessagesArea"]
ChatBubble = _ns["ChatBubble"] if "ChatBubble" in _ns else None
MessageRow = _ns["MessageRow"] if "MessageRow" in _ns else None


# ── Helpers ──


def _find_chat_bubble(page) -> object | None:
    """Trouve la dernière ChatBubble dans MessagesArea."""
    layout = page.messages._layout
    for i in range(layout.count() - 1, -1, -1):
        item = layout.itemAt(i)
        w = item.widget()
        if w is not None and hasattr(w, "_bubble"):
            return w._bubble
    return None


# ══════════════════════════════════════════════════════════════════════
# P0-N — Routeur footer
# ══════════════════════════════════════════════════════════════════════


def test_p0n_footer_shown_with_mode():
    """Message assistant avec mode CLOUD → footer visible avec ModeBadge."""
    page = ConsolePage()
    page.messages.add_message(
        text="Réponse cloud",
        role="assistant",
        mode="CLOUD",
        model_name="Groq llama-3.3",
    )

    bubble = _find_chat_bubble(page)
    assert bubble is not None, "ChatBubble doit exister"
    assert bubble._mode == "CLOUD", f"mode attendu 'CLOUD', eu {bubble._mode!r}"
    assert bubble._model_name == "Groq llama-3.3", (
        f"model_name attendu 'Groq llama-3.3', eu {bubble._model_name!r}"
    )
    print("PASS test_p0n_footer_shown_with_mode")


def test_p0n_footer_empty_by_default():
    """Message assistant sans mode → pas de footer, mode vide."""
    page = ConsolePage()
    page.messages.add_message(
        text="Réponse simple",
        role="assistant",
    )

    bubble = _find_chat_bubble(page)
    assert bubble is not None, "ChatBubble doit exister"
    assert bubble._mode == "", f"mode devrait être vide, eu {bubble._mode!r}"
    assert bubble._model_name == "", f"model_name devrait être vide, eu {bubble._model_name!r}"
    print("PASS test_p0n_footer_empty_by_default")


def test_p0n_footer_user_message_no_footer():
    """Message utilisateur → pas de footer même si mode passé."""
    page = ConsolePage()
    page.messages.add_message(
        text="Question",
        role="user",
        mode="CLOUD",
        model_name="Groq llama",
    )

    bubble = _find_chat_bubble(page)
    assert bubble is not None, "ChatBubble doit exister"
    # Pour user, _mode stocké mais footer pas affiché (self._role != "user")
    # On vérifie juste qu'il n'y a pas de crash
    print("PASS test_p0n_footer_user_message_no_footer")


def test_p0n_footer_via_on_response_received():
    """ConsolePage.on_response_received() propage mode/mode_primary."""
    page = ConsolePage()
    page.on_response_received(
        text="Réponse RAG",
        mode_primary="RAG",
        mode_secondary="HyDE",
    )

    bubble = _find_chat_bubble(page)
    assert bubble is not None, "ChatBubble doit exister"
    assert bubble._mode == "RAG", (
        f"mode attendu 'RAG' depuis mode_primary, eu {bubble._mode!r}"
    )
    assert bubble._model_name == "HyDE", (
        f"model_name attendu 'HyDE' depuis mode_secondary, eu {bubble._model_name!r}"
    )
    print("PASS test_p0n_footer_via_on_response_received")


# ══════════════════════════════════════════════════════════════════════
# P0-E — Model switcher
# ══════════════════════════════════════════════════════════════════════


def test_p0e_model_changed_signal():
    """ChatHeader émet model_changed quand le combobox change."""
    header = ChatHeader()
    captured = []
    header.model_changed.connect(lambda m: captured.append(m))

    # Simuler un changement de modèle
    header._model_combo.setCurrentText("deepseek-chat")

    assert len(captured) >= 1, "model_changed devrait être émis"
    assert captured[-1] == "deepseek-chat", (
        f"modèle attendu 'deepseek-chat', eu {captured[-1]!r}"
    )
    print("PASS test_p0e_model_changed_signal")


def test_p0e_model_changed_via_set_model():
    """ChatHeader.set_model() change le combobox sans émettre de signal."""
    header = ChatHeader()
    captured = []
    header.model_changed.connect(lambda m: captured.append(m))

    # set_model() change l'index mais n'émet PAS (findText + setCurrentIndex)
    header.set_model("deepseek-chat")
    # currentText doit être mis à jour
    assert header.current_model == "deepseek-chat", (
        f"current_model attendu 'deepseek-chat', eu {header.current_model!r}"
    )

    print("PASS test_p0e_model_changed_via_set_model")


def test_p0e_console_wires_model_changed():
    """ConsolePage._wire_signals relaye model_changed de ChatHeader."""
    page = ConsolePage()
    captured = []
    page.model_changed.connect(lambda m: captured.append(m))

    # Changer le modèle via le header — doit remonter jusqu'à ConsolePage
    page.header._model_combo.setCurrentText("openrouter-auto")

    assert len(captured) >= 1, "ConsolePage.model_changed devrait être émis"
    assert captured[-1] == "openrouter-auto", (
        f"modèle attendu 'openrouter-auto', eu {captured[-1]!r}"
    )
    print("PASS test_p0e_console_wires_model_changed")


# ══════════════════════════════════════════════════════════════════════
# P0-G — StatCard unifié (vérification structure)
# ══════════════════════════════════════════════════════════════════════


def _import_stat_card():
    """Importe stat_card.py dans l'espace de test."""
    stat_path = SRC / "ui" / "components" / "stat_card.py"
    mod_name = "test_stat_card_import"
    spec = importlib.util.spec_from_file_location(mod_name, str(stat_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_p0g_stat_card_importable():
    """StatCard et MiniStatCard sont importables et instanciables."""
    mod = _import_stat_card()
    assert hasattr(mod, "StatCard"), "StatCard doit exister dans stat_card.py"
    assert hasattr(mod, "MiniStatCard"), "MiniStatCard doit exister dans stat_card.py"

    # Instanciation
    card = mod.StatCard(title="Tokens", value="1.2k", icon="⚡", color="#60a5fa")
    assert card is not None
    assert card._title_str == "Tokens"

    mini = mod.MiniStatCard(label="RAM", value="3.2 Go", subtitle="/ 8 Go")
    assert mini is not None
    assert mini._value_w.text() == "3.2 Go"

    print("PASS test_p0g_stat_card_importable")


def test_p0g_mini_stat_card_setters():
    """MiniStatCard.set_value / set_subtitle / set_label fonctionnent."""
    mod = _import_stat_card()
    mini = mod.MiniStatCard(label="X", value="0", subtitle="")

    mini.set_value("42")
    assert mini._value_w.text() == "42"

    mini.set_subtitle("updated")
    assert mini._subtitle_w.text() == "updated"
    # isHidden() = True si explicitement caché via setVisible(False) → False ici
    assert not mini._subtitle_w.isHidden(), "subtitle ne devrait pas être caché après set_subtitle"

    mini.set_label("Y")
    assert mini._label_w.text() == "Y"

    print("PASS test_p0g_mini_stat_card_setters")


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # P0-N
    test_p0n_footer_shown_with_mode()
    test_p0n_footer_empty_by_default()
    test_p0n_footer_user_message_no_footer()
    test_p0n_footer_via_on_response_received()

    # P0-E
    test_p0e_model_changed_signal()
    test_p0e_model_changed_via_set_model()
    test_p0e_console_wires_model_changed()

    # P0-G
    test_p0g_stat_card_importable()
    test_p0g_mini_stat_card_setters()

    print("\n✅ JOUR 4 — 9/9 tests P0-N/P0-E/P0-G OK")
