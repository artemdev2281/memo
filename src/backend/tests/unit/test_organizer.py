import os

import numpy as np
import pytest

from memo.services.organizer import _cluster, _document_vectors, _name_cluster, _tfidf_name
from memo.services.fs import apply_organization


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeOllama:
    def __init__(self, response: str = "Название папки", fail: bool = False):
        self._response = response
        self._fail = fail

    async def chat_stream(self, model, messages, num_ctx=4096, think=None):
        if self._fail:
            raise RuntimeError("Ollama unavailable")
        yield {"message": {"content": self._response}, "done": True}


# ---------------------------------------------------------------------------
# _document_vectors
# ---------------------------------------------------------------------------

def test_document_vectors_averages_chunks(mock_chroma):
    mock_chroma.get.return_value = {
        "ids": ["a::chunk::0", "a::chunk::1"],
        "embeddings": [[1.0, 0.0], [0.0, 1.0]],
        "documents": ["chunk A", "chunk B"],
        "metadatas": [],
    }
    vectors = _document_vectors(["/some/a.txt"])
    assert "/some/a.txt" in vectors
    result = vectors["/some/a.txt"]
    assert abs(result[0] - 0.5) < 1e-6
    assert abs(result[1] - 0.5) < 1e-6


def test_document_vectors_missing_file_skipped(mock_chroma):
    mock_chroma.get.return_value = {"ids": [], "embeddings": [], "documents": [], "metadatas": []}
    vectors = _document_vectors(["/nonexistent/file.txt"])
    assert vectors == {}


def test_document_vectors_chroma_error_skipped(mock_chroma):
    mock_chroma.get.side_effect = Exception("chroma error")
    vectors = _document_vectors(["/some/file.txt"])
    assert vectors == {}


# ---------------------------------------------------------------------------
# _cluster
# ---------------------------------------------------------------------------

def test_cluster_single_file():
    vectors = {"/a.txt": [1.0, 0.0]}
    result = _cluster(vectors)
    assert result == {"/a.txt": 0}


def test_cluster_two_files():
    vectors = {"/a.txt": [1.0, 0.0], "/b.txt": [0.0, 1.0]}
    result = _cluster(vectors)
    assert set(result.keys()) == {"/a.txt", "/b.txt"}
    assert result["/a.txt"] != result["/b.txt"]


def test_cluster_two_clear_groups():
    # Group 1: near [1,0], Group 2: near [0,1]
    vecs = {
        "/a1.txt": [1.0, 0.0],
        "/a2.txt": [0.9, 0.1],
        "/b1.txt": [0.0, 1.0],
        "/b2.txt": [0.1, 0.9],
    }
    result = _cluster(vecs)
    # Both files in group A should share one label, both in B another
    assert result["/a1.txt"] == result["/a2.txt"]
    assert result["/b1.txt"] == result["/b2.txt"]
    assert result["/a1.txt"] != result["/b1.txt"]


def test_cluster_empty():
    assert _cluster({}) == {}


# ---------------------------------------------------------------------------
# _tfidf_name
# ---------------------------------------------------------------------------

def test_tfidf_name_basic():
    name = _tfidf_name(["договор аренды квартиры договор аренды"])
    assert isinstance(name, str)
    assert len(name) > 0


def test_tfidf_name_empty_chunks():
    name = _tfidf_name([])
    assert name == "Разное"


# ---------------------------------------------------------------------------
# _name_cluster
# ---------------------------------------------------------------------------

async def test_name_cluster_uses_llm():
    ollama = FakeOllama(response="Финансовые отчёты")
    name = await _name_cluster(["фрагмент документа"], ollama)
    assert name == "Финансовые отчёты"


async def test_name_cluster_falls_back_on_error():
    ollama = FakeOllama(fail=True)
    name = await _name_cluster(["договор аренды договор аренды"], ollama)
    # Should return something non-empty (TF-IDF fallback)
    assert isinstance(name, str)
    assert len(name) > 0


async def test_name_cluster_empty_chunks_fallback():
    ollama = FakeOllama(response="")
    name = await _name_cluster([], ollama)
    assert isinstance(name, str)


# ---------------------------------------------------------------------------
# apply_organization
# ---------------------------------------------------------------------------

def test_apply_organization_moves_files(tmp_path):
    f1 = tmp_path / "doc1.txt"
    f2 = tmp_path / "doc2.txt"
    f1.write_text("a")
    f2.write_text("b")

    plan = [
        {"folder_name": "Группа1", "files": [str(f1)]},
        {"folder_name": "Группа2", "files": [str(f2)]},
    ]
    result = apply_organization(str(tmp_path), plan)

    assert result["folders_created"] == 2
    assert result["files_moved"] == 2
    assert (tmp_path / "Группа1" / "doc1.txt").exists()
    assert (tmp_path / "Группа2" / "doc2.txt").exists()
    assert not f1.exists()
    assert not f2.exists()


def test_apply_organization_skips_missing_src(tmp_path):
    f1 = tmp_path / "exists.txt"
    f1.write_text("a")
    plan = [
        {"folder_name": "Группа1", "files": [str(f1), str(tmp_path / "missing.txt")]},
    ]
    result = apply_organization(str(tmp_path), plan)
    assert result["files_moved"] == 1
    assert (tmp_path / "Группа1" / "exists.txt").exists()


def test_apply_organization_rollback_on_error(tmp_path):
    f1 = tmp_path / "real.txt"
    f1.write_text("content")
    plan = [
        {"folder_name": "Группа1", "files": [str(f1)]},
        # Second cluster: file doesn't exist but folder_name triggers mkdir first,
        # then we can force an error by making the dest unwritable.
        # Instead, let's patch shutil.move to fail on the 2nd call.
    ]
    # For a simpler rollback test: use a plan that tries to move the same file twice
    # (second move fails because the file is no longer at original location).
    # But apply_organization skips missing sources, so that won't raise.
    # Instead, let's verify rollback by making dest_dir creation fail.
    import unittest.mock as mock

    call_count = [0]
    original_move = __import__("shutil").move

    def failing_move(src, dst):
        call_count[0] += 1
        if call_count[0] == 2:  # fail only on the 2nd forward call; rollback calls (3+) succeed
            raise OSError("simulated failure")
        original_move(src, dst)

    f2 = tmp_path / "real2.txt"
    f2.write_text("content2")

    plan2 = [
        {"folder_name": "GrpA", "files": [str(f1)]},
        {"folder_name": "GrpB", "files": [str(f2)]},
    ]

    with mock.patch("memo.services.fs.shutil.move", side_effect=failing_move):
        with pytest.raises(ValueError, match="Ошибка применения организации"):
            apply_organization(str(tmp_path), plan2)

    # f1 should be rolled back to original location
    assert f1.exists()


def test_apply_organization_no_change_for_same_location(tmp_path):
    # File already in target folder — skip it gracefully
    sub = tmp_path / "Группа1"
    sub.mkdir()
    f = sub / "doc.txt"
    f.write_text("x")

    plan = [{"folder_name": "Группа1", "files": [str(f)]}]
    result = apply_organization(str(tmp_path), plan)
    assert result["files_moved"] == 0
    assert f.exists()


def test_apply_organization_empty_plan(tmp_path):
    result = apply_organization(str(tmp_path), [])
    assert result == {"folders_created": 0, "files_moved": 0}


def test_apply_organization_rejects_path_traversal(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    plan = [{"folder_name": "../../evil", "files": [str(f)]}]
    with pytest.raises(ValueError, match="path traversal"):
        apply_organization(str(tmp_path), plan)
    assert f.exists()


def test_apply_organization_rejects_separator_in_folder_name(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    plan = [{"folder_name": "sub/dir", "files": [str(f)]}]
    with pytest.raises(ValueError, match="path traversal"):
        apply_organization(str(tmp_path), plan)
