import os
from datetime import datetime
from typing import AsyncGenerator

from memo.chroma import get_collection
from memo.db.models import IndexState
from memo.db.session import SessionLocal
from memo.services.document_loader import SUPPORTED, load
from memo.services.ollama_client import OllamaClient

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


def _chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if not text.strip():
        return []
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
            files.append(abs_path)
        elif os.path.isdir(abs_path):
            for root, _, names in os.walk(abs_path):
                for name in sorted(names):
                    files.append(os.path.join(root, name))
    return files


def _db_get(path: str) -> tuple[str, str] | None:
    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        return (row.file_hash, row.status) if row else None


def _db_upsert(path: str, hash_: str, status: str, error: str | None) -> None:
    with SessionLocal() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        if row:
            row.file_hash = hash_
            row.status = status
            row.error_msg = error
            row.indexed_at = datetime.utcnow()
        else:
            db.add(
                IndexState(
                    file_path=path,
                    file_hash=hash_,
                    status=status,
                    error_msg=error,
                    indexed_at=datetime.utcnow(),
                )
            )
        db.commit()


async def index_files(
    paths: list[str],
    ollama: OllamaClient,
    embed_model: str,
) -> AsyncGenerator[dict, None]:
    files = _expand_paths(paths)
    total = len(files)

    for i, path in enumerate(files):
        yield {"type": "progress", "done": i, "total": total, "file": path}

        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED:
            _db_upsert(path, "", "error", "Unsupported format")
            yield {"type": "error", "file": path, "msg": "Unsupported format"}
            continue

        try:
            doc = load(path)
        except Exception as e:
            _db_upsert(path, "", "error", str(e))
            yield {"type": "error", "file": path, "msg": str(e)}
            continue

        existing = _db_get(path)
        if existing and existing[0] == doc.file_hash and existing[1] == "indexed":
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

        collection = get_collection()
        try:
            existing_ids = collection.get(where={"file_path": path})["ids"]
            if existing_ids:
                collection.delete(ids=existing_ids)
        except Exception:
            pass

        ids = [f"{path}::chunk::{j}" for j in range(len(chunks))]
        metadatas = [{"file_path": path, "chunk_index": j} for j in range(len(chunks))]
        collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

        _db_upsert(path, doc.file_hash, "indexed", None)

        from memo.services import watcher as file_watcher

        file_watcher.watch_dir(os.path.dirname(path))

        yield {"type": "done", "file": path}

    yield {"type": "progress", "done": total, "total": total, "file": ""}
