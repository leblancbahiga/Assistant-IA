"""Test V11.1 P0-O + P0-M — FactChecker status badge + citations inline."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication

# Application Qt partagée pour tous les tests
app = QApplication.instance() or QApplication(sys.argv)

from src.ui.components.chat_bubble import ChatBubble, MessageRow


def test_fact_status_none_no_badge():
    """fact_status=None → aucun badge FactChecker créé."""
    b = ChatBubble(text="Hello", role="assistant", fact_status=None)
    assert b._fact_status is None
    assert b._fact_badge is None


def test_fact_status_verified_badge():
    """fact_status='verified' → badge vert présent."""
    b = ChatBubble(text="Verified", role="assistant", fact_status="verified")
    assert b._fact_status == "verified"
    assert b._fact_badge is not None
    text = b._fact_badge.text()
    assert "Vérifié" in text


def test_fact_status_issues_badge():
    """fact_status='issues' → badge orange présent."""
    b = ChatBubble(text="Issues", role="assistant", fact_status="issues")
    assert b._fact_status == "issues"
    assert b._fact_badge is not None
    text = b._fact_badge.text()
    assert "Problèmes" in text


def test_fact_status_error_badge():
    """fact_status='error' → badge rouge présent."""
    b = ChatBubble(text="Error", role="assistant", fact_status="error")
    assert b._fact_status == "error"
    assert b._fact_badge is not None
    text = b._fact_badge.text()
    assert "Erreur" in text


def test_fact_status_user_ignored():
    """fact_status ignoré pour les bulles utilisateur."""
    b = ChatBubble(text="User msg", role="user", fact_status="verified")
    assert b._fact_status == "verified"
    assert b._fact_badge is None  # pas de badge pour user


def test_citation_linkify_single():
    """[1] dans le texte → lien cliquable."""
    html = ChatBubble._linkify_citations("voir [1]")
    assert 'href="citation:1"' in html
    assert ">[1]<" in html


def test_citation_linkify_multiple():
    """[1] et [2] → deux liens distincts."""
    html = ChatBubble._linkify_citations("selon [1] et [2]")
    assert html.count('href="citation:') == 2


def test_citation_linkify_no_number():
    """[abc] ne doit PAS être lié."""
    html = ChatBubble._linkify_citations("tag [abc]")
    assert 'href="citation:' not in html


def test_markdown_with_citations():
    """_markdown_to_html inclut les liens [N]."""
    html = ChatBubble._markdown_to_html("**important** [1]")
    assert "<strong>important</strong>" in html
    assert 'href="citation:1"' in html


def test_message_row_passes_fact_status():
    """MessageRow propage fact_status à ChatBubble."""
    row = MessageRow(text="Check", role="assistant",
                     fact_status="verified")
    assert row._fact_status == "verified"
    assert row._bubble._fact_status == "verified"
    assert row._bubble._fact_badge is not None


def test_on_link_activated_citation():
    """_on_link_activated 'citation:1' → émet citation_clicked."""
    b = ChatBubble(text="test", role="assistant")
    received = []
    b.citation_clicked.connect(lambda path, page: received.append((path, page)))
    b._on_link_activated("citation:3")
    assert len(received) == 1
    assert received[0] == ("[3]", 0)


if __name__ == "__main__":
    # Exécution manuelle simple
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    
    tests = [
        test_fact_status_none_no_badge,
        test_fact_status_verified_badge,
        test_fact_status_issues_badge,
        test_fact_status_error_badge,
        test_fact_status_user_ignored,
        test_citation_linkify_single,
        test_citation_linkify_multiple,
        test_citation_linkify_no_number,
        test_markdown_with_citations,
        test_message_row_passes_fact_status,
        test_on_link_activated_citation,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1
    
    print(f"\n{'─' * 40}")
    print(f"✅ {passed}/{passed+failed} tests P0-O+P0-M passent")
    sys.exit(0 if failed == 0 else 1)
