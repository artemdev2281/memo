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


def test_mark_stale_flips_error_state(in_memory_db):
    # A file that previously errored but is edited again must be re-flagged.
    with in_memory_db() as db:
        db.add(IndexState(file_path="/e.txt", file_hash="x", status="error",
                          indexed_at=datetime.utcnow()))
        db.commit()

    _mark_stale("/e.txt")

    with in_memory_db() as db:
        assert db.query(IndexState).filter_by(file_path="/e.txt").first().status == "stale"


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


def test_on_created_marks_stale(in_memory_db, tmp_path):
    from memo.services.watcher import _Handler
    import os
    import types

    handler = _Handler()
    target = str(tmp_path / "created.txt")
    event = types.SimpleNamespace(is_directory=False, src_path=target)
    handler.on_created(event)

    expected_path = os.path.abspath(target)
    with in_memory_db() as db:
        row = db.query(IndexState).filter_by(file_path=expected_path).first()
        assert row is not None
        assert row.status == "stale"


def test_on_created_ignores_unsupported_extension(in_memory_db, tmp_path):
    # Recursive watch on a folder sees every file; only indexable formats
    # should land in index_state — not temp/lock/binary files.
    from memo.services.watcher import _Handler
    import os
    import types

    handler = _Handler()
    target = str(tmp_path / "scratch.tmp")
    handler.on_created(types.SimpleNamespace(is_directory=False, src_path=target))

    with in_memory_db() as db:
        row = db.query(IndexState).filter_by(file_path=os.path.abspath(target)).first()
        assert row is None


def test_on_created_ignores_office_lock_file(in_memory_db, tmp_path):
    # Word writes ~$doc.docx lock files that share the .docx extension.
    from memo.services.watcher import _Handler
    import os
    import types

    handler = _Handler()
    target = str(tmp_path / "~$report.docx")
    handler.on_created(types.SimpleNamespace(is_directory=False, src_path=target))

    with in_memory_db() as db:
        assert db.query(IndexState).filter_by(file_path=os.path.abspath(target)).first() is None


def test_watch_dir_skips_missing_directory():
    # A previously indexed file's folder may be gone on restart; scheduling a
    # watch on it must not raise (would otherwise crash startup re-registration).
    from memo.services import watcher

    before = set(watcher._watched_dirs)
    watcher.watch_dir("/no/such/directory/here")
    assert watcher._watched_dirs == before
