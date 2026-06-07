import os
from datetime import datetime, timezone
from typing import AsyncGenerator

from memo.chroma import get_collection
from memo.db.models import IndexState
from memo.db.session import SessionLocal
from memo.services.document_loader import SUPPORTED, compute_hash, load
from memo.services.ollama_client import OllamaClient

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


def _chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if not text.strip():
        return []
    # Guard against a non-advancing window (infinite loop) on bad config.
    overlap = max(0, min(overlap, size - 1))
    result = []
    start = 0
    while start < len(text):
        result.append(text[start : start + size])
        start = start + size - overlap
        if start >= len(text):
            break
    return result


def _expand_paths(paths: list[str]) -> list[str]:
    files: list[str] = []
    for path in paths:
        abs_path = os.path.abspath(path)
        if os.path.isfile(abs_path):
            # Explicitly selected files are honoured as-is; an unsupported one
            # still surfaces a clear per-file "Unsupported format" error.
            files.append(abs_path)
        elif os.path.isdir(abs_path):
            # When expanding a directory, keep only supported documents. Pulling
            # in every file (images, spreadsheets, …) would mark each as an
            # "error" row, which then falsely trips the stale/incomplete warning
            # for any chat scoped to that folder.
            for root, _, names in os.walk(abs_path):
                for name in sorted(names):
                    if os.path.splitext(name)[1].lower() in SUPPORTED:
                        files.append(os.path.join(root, name))
    return files


def _db_get_baseline(path: str) -> tuple[str, str, float, int] | None:
    """(hash, status, mtime, size) — used for the cheap unchanged-file pre-skip."""
    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        return (row.file_hash, row.status, row.mtime, row.size) if row else None


def _stat(path: str) -> tuple[float, int]:
    try:
        st = os.stat(path)
        return st.st_mtime, st.st_size
    except OSError:
        return 0.0, 0


def _db_upsert(path: str, hash_: str, status: str, error: str | None) -> None:
    # Record mtime/size only for successfully indexed files — that's the
    # baseline mark_changed_stale() compares against to skip re-hashing.
    mtime, size = _stat(path) if status == "indexed" else (0.0, 0)
    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        if row:
            row.file_hash = hash_
            row.status = status
            row.error_msg = error
            row.mtime = mtime
            row.size = size
            row.indexed_at = datetime.now(timezone.utc)
        else:
            db.add(
                IndexState(
                    file_path=path,
                    file_hash=hash_,
                    status=status,
                    error_msg=error,
                    mtime=mtime,
                    size=size,
                    indexed_at=datetime.now(timezone.utc),
                )
            )
        db.commit()


def mark_changed_stale(paths: list[str]) -> None:
    """Re-hash already-'indexed' files and flip any whose content changed to
    'stale'.

    Content hashing is the source of truth for staleness. The filesystem
    watcher is only a best-effort optimisation: it can miss events (e.g.
    ReadDirectoryChangesW buffer overflow under rapid edits) or fire while the
    app is closed. Calling this on demand — before answering a chat and on
    startup — guarantees a changed file is detected on *every* edit, not just
    the first one the watcher happened to catch.
    """
    with SessionLocal() as db:
        for path in paths:
            row = db.query(IndexState).filter(IndexState.file_path == path).first()
            if row is None or row.status != "indexed":
                continue
            try:
                st = os.stat(path)
            except OSError:
                # Unreadable / temporarily missing (e.g. disconnected drive):
                # leave the existing index untouched rather than destroy it.
                continue
            # Cheap pre-filter: identical mtime+size → assume unchanged, no hash.
            if st.st_mtime == row.mtime and st.st_size == row.size:
                continue
            try:
                current = compute_hash(path)
            except OSError:
                continue
            if current != row.file_hash:
                row.status = "stale"
            else:
                # Content identical, only metadata touched → refresh the
                # baseline so this file isn't re-hashed on every future message.
                row.mtime = st.st_mtime
                row.size = st.st_size
        db.commit()


def reconcile_all() -> None:
    """Flip every indexed file whose content changed to 'stale'. Runs at
    startup to catch edits made while the watcher was not running."""
    with SessionLocal() as db:
        paths = [r.file_path for r in db.query(IndexState).filter(IndexState.status == "indexed").all()]
    mark_changed_stale(paths)


async def index_files(
    paths: list[str],
    ollama: OllamaClient,
    embed_model: str,
) -> AsyncGenerator[dict, None]:
    files = _expand_paths(paths)
    total = len(files)
    collection = get_collection()

    for i, path in enumerate(files):
        yield {"type": "progress", "done": i, "total": total, "file": path}

        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED:
            _db_upsert(path, "", "error", "Unsupported format")
            yield {"type": "error", "file": path, "msg": "Unsupported format"}
            continue

        # Cheap pre-skip: an already-indexed file whose mtime+size match the
        # recorded baseline is unchanged → skip without reading/hashing it.
        baseline = _db_get_baseline(path)
        if baseline and baseline[1] == "indexed":
            mtime, size = _stat(path)
            if mtime == baseline[2] and size == baseline[3]:
                yield {"type": "skip", "file": path}
                continue

        try:
            doc = load(path)
        except Exception as e:
            _db_upsert(path, "", "error", str(e))
            yield {"type": "error", "file": path, "msg": str(e)}
            continue

        # Authoritative skip: content hash unchanged (stat may have shifted with
        # identical bytes).
        if baseline and baseline[0] == doc.file_hash and baseline[1] == "indexed":
            yield {"type": "skip", "file": path}
            continue

        chunks = _chunks(doc.text)
        if not chunks:
            _db_upsert(path, doc.file_hash, "error", "Empty document")
            yield {"type": "error", "file": path, "msg": "Empty document"}
            continue

        try:
            embeddings = await ollama.embed(chunks, embed_model)
        except Exception as e:
            _db_upsert(path, doc.file_hash, "error", f"Embedding failed: {e}")
            yield {"type": "error", "file": path, "msg": f"Embedding failed: {e}"}
            continue

        delete_failed = False
        try:
            existing_ids = collection.get(where={"file_path": path})["ids"]
            if existing_ids:
                collection.delete(ids=existing_ids)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Chroma delete failed for %s: %s", path, e)
            delete_failed = True

        if delete_failed:
            _db_upsert(path, doc.file_hash, "error", "Chroma delete failed; skipping re-index")
            yield {"type": "error", "file": path, "msg": "Chroma delete failed; skipping re-index"}
            continue

        ids = [f"{path}::chunk::{j}" for j in range(len(chunks))]
        file_name = os.path.basename(path)
        metadatas = [
            {"file_path": path, "file_name": file_name, "file_hash": doc.file_hash, "chunk_index": j}
            for j in range(len(chunks))
        ]
        try:
            collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
        except Exception as e:
            _db_upsert(path, doc.file_hash, "error", f"Chroma add failed: {e}")
            yield {"type": "error", "file": path, "msg": f"Chroma add failed: {e}"}
            continue

        _db_upsert(path, doc.file_hash, "indexed", None)

        from memo.services import watcher as file_watcher

        file_watcher.watch_dir(os.path.dirname(path))

        yield {"type": "done", "file": path}

    yield {"type": "progress", "done": total, "total": total, "file": ""}
