"""Tests unitaires pour SessionStore."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.session.store import SessionStore, Session


@pytest.fixture
def store():
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    yield SessionStore(db_path=db.name)
    Path(db.name).unlink(missing_ok=True)


class TestSessionStore:

    def test_create_and_get(self, store):
        store.create_session("test-1", title="Test")
        s = store.get_or_create("test-1")
        assert s.id == "test-1"
        assert s.title == "Test"
        assert len(s.messages) == 0

    def test_get_or_create_new(self, store):
        s = store.get_or_create("new-session", title="Nouveau")
        assert s.id == "new-session"
        assert len(s.messages) == 0

    def test_add_message(self, store):
        store.add_message("s1", "user", "Bonjour")
        store.add_message("s1", "assistant", "Salut")
        s = store.get_or_create("s1")
        assert len(s.messages) == 2
        assert s.messages[0].role == "user"
        assert s.messages[0].content == "Bonjour"
        assert s.messages[1].role == "assistant"

    def test_build_context_empty(self, store):
        ctx = store.build_context("empty-session")
        assert ctx == ""

    def test_build_context_single_message(self, store):
        store.add_message("s2", "user", "Bonjour")
        ctx = store.build_context("s2")
        assert ctx == ""

    def test_build_context_two_messages(self, store):
        store.add_message("s3", "user", "Quel temps fait-il ?")
        store.add_message("s3", "assistant", "Il fait beau.")
        ctx = store.build_context("s3")
        assert "Quel temps fait-il" in ctx
        assert "Il fait beau" in ctx
        assert "Historique de la conversation" in ctx

    def test_build_context_max_messages(self, store):
        for i in range(10):
            store.add_message("s4", "user", f"Q{i}")
            store.add_message("s4", "assistant", f"R{i}")
        ctx = store.build_context("s4", max_messages=4)
        # Doit contenir seulement les 4 derniers messages
        assert "Q9" in ctx
        assert "R9" in ctx
        assert "Q0" not in ctx

    def test_clear_session(self, store):
        store.add_message("s5", "user", "Test")
        store.clear_session("s5")
        s = store.get_or_create("s5")
        assert len(s.messages) == 0

    def test_delete_session(self, store):
        store.add_message("s6", "user", "A")
        store.delete_session("s6")
        # La session est recréée vide via get_or_create
        s = store.get_or_create("s6")
        assert len(s.messages) == 0

    def test_list_sessions(self, store):
        store.add_message("a", "user", "msg1")
        store.add_message("b", "user", "msg1")
        store.add_message("b", "user", "msg2")
        lst = store.list_sessions()
        # Au moins 2 sessions
        ids = {s["id"] for s in lst}
        assert "a" in ids
        assert "b" in ids

    def test_update_title(self, store):
        store.create_session("s7")
        store.update_title("s7", "Super titre")
        s = store.get_or_create("s7")
        assert s.title == "Super titre"

    def test_list_sessions_order(self, store):
        store.add_message("old", "user", "ancien")
        import time
        time.sleep(0.01)
        store.add_message("new", "user", "nouveau")
        lst = store.list_sessions(limit=5)
        # La plus récente en premier
        assert lst[0]["id"] == "new"
