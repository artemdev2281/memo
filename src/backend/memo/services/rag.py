from __future__ import annotations

import os
from typing import AsyncGenerator

from memo.chroma import get_collection
from memo.services.indexer import _expand_paths
from memo.services.ollama_client import OllamaClient, _supports_thinking

_SYSTEM_PROMPT = (
    "Ты — AI-ассистент, который отвечает на вопросы исключительно на основе предоставленных фрагментов документов. "
    "Если ответ не содержится в документах, скажи об этом прямо. "
    "Отвечай на том языке, на котором задан вопрос."
)

_GENERAL_SYSTEM_PROMPT = (
    "Ты — полезный AI-ассистент. Отвечай ясно и по существу, учитывая историю диалога. "
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


_HISTORY_LIMIT = 20  # max prior turns sent to the model (keeps KV-cache bounded)


def _build_messages(
    question: str,
    context_block: str,
    history: list[dict],
) -> list[dict]:
    # With documents → strict RAG prompt; without → general chat so the model
    # uses conversation history normally instead of refusing "not in documents".
    if context_block:
        system_content = f"{_SYSTEM_PROMPT}\n\nФрагменты документов:\n\n{context_block}"
    else:
        system_content = _GENERAL_SYSTEM_PROMPT
    messages = [{"role": "system", "content": system_content}]
    recent = history[-_HISTORY_LIMIT:]
    for m in recent:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})
    return messages


async def answer_stream(
    question: str,
    context_paths: list[str],
    model: str,
    ollama: OllamaClient,
    embed_model: str,
    history: list[dict] | None = None,
    k: int = 5,
    think: bool | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Yields SSE events:
      {"type": "thinking", "content": "..."}   # only when think=ON
      {"type": "token", "content": "..."}
      {"type": "done", "sources": [...], "stale_warning": bool}
      {"type": "error", "msg": "..."}

    Reasoning splitter: handles both Ollama behaviours — a separate `thinking`
    field, and reasoning emitted inline in `content` terminated by `</think>`
    (qwen3:4b ignores think=false). With think=OFF reasoning is stripped so the
    user only sees the clean answer, regardless of model behaviour.
    """
    history = history or []
    context_block = ""
    sources: list[str] = []
    stale_warning = False

    if context_paths:
        try:
            embeddings = await ollama.embed([question], embed_model)
            q_embedding = embeddings[0]
        except Exception as e:
            yield {"type": "error", "msg": f"Ошибка эмбеддинга: {e}. Убедитесь, что Ollama запущена."}
            return

        chunks, metas = retrieve(question, context_paths, q_embedding, k)

        from memo.db.models import IndexState
        from memo.db.session import SessionLocal
        expanded = _expand_paths(context_paths)
        with SessionLocal() as db:
            for fp in expanded:
                row = db.query(IndexState).filter(IndexState.file_path == fp).first()
                # "error" also means the file's current content isn't reflected
                # in the index → warn the user the answer may be incomplete.
                if row and row.status in ("stale", "error"):
                    stale_warning = True
                    break

        if chunks:
            context_block = "\n\n---\n\n".join(chunks)
            sources = list({m["file_name"] for m in metas if "file_name" in m})

    messages = _build_messages(question, context_block, history)

    think_on = think is True
    # Non-reasoning models can't emit hidden reasoning → stream directly.
    answer_started = not _supports_thinking(model)
    content_buf = ""

    try:
        async for chunk in ollama.chat_stream(model, messages, think=think):
            msg = chunk.get("message", {}) or {}
            thinking_delta = msg.get("thinking") or ""
            content_delta = msg.get("content") or ""

            if thinking_delta:
                if think_on:
                    yield {"type": "thinking", "content": thinking_delta}
                # Reasoning arrives on the dedicated `thinking` channel → `content`
                # is already the clean answer. Stream it directly instead of
                # buffering for a </think> marker that will never come (the bug
                # that previously held the whole answer back until the end).
                answer_started = True

            if content_delta:
                if answer_started:
                    yield {"type": "token", "content": content_delta}
                else:
                    # No dedicated thinking field seen yet → reasoning may be
                    # inline, terminated by </think> (qwen3 ignoring think=false),
                    # with or without an opening <think>. Buffer until we see it.
                    content_buf += content_delta
                    if "</think>" in content_buf:
                        before, after = content_buf.split("</think>", 1)
                        if before.startswith("<think>"):
                            before = before[len("<think>"):]
                        if think_on and before.strip():
                            yield {"type": "thinking", "content": before}
                        answer_started = True
                        content_buf = ""
                        after = after.lstrip("\n")
                        if after:
                            yield {"type": "token", "content": after}

            if chunk.get("done"):
                break
    except Exception as e:
        yield {"type": "error", "msg": f"Ошибка генерации: {e}. Убедитесь, что Ollama запущена."}
        return

    # No </think> ever seen → the whole buffer was the answer.
    if not answer_started and content_buf:
        answer = content_buf.lstrip("\n")
        if answer:
            yield {"type": "token", "content": answer}

    yield {"type": "done", "sources": sources, "stale_warning": stale_warning}
