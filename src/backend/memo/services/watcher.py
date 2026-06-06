import os
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from memo.db.models import IndexState
from memo.db.session import SessionLocal
from memo.services.document_loader import SUPPORTED

_observer = Observer()
_watched_dirs: set[str] = set()
_lock = threading.Lock()


def _should_track(path: str) -> bool:
    name = os.path.basename(path)
    # Skip editor/OS scratch files (Office locks ~$x.docx, dotfile temps) that
    # share a supported extension but aren't real documents.
    if name.startswith("~$") or name.startswith("."):
        return False
    return os.path.splitext(path)[1].lower() in SUPPORTED


class _Handler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and _should_track(event.src_path):
            _mark_stale_or_create(os.path.abspath(event.src_path))

    def on_modified(self, event):
        if not event.is_directory and _should_track(event.src_path):
            _mark_stale(os.path.abspath(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            _remove(os.path.abspath(event.src_path))
            if _should_track(event.dest_path):
                _mark_stale_or_create(os.path.abspath(event.dest_path))

    def on_deleted(self, event):
        if not event.is_directory:
            _remove(os.path.abspath(event.src_path))


_handler = _Handler()


def _mark_stale(path: str) -> None:
    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        # Flip from any settled state (indexed or error) — not just "indexed" —
        # so a file re-edited after a re-index, or fixed after an error, is
        # always re-flagged for re-indexing.
        if row and row.status != "stale":
            row.status = "stale"
            db.commit()


def _mark_stale_or_create(path: str) -> None:
    from datetime import datetime, timezone

    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        if row:
            row.status = "stale"
        else:
            db.add(IndexState(file_path=path, file_hash="", status="stale", indexed_at=datetime.now(timezone.utc)))
        db.commit()


def _remove(path: str) -> None:
    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        if row:
            db.delete(row)
            db.commit()
    try:
        from memo.chroma import get_collection

        get_collection().delete(where={"file_path": path})
    except Exception:
        pass


def watch_dir(directory: str) -> None:
    abs_dir = os.path.abspath(directory)
    # A previously indexed file's directory may be gone (deleted, moved, or on a
    # disconnected drive). Scheduling a watch on it raises OSError, so skip it
    # rather than crash startup re-registration.
    if not os.path.isdir(abs_dir):
        return
    with _lock:
        if abs_dir not in _watched_dirs:
            try:
                _observer.schedule(_handler, abs_dir, recursive=True)
                _watched_dirs.add(abs_dir)
            except OSError:
                pass


def start() -> None:
    if not _observer.is_alive():
        _observer.start()


def stop() -> None:
    if _observer.is_alive():
        _observer.stop()
        _observer.join()
