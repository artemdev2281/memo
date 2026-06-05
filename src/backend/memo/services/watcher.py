import os
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from memo.db.models import IndexState
from memo.db.session import SessionLocal

_observer = Observer()
_watched_dirs: set[str] = set()
_lock = threading.Lock()


class _Handler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            _mark_stale_or_create(os.path.abspath(event.src_path))

    def on_modified(self, event):
        if not event.is_directory:
            _mark_stale(os.path.abspath(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            _remove(os.path.abspath(event.src_path))
            _mark_stale_or_create(os.path.abspath(event.dest_path))

    def on_deleted(self, event):
        if not event.is_directory:
            _remove(os.path.abspath(event.src_path))


_handler = _Handler()


def _mark_stale(path: str) -> None:
    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        if row and row.status == "indexed":
            row.status = "stale"
            db.commit()


def _mark_stale_or_create(path: str) -> None:
    from datetime import datetime

    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        if row:
            row.status = "stale"
        else:
            db.add(IndexState(file_path=path, file_hash="", status="stale", indexed_at=datetime.utcnow()))
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
    with _lock:
        if abs_dir not in _watched_dirs:
            _observer.schedule(_handler, abs_dir, recursive=True)
            _watched_dirs.add(abs_dir)


def start() -> None:
    if not _observer.is_alive():
        _observer.start()


def stop() -> None:
    if _observer.is_alive():
        _observer.stop()
        _observer.join()
