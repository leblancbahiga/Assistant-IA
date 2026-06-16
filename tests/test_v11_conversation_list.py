"""Test isolé P0-J V11.1 — ConversationList.

Exécuté avec : python3 tests/test_v11_conversation_list.py
- Test 1 : store vide → empty label visible, list cachée
- Test 2 : ajout de 3 sessions → 3 items dans la liste, signal émis au clic
- Test 3 : store None → empty label "indisponible"
- Test 4 : _format_relative_date sur timestamps variés
"""

import os
import sys
import tempfile
import time
from pathlib import Path

# Force src on path (avant TOUT import)
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Environnement Qt offscreen (ne nécessite pas de display)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# V11.1 — import via importlib pour bypass namespace caching
import importlib
import importlib.util

def _import_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

# Vérification rapide que src existe
assert SRC.exists(), f"src not found: {SRC}"
assert (SRC / "__init__.py").exists(), f"src/__init__.py missing"

from PySide6.QtWidgets import QApplication

# Charge les modules explicitement via importlib
_session = _import_from_path("src.session.store", SRC / "session" / "store.py")
SessionStore = _session.SessionStore
_cl = _import_from_path("src.ui.components.conversation_list", SRC / "ui" / "components" / "conversation_list.py")
ConversationList = _cl.ConversationList
_format_relative_date = _cl._format_relative_date


def test_empty_store():
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("a1", title="Session A")
    widget = ConversationList(session_store=store)
    # Store avec 1 seule session = 1 item visible
    assert widget._list.count() == 1
    # Cache la session puis teste empty
    store.delete_session("a1")
    widget.refresh()
    assert widget._list.count() == 0
    # En mode offscreen, le widget peut ne pas être visible visuellement,
    # mais isHidden() reflète l'état logique du widget.
    assert widget._empty_label.isHidden() is False
    print("PASS test_empty_store")


def test_three_sessions():
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("s1", title="Analyse RAG")
    time.sleep(0.5)
    store.create_session("s2", title="Mémoire procédure")
    time.sleep(0.5)
    store.create_session("s3", title="Indexation docs")
    # add_message MUTATE updated_at → on le fait AVANT la dernière create
    # Pour ce test on skip les messages et on teste l'ordre chronologique
    # de création (DESC).

    widget = ConversationList(session_store=store)
    raw = store.list_sessions()
    assert widget._list.count() == 3, f"attendu 3 items, eu {widget._list.count()}"

    # Vérifier ordre : plus récent en premier (updated_at DESC)
    all_ids = [widget._list.item(i).data(0x0100) for i in range(widget._list.count())]
    assert all_ids[0] == "s3", f"attendu s3 en tête, eu {all_ids[0]}"
    assert all_ids[-1] == "s1", f"attendu s1 en queue, eu {all_ids[-1]}"

    print("PASS test_three_sessions")


def test_signal_emitted_on_click():
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("click1", title="Test click")

    widget = ConversationList(session_store=store)

    captured = []
    widget.session_selected.connect(lambda sid: captured.append(sid))

    # Simuler un clic sur le 1er item
    widget._list.setCurrentRow(0)
    widget._on_item_clicked(widget._list.item(0))

    assert captured == ["click1"], f"signal capturé: {captured}"
    print("PASS test_signal_emitted_on_click")


def test_new_conversation_button():
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    widget = ConversationList(session_store=store)

    captured = []
    widget.new_conversation_requested.connect(lambda: captured.append(True))

    # Test direct du signal : clic simulé
    widget._new_btn.click()
    assert captured == [True], f"signal new_conv: {captured}"
    print("PASS test_new_conversation_button")


def test_store_none():
    widget = ConversationList(session_store=None)
    assert widget._list.count() == 0
    # isHidden() plutôt que isVisible() en mode test offscreen
    assert widget._empty_label.isHidden() is False
    assert "indisponible" in widget._empty_label.text()
    print("PASS test_store_none")


def test_format_relative_date():
    now = time.time()
    cases = [
        (now, "à l'instant"),
        (now - 30, "à l'instant"),
        (now - 120, "il y a 2min"),
        (now - 7200, "il y a 2h"),
        (now - 86400 * 3, "il y a 3j"),
    ]
    for ts, expected in cases:
        result = _format_relative_date(ts)
        assert result == expected, f"ts={ts}, expected={expected!r}, got={result!r}"
    print("PASS test_format_relative_date")


def test_max_displayed_limit():
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    for i in range(15):
        store.create_session(f"s{i:02d}", title=f"Conv {i}")
        time.sleep(0.01)

    widget = ConversationList(session_store=store)
    assert widget._list.count() == 10, (
        f"attendu 10 items (MAX_DISPLAYED), eu {widget._list.count()}"
    )
    print("PASS test_max_displayed_limit")


def test_message_counter():
    """Le compteur de messages apparaît dès qu'on add_message."""
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("s1", title="Avec messages")
    # NE PAS add_message AVANT la création d'autres sessions pour
    # ne pas fausser l'order — ici on teste juste le compteur.
    store.add_message("s1", "user", "Hello")
    store.add_message("s1", "assistant", "Hi!")

    widget = ConversationList(session_store=store)
    assert widget._list.count() == 1
    label = widget._list.item(0).text()
    assert "2 msgs" in label, f"compteur msgs manquant: {label!r}"
    print("PASS test_message_counter")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    test_empty_store()
    test_three_sessions()
    test_signal_emitted_on_click()
    test_new_conversation_button()
    test_store_none()
    test_format_relative_date()
    test_max_displayed_limit()
    test_message_counter()
    print("\n✅ 8/8 tests P0-J V11.1 ConversationList — OK")


if __name__ == "__main__":
    main()
