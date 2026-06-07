from __future__ import annotations

import collections
import os
import re
from typing import AsyncGenerator

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from memo.chroma import get_collection
from memo.services.document_loader import SUPPORTED
from memo.services.indexer import _expand_paths, index_files
from memo.services.ollama_client import OllamaClient
from memo.settings import settings


def _collect_files(folder: str, include_subfolders: bool) -> list[str]:
    abs_folder = os.path.abspath(folder)
    if include_subfolders:
        return _expand_paths([abs_folder])
    files: list[str] = []
    try:
        for entry in sorted(os.scandir(abs_folder), key=lambda e: e.name):
            if entry.is_file() and not entry.name.startswith("."):
                files.append(entry.path)
    except PermissionError:
        pass
    return files


def _document_vectors(file_paths: list[str]) -> dict[str, list[float]]:
    """Average chunk embeddings from Chroma to get one vector per document."""
    collection = get_collection()
    vectors: dict[str, list[float]] = {}
    for path in file_paths:
        try:
            result = collection.get(
                where={"file_path": path},
                include=["embeddings"],
            )
            embeddings = result.get("embeddings")
            if embeddings is not None and len(embeddings) > 0:
                arr = np.array(embeddings, dtype=float)
                vectors[path] = arr.mean(axis=0).tolist()
        except Exception:
            pass
    return vectors


def _cluster(vectors: dict[str, list[float]]) -> dict[str, int]:
    """Return {path: cluster_label}. Best k chosen by silhouette score."""
    if not vectors:
        return {}
    paths = list(vectors.keys())
    n = len(paths)
    if n == 1:
        return {paths[0]: 0}
    if n == 2:
        return {paths[0]: 0, paths[1]: 1}

    X = np.array([vectors[p] for p in paths], dtype=float)
    best_k, best_score = 2, -1.0
    max_k = min(8, n - 1)
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X)
        try:
            score = float(silhouette_score(X, labels))
        except Exception:
            score = -1.0
        if score > best_score:
            best_score, best_k = score, k

    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = km.fit_predict(X)
    return {paths[i]: int(labels[i]) for i in range(n)}


_STOPWORDS = frozenset({
    "это", "как", "для", "что", "при", "его", "она", "они", "или", "не", "на",
    "в", "с", "и", "по", "из", "от", "до", "за", "об", "the", "and", "for",
    "that", "this", "with", "are", "was", "were", "has", "have", "но", "а",
    "же", "бы", "то", "так", "уже", "ещё", "все", "был", "быть",
})


def _tfidf_name(chunks: list[str]) -> str:
    text = " ".join(chunks[:3]).lower()
    words = re.findall(r"\b[а-яёa-z]{3,}\b", text)
    words = [w for w in words if w not in _STOPWORDS]
    counter = collections.Counter(words)
    top = [w for w, _ in counter.most_common(3)]
    return " ".join(top).capitalize() if top else "Разное"


async def _name_cluster(repr_chunks: list[str], ollama: OllamaClient) -> str:
    """Generate short folder name via LLM; fall back to TF-IDF on error."""
    try:
        prompt = (
            "Ниже представлены фрагменты документов из одной тематической группы. "
            "Придумай короткое название папки (2–4 слова) на русском языке, отражающее тему. "
            "Отвечай только названием без кавычек и пояснений.\n\n"
            + "\n\n---\n\n".join(repr_chunks[:3])
        )
        messages = [
            {
                "role": "system",
                "content": "Ты — помощник по организации файлов. Отвечай только кратким названием папки.",
            },
            {"role": "user", "content": prompt},
        ]
        parts: list[str] = []
        async for chunk in ollama.chat_stream(
            settings.name_model, messages, num_ctx=2048, think=False
        ):
            msg = chunk.get("message", {}) or {}
            content = msg.get("content") or ""
            if content:
                parts.append(content)
            if chunk.get("done"):
                break
        name = "".join(parts).strip().splitlines()[0].strip() if parts else ""
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name)[:50].strip()
        if name:
            return name
    except Exception:
        pass
    return _tfidf_name(repr_chunks)


async def analyze(
    folder: str,
    include_subfolders: bool,
    ollama: OllamaClient,
    embed_model: str,
    paths: list[str] | None = None,
) -> dict:
    """
    Analyze folder contents and return an organize preview.
    Returns one of:
      {"empty": True}
      {"clusters": [...], "misc": [...], "single_cluster": bool}
    """
    abs_folder = os.path.abspath(folder)
    if paths is not None:
        all_files = [os.path.abspath(p) for p in paths]
    else:
        all_files = _collect_files(abs_folder, include_subfolders)
    supported = [p for p in all_files if os.path.splitext(p)[1].lower() in SUPPORTED]

    if not supported:
        return {"empty": True}

    # Index files that have no vectors in ChromaDB (source of truth for clustering).
    # SQLite status alone is insufficient — paths may have changed after a previous
    # organize+apply cycle without ChromaDB being updated.
    vectors = _document_vectors(supported)
    needs_index = [p for p in supported if p not in vectors]

    if needs_index:
        async for _ in index_files(needs_index, ollama, embed_model):
            pass
        vectors = _document_vectors(supported)

    misc_paths = [p for p in supported if p not in vectors]
    clusterable = [p for p in supported if p in vectors]

    if not clusterable:
        misc_items = [{"path": p, "name": os.path.basename(p)} for p in supported]
        return {"clusters": [], "misc": misc_items, "single_cluster": False}

    labels = _cluster({p: vectors[p] for p in clusterable})

    cluster_map: dict[int, list[str]] = {}
    for path, label in labels.items():
        cluster_map.setdefault(label, []).append(path)

    single_cluster = len(cluster_map) == 1

    # Fetch representative text chunks for naming
    collection = get_collection()
    cluster_list: list[dict] = []
    for label, cpaths in sorted(cluster_map.items()):
        repr_chunks: list[str] = []
        for p in cpaths[:2]:
            try:
                result = collection.get(where={"file_path": p}, include=["documents"])
                docs = result.get("documents") or []
                if docs:
                    repr_chunks.append(docs[0])
            except Exception:
                pass
        name = await _name_cluster(repr_chunks, ollama)
        cluster_list.append(
            {
                "id": label,
                "name": name,
                "files": [{"path": p, "name": os.path.basename(p)} for p in cpaths],
            }
        )

    misc_items = [{"path": p, "name": os.path.basename(p)} for p in misc_paths]

    return {
        "clusters": cluster_list,
        "misc": misc_items,
        "single_cluster": single_cluster,
    }
