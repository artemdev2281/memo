from __future__ import annotations

import os
from typing import AsyncGenerator

from memo.chroma import get_collection
from memo.services.indexer import _expand_paths
from memo.services.ollama_client import OllamaClient

_SYSTEM_PROMPT = (
    "Ты — AI-ассистент, который отвечает на вопросы исключительно на основе предоставленных фрагментов документов. "
    "Если ответ не содержится в документах, скажи об этом прямо. "
    "Отвечай на том языке, на котором задан вопрос."
)


def _context_filter(paths: list[str]) -> dict | None:
    expanded = _expand_paths(paths)
    if not expanded:
        return None
    if len(expanded) == 1:
        return {"file_path": expanded[0]}
    return {"file_path": {"$in": expanded}}


def retrieve(
    question: str,
    context_paths: list[str],
    question_embedding: list[float],
    k: int = 5,
) -> tuple[list[str], list[dict]]:
    """Return (texts, metadatas) of top-k relevant chunks."""
    collection = get_collection()
    where = _context_filter(context_paths) if context_paths else None
    query_kwargs: dict = {
        "query_embeddings": [question_embedding],
        "n_results": k,
        "include": ["documents", "metadatas"],
    }
    if where:
        query_kwargs["where"] = where
    try:
        results = collection.query(**query_kwargs)
    except Exception:
        return [], []

    docs = results.get("documents", [[]])[0] or []
    metas = results.get("metadatas", [[]])[0] or []
    return docs, metas


def build_prompt(question: str, chunks: list[str]) -> str:
    if not chunks:
        return f"{_SYSTEM_PROMPT}\n\nВопрос: {question}"
    context_block = "\n\n---\n\n".join(chunks)
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        f"Фрагменты документов:\n\n{context_block}\n\n"
        f"Вопрос: {question}"
    )


async def answer_stream(
    question: str,
    context_paths: list[str],
    model: str,
    ollama: OllamaClient,
    embed_model: str,
    k: int = 5,
    think: bool | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Yields SSE events:
      {"type": "token", "content": "..."}
      {"type": "done", "sources": [...], "stale_warning": bool}
      {"type": "error", "msg": "..."}
    """
    if context_paths:
        try:
            embeddings = await ollama.embed([question], embed_model)
            q_embedding = embeddings[0]
        except Exception as e:
            yield {"type": "error", "msg": f"Ошибка эмбеддинга: {e}. Убедитесь, что Ollama запущена."}
            return

        chunks, metas = retrieve(question, context_paths, q_embedding, k)

        stale_warning = False
        if context_paths:
            from memo.db.models import IndexState
            from memo.db.session import SessionLocal
            expanded = _expand_paths(context_paths)
            with SessionLocal() as db:
                for fp in expanded:
                    row = db.query(IndexState).filter(IndexState.file_path == fp).first()
                    if row and row.status == "stale":
                        stale_warning = True
                        break

        if not chunks:
            prompt = build_prompt(question, [])
            no_context_msg = "В выбранных документах не найдено информации по этому вопросу. "
            sources: list[str] = []
        else:
            prompt = build_prompt(question, chunks)
            no_context_msg = ""
            sources = list({m["file_name"] for m in metas if "file_name" in m})
    else:
        prompt = build_prompt(question, [])
        no_context_msg = ""
        sources = []
        stale_warning = False

    try:
        async for chunk in ollama.generate_stream(model, prompt, think=think):
            token = chunk.get("response", "")
            if token:
                yield {"type": "token", "content": token}
            if chunk.get("done"):
                break
    except Exception as e:
        yield {"type": "error", "msg": f"Ошибка генерации: {e}. Убедитесь, что Ollama запущена."}
        return

    yield {"type": "done", "sources": sources, "stale_warning": stale_warning}
