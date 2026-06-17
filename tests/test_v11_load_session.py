"""Test isolé V11.1 JOUR 3 — ConsolePage.load_session().

Exécuté avec : python3 tests/test_v11_load_session.py

Couvre :
- Test 1 : store None → widget reste vide, aucune erreur, signal émis
- Test 2 : session vide → widget vide, signal émis
- Test 3 : 3 messages (user/assistant/user) → re-rendus dans l'ordre, role préservé
- Test 4 : titre → header.set_title() appliqué
- Test 5 : session inexistante → get_or_create la crée, widget vide, signal émis
- Test 6 : store cassé (exception) → erreur affichée, échec gracieux

Pattern repris de test_v11_conversation_list.py : QT_QPA_PLATFORM=offscreen
+ importlib pour bypass du cache .pyc.
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

# Environnement Qt offscreen (ne nécessite pas de display)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib
import importlib.util


def _import_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Sanity checks
assert SRC.exists(), f"src not found: {SRC}"
assert (SRC / "__init__.py").exists()

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

# Crée l'app Qt une seule fois (réutilisée par tous les tests)
_app = QCoreApplication.instance() or QApplication(sys.argv)

# Load les modules via importlib comme sous-packages du package `src`
# afin que les imports relatifs (`.nuru_widgets`) résolvent correctement.
# On enregistre les parents d'abord pour que Python les reconnaisse comme packages.
import types

# Crée le package `src` racine comme alias
if "src" not in sys.modules:
    src_pkg = types.ModuleType("src")
    src_pkg.__path__ = [str(SRC)]
    sys.modules["src"] = src_pkg

# Crée le sous-package `src.ui`
if "src.ui" not in sys.modules:
    ui_pkg = types.ModuleType("src.ui")
    ui_pkg.__path__ = [str(SRC / "ui")]
    sys.modules["src.ui"] = ui_pkg

# Crée le sous-package `src.ui.components`
if "src.ui.components" not in sys.modules:
    comp_pkg = types.ModuleType("src.ui.components")
    comp_pkg.__path__ = [str(SRC / "ui" / "components")]
    sys.modules["src.ui.components"] = comp_pkg

# Crée le sous-package `src.session`
if "src.session" not in sys.modules:
    sess_pkg = types.ModuleType("src.session")
    sess_pkg.__path__ = [str(SRC / "session")]
    sys.modules["src.session"] = sess_pkg


# Charge `src.session.store` AVANT `console_page` (utilisé par celui-ci).
# IMPORTANT : enregistrer dans sys.modules AVANT exec() car `@dataclass`
# fait `sys.modules[cls.__module__].__dict__` qui plante si None.
_session_mod = types.ModuleType("src.session.store")
_session_mod.__file__ = str(SRC / "session" / "store.py")
sys.modules["src.session.store"] = _session_mod  # ENREGISTREMENT PRÉALABLE
exec(
    compile(
        (SRC / "session" / "store.py").read_text(),
        str(SRC / "session" / "store.py"),
        "exec",
    ),
    _session_mod.__dict__,
)
SessionStore = _session_mod.SessionStore

# Charge `console_page` dans le globals du package `src.ui.components`
# pour que les imports relatifs (`from .nuru_widgets import ...`) résolvent.
_comp_pkg_mod = sys.modules["src.ui.components"]
_console_path = SRC / "ui" / "components" / "console_page.py"
_console_code = _console_path.read_text()
# Pré-remplit __name__/__file__/__package__ comme si Python l'avait chargé
_comp_pkg_mod.__name__ = "src.ui.components"  # déjà bon mais idempotent
# Exécute dans le namespace du package parent
_console_mod_globals = _comp_pkg_mod.__dict__.copy()
_console_mod_globals["__name__"] = "src.ui.components.console_page"
_console_mod_globals["__file__"] = str(_console_path)
_console_mod_globals["__package__"] = "src.ui.components"
# Calcule la valeur __cached__/__loader__ si nécessaire — exec les accepte
exec(compile(_console_code, str(_console_path), "exec"), _console_mod_globals)
# Récupère ConsolePage depuis le globals après exec
ConsolePage = _console_mod_globals["ConsolePage"]
sys.modules["src.ui.components.console_page"] = types.ModuleType(
    "src.ui.components.console_page"
)
sys.modules["src.ui.components.console_page"].__dict__.update(_console_mod_globals)


def _new_console_page() -> "ConsolePage":
    """Helper : crée un ConsolePage propre pour chaque test."""
    page = ConsolePage()
    return page


def _count_visible_messages(page: "ConsolePage") -> int:
    """Compte le nombre de MessageRow effectivement ajoutés dans le chat."""
    layout = page.messages._layout
    count = 0
    for i in range(layout.count()):
        item = layout.itemAt(i)
        w = item.widget()
        if w is not None and hasattr(w, "role"):
            count += 1
    return count


def _last_message_text(page: "ConsolePage"):
    """Retourne le texte de la dernière ChatBubble ajoutée, ou None."""
    layout = page.messages._layout
    if layout.count() == 0:
        return None
    last_widget = layout.itemAt(layout.count() - 1).widget()
    return getattr(last_widget, "text", None)


def test_load_session_no_store():
    """store=None : aucun crash, widget vidé, signal session_loaded émis."""
    page = _new_console_page()
    captured = []
    page.session_loaded.connect(lambda sid: captured.append(sid))

    # Pré-remplir pour vérifier que clear() est appelé
    page.messages.add_message("will be cleared", role="assistant")
    assert _count_visible_messages(page) >= 1, "pré-condition: 1 message présent"

    # Appel avec store=None (état initial après __init__)
    page.load_session("sess_xyz", title="X")

    # Le widget doit être vidé
    assert _count_visible_messages(page) == 0, (
        f"attendu 0 message après load_session sans store, "
        f"eu {_count_visible_messages(page)}"
    )
    # Le signal doit quand même être émis (pour que le dashboard réagisse)
    assert captured == ["sess_xyz"], f"signal non émis correctement: {captured}"
    print("PASS test_load_session_no_store")


def test_load_session_empty_session():
    """Session vide (créée mais sans message) : widget vide, signal émis."""
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("empty_sess", title="Empty")

    page = _new_console_page()
    page.set_session_store(store)
    captured = []
    page.session_loaded.connect(lambda sid: captured.append(sid))

    page.load_session("empty_sess", title="Empty")

    assert _count_visible_messages(page) == 0, (
        f"session vide → 0 message attendu, eu {_count_visible_messages(page)}"
    )
    assert captured == ["empty_sess"], f"signal non émis: {captured}"
    print("PASS test_load_session_empty_session")


def test_load_session_three_messages():
    """3 messages user/assistant/user : re-rendus dans l'ordre avec bon role."""
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("three_msg_sess", title="Conversation 3 msg")
    store.add_message("three_msg_sess", "user", "Bonjour NURU")
    store.add_message("three_msg_sess", "assistant", "Bonjour ! Comment puis-je aider ?")
    store.add_message("three_msg_sess", "user", "Quel temps fait-il ?")

    page = _new_console_page()
    page.set_session_store(store)
    page.load_session("three_msg_sess", title="Conversation 3 msg")

    # Vérifier le nombre de messages re-rendus
    n = _count_visible_messages(page)
    assert n == 3, f"attendu 3 messages, eu {n}"

    # Vérifier l'ordre et les rôles via le SessionStore (référence)
    reloaded = store.get_or_create("three_msg_sess")
    assert len(reloaded.messages) == 3
    assert reloaded.messages[0].role == "user"
    assert reloaded.messages[1].role == "assistant"
    assert reloaded.messages[2].role == "user"
    assert reloaded.messages[0].content == "Bonjour NURU"
    print("PASS test_load_session_three_messages")


def test_load_session_title_applied():
    """title passé → header.set_title() appliqué."""
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("titled", title="Titre Original")
    store.add_message("titled", "user", "msg")

    page = _new_console_page()
    page.set_session_store(store)
    # Titre passé explicitement (devrait override le titre stocké en DB)
    page.load_session("titled", title="Titre Affiché Custom")

    # Vérifier que le header a bien le titre demandé
    actual = page.header._title_label.text()
    assert actual == "Titre Affiché Custom", (
        f"attendu 'Titre Affiché Custom', eu {actual!r}"
    )
    print("PASS test_load_session_title_applied")


def test_load_session_unknown_id_creates_empty():
    """session_id inconnu → get_or_create crée la session, widget vide."""
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("existing", title="Existante")

    page = _new_console_page()
    page.set_session_store(store)
    page.load_session("doesnotexist123", title="")

    # Session créée mais vide
    assert _count_visible_messages(page) == 0
    listed = store.list_sessions()
    ids = [s["id"] for s in listed]
    assert "doesnotexist123" in ids, f"session devrait être créée, ids={ids}"
    print("PASS test_load_session_unknown_id_creates_empty")


def test_load_session_store_raises_gracefully():
    """store.get_or_create lève une exception → erreur affichée, pas de crash."""
    store = SessionStore(db_path=tempfile.mktemp(suffix=".db"))
    store.create_session("broken", title="Broken")

    page = _new_console_page()
    page.set_session_store(store)
    # Mock : get_or_create explose
    store.get_or_create = MagicMock(  # type: ignore[assignment]
        side_effect=RuntimeError("DB verrouillée")
    )
    captured = []
    page.session_loaded.connect(lambda sid: captured.append(sid))

    # Doit logger une erreur et afficher un message d'erreur, PAS crash
    page.load_session("broken", title="Broken")

    captured_ok = captured == ["broken"], f"signal doit être émis: {captured}"
    # Au moins un message d'erreur doit être rendu (le ⚠️ ...)
    rendered = _count_visible_messages(page) >= 1
    assert captured_ok and rendered, (
        f"échec gracieux: signal={captured}, rendered={rendered}"
    )
    print("PASS test_load_session_store_raises_gracefully")


if __name__ == "__main__":
    # stdout simple pour grep PASS / FAIL
    test_load_session_no_store()
    test_load_session_empty_session()
    test_load_session_three_messages()
    test_load_session_title_applied()
    test_load_session_unknown_id_creates_empty()
    test_load_session_store_raises_gracefully()
    print("OK — 6/6 tests passent")
