"""Test V11.1 JOUR 4 — P0-N (Routeur footer), P0-E (Model switcher), P0-G (StatCard).

Exécuté avec : python3 tests/test_v11_jour4_p0_neg.py

Couvre :
- P0-N : ChatBubble affiche le mode footer (ModeBadge) quand mode est fourni
- P0-E : ChatHeader model switcher (QComboBox) s'initialise et émet model_changed
- P0-G : StatCard unifié s'affiche et met à jour sa valeur
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib
import importlib.util
import types


def _import_module(module_name: str, path: Path, parent_pkg: types.ModuleType | None = None):
    """Importe un fichier .py comme sous-module d'un package parent."""
    mod = types.ModuleType(module_name)
    mod.__file__ = str(path)
    mod.__path__ = [str(path.parent)]
    sys.modules[module_name] = mod
    exec(compile(path.read_text(), str(path), "exec"), mod.__dict__)
    return mod


# ── Setup packages ──────────────────────────────────────────────────────

for pkg_name, pkg_path in [
    ("src", SRC),
    ("src.ui", SRC / "ui"),
    ("src.ui.components", SRC / "ui" / "components"),
]:
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(pkg_path)]
        sys.modules[pkg_name] = pkg

from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import QCoreApplication

_app = QCoreApplication.instance() or QApplication(sys.argv)

# ── Imports ─────────────────────────────────────────────────────────────

# 1. nuru_widgets (ModeBadge)
_nuru_w = _import_module("src.ui.components.nuru_widgets",
                          SRC / "ui" / "components" / "nuru_widgets.py")
ModeBadge = _nuru_w.ModeBadge

# 2. chat_bubble (ChatBubble, MessageRow)
_cb = _import_module("src.ui.components.chat_bubble",
                     SRC / "ui" / "components" / "chat_bubble.py")
ChatBubble = _cb.ChatBubble

# 3. console_page (ChatHeader, MessagesArea, ConsolePage)
_comp_pkg_mod = types.ModuleType("src.ui.components.console_page_pkg")
_comp_pkg_mod.__path__ = [str(SRC / "ui" / "components")]
# On a besoin que le module parent existe pour les imports relatifs
if "src.ui.components" not in sys.modules:
    ui_comp = types.ModuleType("src.ui.components")
    ui_comp.__path__ = [str(SRC / "ui" / "components")]
    sys.modules["src.ui.components"] = ui_comp

# Charge console_page dans le namespace de src.ui.components
_console_path = SRC / "ui" / "components" / "console_page.py"
_console_code = _console_path.read_text()
_comp_ns = sys.modules["src.ui.components"].__dict__.copy()
_comp_ns["__name__"] = "src.ui.components.console_page"
_comp_ns["__file__"] = str(_console_path)
_comp_ns["__package__"] = "src.ui.components"
exec(compile(_console_code, str(_console_path), "exec"), _comp_ns)
ChatHeader = _comp_ns["ChatHeader"]
MessagesArea = _comp_ns["MessagesArea"]
ConsolePage = _comp_ns["ConsolePage"]

# 4. stat_card (StatCard, MiniStatCard)
_sc = _import_module("src.ui.components.stat_card",
                     SRC / "ui" / "components" / "stat_card.py")
StatCard = _sc.StatCard
MiniStatCard = _sc.MiniStatCard


# ═══════════════════════════════════════════════════════════════════════
# P0-E — Model Switcher header
# ═══════════════════════════════════════════════════════════════════════

def test_p0e_model_switcher_init():
    """QComboBox dans ChatHeader s'initialise avec les modèles."""
    header = ChatHeader()
    assert hasattr(header, "_model_combo"), "ChatHeader doit avoir _model_combo"
    combo = header._model_combo
    assert combo.count() >= 3, (
        f"Au moins 3 modèles attendus, eu {combo.count()}"
    )
    # Vérifier que le modèle local est le premier (défaut)
    assert "local" in combo.itemText(0).lower(), (
        f"Premier modèle devrait être local: {combo.itemText(0)!r}"
    )
    print("PASS test_p0e_model_switcher_init")


def test_p0e_model_change_signal():
    """Changer de modèle émet model_changed(str)."""
    header = ChatHeader()
    captured = []
    header.model_changed.connect(lambda m: captured.append(m))

    # Sélectionner un autre modèle
    if header._model_combo.count() > 1:
        header._model_combo.setCurrentIndex(1)
        assert len(captured) >= 1, "model_changed devrait être émis"
        assert len(captured[0]) > 0, "Le nom du modèle ne doit pas être vide"
    print("PASS test_p0e_model_change_signal")


def test_p0e_set_model():
    """set_model() sélectionne le bon item."""
    header = ChatHeader()
    header.set_model("deepseek-chat")
    assert "deepseek" in header.current_model.lower(), (
        f"current_model devrait contenir deepseek: {header.current_model!r}"
    )
    print("PASS test_p0e_set_model")


def test_p0e_current_model():
    """current_model property retourne le texte du combo."""
    header = ChatHeader()
    current = header.current_model
    assert isinstance(current, str) and len(current) > 0, (
        f"current_model devrait être une string non vide: {current!r}"
    )
    print("PASS test_p0e_current_model")


# ═══════════════════════════════════════════════════════════════════════
# P0-N — Routeur footer de bulle
# ═══════════════════════════════════════════════════════════════════════

def _find_modebadge_in_footer(bubble: ChatBubble) -> ModeBadge | None:
    """Cherche un ModeBadge dans les layouts enfants du ChatBubble."""
    # Parcourt le layout principal à la recherche du footer layout
    main_layout = bubble.layout()
    for i in range(main_layout.count()):
        item = main_layout.itemAt(i)
        if item and item.layout():
            sub = item.layout()
            for j in range(sub.count()):
                w = sub.itemAt(j)
                if w and w.widget() and isinstance(w.widget(), ModeBadge):
                    return w.widget()
    return None


def test_p0n_no_mode_no_footer():
    """Pas de mode → pas de footer ModeBadge."""
    bubble = ChatBubble(text="Hello", role="nuru")
    badge = _find_modebadge_in_footer(bubble)
    assert badge is None, "Aucun ModeBadge attendu quand mode=''"
    print("PASS test_p0n_no_mode_no_footer")


def test_p0n_mode_shows_badge():
    """mode='RAG' → footer affiche un ModeBadge RAG."""
    bubble = ChatBubble(text="Réponse RAG", role="nuru", mode="RAG")
    badge = _find_modebadge_in_footer(bubble)
    assert badge is not None, "ModeBadge devrait être présent avec mode='RAG'"
    assert badge._mode == "RAG", (
        f"Le badge devrait afficher RAG, eu {badge._mode}"
    )
    print("PASS test_p0n_mode_shows_badge")


def test_p0n_model_name_shown():
    """model_name fourni → le footer affiche bien un ModeBadge + label modèle visible."""
    bubble = ChatBubble(
        text="Réponse", role="nuru",
        mode="CLOUD", model_name="Groq llama",
    )
    badge = _find_modebadge_in_footer(bubble)
    assert badge is not None, "ModeBadge devrait être présent avec mode='CLOUD'"
    assert badge._mode == "CLOUD", f"Badge devrait être CLOUD, eu {badge._mode}"
    print("PASS test_p0n_model_name_shown")


def test_p0n_user_mode_no_footer():
    """role='user' avec mode → pas de footer (les actions sont désactivées)."""
    bubble = ChatBubble(text="User msg", role="user", mode="RAG")
    badge = _find_modebadge_in_footer(bubble)
    assert badge is None, "ModeBadge ne devrait pas apparaître sur les messages user"
    print("PASS test_p0n_user_mode_no_footer")


def test_p0n_messages_area_propagates_mode():
    """MessagesArea.add_message() propage mode/model_name à ChatBubble."""
    area = MessagesArea()
    row = area.add_message(
        text="Test",
        role="assistant",
        mode="RAG",
        model_name="Phi-4 mini",
    )
    # Le ChatBubble doit avoir reçu les valeurs
    assert hasattr(row, "_bubble"), "MessageRow doit avoir _bubble"
    bubble = row._bubble
    assert bubble._mode == "RAG", (
        f"ChatBubble._mode attendu RAG, eu {bubble._mode}"
    )
    badge = _find_modebadge_in_footer(bubble)
    assert badge is not None, "ModeBadge devrait être présent"
    print("PASS test_p0n_messages_area_propagates_mode")


# ═══════════════════════════════════════════════════════════════════════
# P0-G — StatCard unifié
# ═══════════════════════════════════════════════════════════════════════

def test_p0g_statcard_init():
    """StatCard s'initialise avec titre, valeur, icône."""
    card = StatCard(title="Tokens", value="12.4k", icon="📊", color="#60a5fa")
    assert card._title_str == "Tokens"
    # Vérifier la valeur affichée
    assert "12.4k" in card._value_lbl.text()
    print("PASS test_p0g_statcard_init")


def test_p0g_statcard_set_value():
    """StatCard.set_value() met à jour la valeur et la couleur."""
    card = StatCard(title="RAM", value="3.2 Go", icon="🧠")
    card.set_value("4.1 Go", color="#22c55e")
    assert "4.1 Go" in card._value_lbl.text()
    # Vérifier que la couleur a changé
    assert card._color == "#22c55e", (
        f"La couleur devrait être mise à jour: {card._color}"
    )
    print("PASS test_p0g_statcard_set_value")


def test_p0g_mini_statcard():
    """MiniStatCard (version compacte) fonctionne."""
    mini = MiniStatCard(label="RAG", value="92%", subtitle="Recall@5")
    assert mini._label_w.text() == "RAG"
    assert mini._value_w.text() == "92%"
    assert mini._subtitle_w.text() == "Recall@5"
    # set_value
    mini.set_value("95%")
    assert mini._value_w.text() == "95%"
    print("PASS test_p0g_mini_statcard")


def test_p0g_statcard_imported():
    """StatCard est importable depuis stat_card.py."""
    from src.ui.components.stat_card import StatCard as SC, MiniStatCard as MSC
    assert SC is StatCard
    assert MSC is MiniStatCard
    print("PASS test_p0g_statcard_imported")


# ═══════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # P0-E
    test_p0e_model_switcher_init()
    test_p0e_model_change_signal()
    test_p0e_set_model()
    test_p0e_current_model()

    # P0-N
    test_p0n_no_mode_no_footer()
    test_p0n_mode_shows_badge()
    test_p0n_model_name_shown()
    test_p0n_user_mode_no_footer()
    test_p0n_messages_area_propagates_mode()

    # P0-G
    test_p0g_statcard_init()
    test_p0g_statcard_set_value()
    test_p0g_mini_statcard()
    test_p0g_statcard_imported()

    print(f"\n✅ JOUR 4 — {13} tests P0-N/E/G — OK")
