from datetime import datetime
from unittest.mock import MagicMock

import pytest

from memo.db.models import IndexState
from memo.services.watcher import _mark_stale, _mark_stale_or_create, _remove


def test_mark_stale_changes_status(in_memory_db):
    with in_memory_db() as db:
        db.add(
            IndexState(
                file_path="/test/file.txt",
                file_hash="abc",
                status="indexed",
                indexed_at=datetime.utcnow(),
            )
        )
        db.commit()

    _mark_stale("/test/file.txt")

    with in_memory_db() as db:
        row = db.query(IndexState).filter_by(file_path="/test/file.txt").first()
        assert row is not None
        assert row.status == "stale"


def test_mark_stale_ignores_missing(in_memory_db):
    # Should not raise even if file not in DB
    _mark_stale("/nonexistent/file.txt")


def test_remove_deletes_row(in_memory_db, monkeypatch):
    monkeypatch.setattr("memo.chroma.get_collection", lambda: MagicMock())

    with in_memory_db() as db:
        db.add(
            IndexState(
                file_path="/test/file.txt",
                file_hash="abc",
                status="indexed",
                indexed_at=datetime.utcnow(),
            )
        )
        db.commit()

    _remove("/test/file.txt")

    with in_memory_db() as db:
        row = db.query(IndexState).filter_by(file_path="/test/file.txt").first()
        assert row is None


def test_remove_ignores_missing(in_memory_db, monkeypatch):
    monkeypatch.setattr("memo.chroma.get_collection", lambda: MagicMock())
    _remove("/nonexistent/file.txt")


def test_mark_stale_or_create_existing(in_memory_db):
    with in_memory_db() as db:
        db.add(IndexState(file_path="/a.txt", file_hash="abc", status="indexed", indexed_at=datetime.utcnow()))
        db.commit()

    _mark_stale_or_create("/a.txt")

    with in_memory_db() as db:
        row = db.query(IndexState).filter_by(file_path="/a.txt").first()
        assert row.status == "stale"


def test_mark_stale_or_create_new(in_memory_db):
    _mark_stale_or_create("/new/file.txt")

    with in_memory_db() as db:
        row = db.query(IndexState).filter_by(file_path="/new/file.txt").first()
        assert row is not None
        assert row.status == "stale"
