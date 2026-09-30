"""
Tests for core.chat_manager.ChatManager -- the SQLite-backed chat store.
Uses a temp DB file per test (via the `chat_manager` fixture) so tests
never touch the real chats.db.
"""
import os
import pytest

from core.chat_manager import ChatManager


@pytest.fixture
def chat_manager(tmp_path):
    cm = ChatManager()
    cm.db_path = str(tmp_path / "test_chats.db")
    cm._ensure_tables()
    return cm


def test_create_and_list_chat(chat_manager):
    cid = chat_manager.create_chat("hello there")
    chats = chat_manager.get_all_chats()
    assert any(c["id"] == cid for c in chats)


def test_add_and_get_messages(chat_manager):
    cid = chat_manager.create_chat("hi")
    chat_manager.add_message(cid, "user", "hi")
    chat_manager.add_message(cid, "assistant", "hello Sir")

    msgs = chat_manager.get_messages_for_llm(cid)
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "content": "hi"}
    assert msgs[1] == {"role": "assistant", "content": "hello Sir"}


def test_auto_rename_only_applies_to_default_title(chat_manager):
    cid = chat_manager.create_chat()  # default "New Chat"
    chat_manager.auto_rename_if_needed(cid, "what's the weather like today")
    assert chat_manager.get_chat_title(cid).startswith("what's the weather")

    # A chat that's already been explicitly named should NOT get overwritten
    chat_manager.rename_chat(cid, "My custom title")
    chat_manager.auto_rename_if_needed(cid, "something else entirely")
    assert chat_manager.get_chat_title(cid) == "My custom title"


def test_rename_chat(chat_manager):
    cid = chat_manager.create_chat("hi")
    chat_manager.rename_chat(cid, "Renamed")
    assert chat_manager.get_chat_title(cid) == "Renamed"


def test_delete_chat_removes_it_and_its_messages(chat_manager):
    # This is exactly the call path that used to crash in
    # ui/chat_manager_ui.py's delete_chat() (see test_chat_manager_ui.py)
    # -- the underlying ChatManager.delete_chat() call itself.
    cid = chat_manager.create_chat("to be deleted")
    chat_manager.add_message(cid, "user", "hi")

    chat_manager.delete_chat(cid)

    remaining = chat_manager.get_all_chats()
    assert not any(c["id"] == cid for c in remaining)
    assert chat_manager.get_messages_for_llm(cid) == []


def test_db_path_is_anchored_to_repo_root_not_cwd():
    import core.chat_manager as cm_mod
    from config.config import BASE_DIR
    # Regression check: this used to be a bare relative "chats.db", which
    # meant launching desktop.py from a different working directory would
    # silently create/read a different, empty database.
    assert cm_mod.DB_FILE == os.path.join(BASE_DIR, "chats.db")
