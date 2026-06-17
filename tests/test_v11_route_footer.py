"""Test V11.1 P0-N — Routeur mode dans le footer de la bulle.

Couvre :
- Test 1 : bulle assistant avec mode 'CLOUD' et model_name 'Groq llama'
  → footer visible avec 'Groq llama' + ModeBadge(CLOUD)
- Test 2 : bulle assistant sans mode ni model_name → pas de footer
- Test 3 : bulle user avec mode défini → pas de footer (user n'affiche pas)
- Test 4 : mode='RAG' → ModeBadge avec texte RAG
- Test 5 : MessagesArea.add_message() avec mode → footer apparaît
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QCoreApplication

_app = QCoreApplication.instance() or QApplication(sys.argv)

# Imports normaux (pas d'import dynamique)
from src.ui.components.nuru_widgets import ModeBadge
from src.ui.components.chat_bubble import ChatBubble, MessageRow


def _find_mode_badge(widget: QWidget) -> ModeBadge | None:
    """Cherche un ModeBadge dans les enfants du widget."""
    for child in widget.findChildren(ModeBadge):
        return child
    return None


def _find_model_label(widget: QWidget) -> QWidget | None:
    """Cherche un QLabel avec le nom du modèle (pas BubbleText, ModeBadge ni AvatarWidget)."""
    for child in widget.findChildren(QWidget):
        if (
            isinstance(child, ModeBadge)
            or not hasattr(child, "text")
            or not callable(child.text)
            or child.objectName() == "BubbleText"
        ):
            continue
        txt = child.text()
        if (
            txt
            and len(txt) > 3  # plus long qu'un avatar 'U'/'N'
            and txt not in ("LOCAL", "RAG", "CLOUD", "VERIFY", "PLAN")
        ):
            return child
    return None


# ── Tests ──


def test_assistant_bubble_shows_mode_footer():
    """Bulle assistant avec mode CLOUD → footer visible."""
    row = MessageRow(
        text="Réponse cloud",
        role="assistant",
        mode="CLOUD",
        model_name="Groq llama",
    )
    badge = _find_mode_badge(row)
    assert badge is not None, (
        "ModeBadge devrait être présent dans la bulle CLOUD"
    )
    assert badge._mode == "CLOUD", f"attendu CLOUD, eu {badge._mode}"
    print("PASS test_assistant_bubble_shows_mode_footer")


def test_assistant_bubble_no_mode_no_footer():
    """Bulle assistant sans mode ni model_name → pas de footer."""
    row = MessageRow(text="Réponse", role="assistant")
    badge = _find_mode_badge(row)
    assert badge is None, "Aucun ModeBadge ne devrait être présent"
    print("PASS test_assistant_bubble_no_mode_no_footer")


def test_user_bubble_no_footer_even_with_mode():
    """Bulle user avec mode défini → pas de footer (privacy UX)."""
    row = MessageRow(
        text="Ma question",
        role="user",
        mode="CLOUD",
        model_name="Groq llama",
    )
    badge = _find_mode_badge(row)
    assert badge is None, "ModeBadge ne devrait pas apparaître sur bulle user"
    print("PASS test_user_bubble_no_footer_even_with_mode")


def test_mode_rag_badge():
    """Mode RAG → badge affiche RAG."""
    row = MessageRow(
        text="Réponse RAG",
        role="assistant",
        mode="RAG",
    )
    badge = _find_mode_badge(row)
    assert badge is not None, "ModeBadge devrait être présent en mode RAG"
    assert badge._mode == "RAG", f"attendu RAG, eu {badge._mode}"
    print("PASS test_mode_rag_badge")


def test_messages_area_propagates_mode():
    """MessagesArea.add_message() avec mode → footer visible."""
    from src.ui.components.console_page import MessagesArea

    area = MessagesArea()
    row = area.add_message(
        text="Réponse avec mode",
        role="assistant",
        mode="VERIFY",
        model_name="Phi-4-mini",
    )
    badge = _find_mode_badge(row)
    assert badge is not None, (
        "ModeBadge présent après add_message avec mode"
    )
    assert badge._mode == "VERIFY", f"attendu VERIFY, eu {badge._mode}"

    model_label = _find_model_label(row)
    assert model_label is not None, (
        "Label modèle présent après add_message avec model_name"
    )
    assert "Phi-4-mini" in model_label.text(), (
        f"attendu 'Phi-4-mini' dans le label, eu '{model_label.text()}'"
    )
    print("PASS test_messages_area_propagates_mode")


# ── Exécution manuelle ──
if __name__ == "__main__":
    tests = [
        test_assistant_bubble_shows_mode_footer,
        test_assistant_bubble_no_mode_no_footer,
        test_user_bubble_no_footer_even_with_mode,
        test_mode_rag_badge,
        test_messages_area_propagates_mode,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
    print(f"\n{'─' * 40}")
    print(f"✅ {passed}/{passed + failed} tests P0-N passent")
    sys.exit(0 if failed == 0 else 1)