from __future__ import annotations

import os

import chromadb

from memo.settings import settings

_client: chromadb.PersistentClient | None = None


def get_collection() -> chromadb.Collection:
    global _client
    if _client is None:
        chroma_path = os.path.join(os.path.abspath(settings.data_dir), "chroma")
        os.makedirs(chroma_path, exist_ok=True)
        _client = chromadb.PersistentClient(path=chroma_path)
    return _client.get_or_create_collection(
        "documents",
        metadata={"hnsw:space": "cosine"},
    )
