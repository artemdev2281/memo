from datetime import datetime

import pytest

from memo.db.models import IndexState
from memo.services.fs import get_tree


def test_get_tree_empty_dir(tmp_path, in_memory_db):
    result = get_tree(str(tmp_path))
    assert result["type"] == "dir"
    assert result["path"] == str(tmp_path)
    assert result["children"] == []


def test_get_tree_with_files(tmp_path, in_memory_db):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.md").write_text("b")
    result = get_tree(str(tmp_path))
    names = [c["name"] for c in result["children"]]
    assert "a.txt" in names
    assert "b.md" in names


def test_get_tree_status_from_db(tmp_path, in_memory_db):
    f = tmp_path / "doc.txt"
    f.write_text("content")
    with in_memory_db() as db:
        db.add(
            IndexState(
                file_path=str(f),
                file_hash="abc",
                status="indexed",
                indexed_at=datetime.utcnow(),
            )
        )
        db.commit()

    result = get_tree(str(tmp_path))
    file_node = next(c for c in result["children"] if c["name"] == "doc.txt")
    assert file_node["status"] == "indexed"


def test_get_tree_hides_dotfiles(tmp_path, in_memory_db):
    (tmp_path / ".hidden").write_text("hidden")
    (tmp_path / "visible.txt").write_text("visible")
    result = get_tree(str(tmp_path))
    names = [c["name"] for c in result["children"]]
    assert ".hidden" not in names
    assert "visible.txt" in names


def test_get_tree_depth_limit(tmp_path, in_memory_db):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_text("deep")
    result = get_tree(str(tmp_path), depth=1)
    sub_node = next(c for c in result["children"] if c["name"] == "sub")
    assert sub_node["children"] == []
