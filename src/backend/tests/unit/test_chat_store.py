import json

import pytest

from memo.services.chat_store import (
    add_message,
    create_chat,
    delete_chat,
    get_chat,
    list_chats,
    list_messages,
    set_chat_title_from_question,
    update_chat,
)


def test_create_and_get_chat(in_memory_db):
    chat = create_chat(model="qwen3:4b", context_type="none")
    assert chat["id"] is not None
    assert chat["model"] == "qwen3:4b"
    assert chat["context_type"] == "none"

    fetched = get_chat(chat["id"])
    assert fetched is not None
    assert fetched["id"] == chat["id"]


def test_list_chats(in_memory_db):
    create_chat(model="a")
    create_chat(model="b")
    chats = list_chats()
    assert len(chats) == 2


def test_update_chat_title(in_memory_db):
    chat = create_chat(model="qwen3:4b")
    updated = update_chat(chat["id"], title="My Chat")
    assert updated["title"] == "My Chat"


def test_delete_chat(in_memory_db):
    chat = create_chat(model="qwen3:4b")
    assert delete_chat(chat["id"]) is True
    assert get_chat(chat["id"]) is None
    assert delete_chat(chat["id"]) is False


def test_add_and_list_messages(in_memory_db):
    chat = create_chat(model="qwen3:4b")
    add_message(chat["id"], "user", "Hello?")
    add_message(chat["id"], "assistant", "Hi!", sources=["doc.txt"])
    msgs = list_messages(chat["id"])
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["sources"] == ["doc.txt"]


def test_sources_serialized_as_list(in_memory_db):
    chat = create_chat(model="qwen3:4b")
    add_message(chat["id"], "assistant", "Answer", sources=["a.txt", "b.txt"])
    msgs = list_messages(chat["id"])
    assert isinstance(msgs[0]["sources"], list)
    assert "a.txt" in msgs[0]["sources"]


def test_set_chat_title_truncates(in_memory_db):
    chat = create_chat(model="qwen3:4b")
    long_q = "A" * 100
    set_chat_title_from_question(chat["id"], long_q)
    updated = get_chat(chat["id"])
    assert len(updated["title"]) <= 61
    assert updated["title"].endswith("…")


def test_context_paths_roundtrip(in_memory_db):
    paths = ["/a/b.txt", "/c/d.pdf"]
    chat = create_chat(model="m", context_type="files", context_paths=paths)
    fetched = get_chat(chat["id"])
    assert fetched["context_paths"] == paths
