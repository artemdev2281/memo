from __future__ import annotations

import os
import re
from typing import AsyncGenerator

from memo.services.ollama_client import OllamaClient, _supports_thinking
from memo.services.rag import retrieve

_INVALID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MAX_NAME_LEN = 60

_SYSTEM_MD = (
    "Ты — генератор документов. Создай хорошо структурированный Markdown-документ: "
    "используй заголовки (#, ##), списки (-, *), выделение (**жирный**, *курсив*). "
    "Начни документ сразу с содержания, без вводных фраз и объяснений."
)
_SYSTEM_TXT = (
    "Ты — генератор документов. Создай документ в формате plain text без Markdown-разметки. "
    "Начни документ сразу с содержания, без вводных фраз и объяснений."
)
_CONTEXT_HINT = " Используй предоставленные фрагменты документов как источник информации и контекст."


def _build_messages(request: str, fmt: str, chunks: list[str]) -> list[dict]:
    base = _SYSTEM_MD if fmt == ".md" else _SYSTEM_TXT
    if chunks:
        context_block = "\n\n---\n\n".join(chunks)
        system_content = base + _CONTEXT_HINT + f"\n\nФрагменты документов:\n\n{context_block}"
    else:
        system_content = base
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": request},
    ]


def suggest_filename(text: str, fmt: str) -> str:
    """Derive a safe filename from generated text."""
    name = ""
    if fmt == ".md":
        m = re.search(r"^#{1,3}\s*(.+)", text, re.MULTILINE)
        if m:
            name = m.group(1).strip()
    if not name:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                name = stripped
                break
    name = _INVALID_CHARS.sub("", name)
    name = re.sub(r"\.{2,}", ".", name)  # collapse .. sequences that would trip save_document
    name = name.strip(". ")
    name = name[:_MAX_NAME_LEN]
    if not name:
        name = "document"
    return name + fmt


async def generate_stream(
    request: str,
    fmt: str,
    context_paths: list[str],
    model: str,
    ollama: OllamaClient,
    embed_model: str,
    think: bool | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Yields SSE events:
      {"type": "thinking", "content": "..."}   # only when think=ON
      {"type": "token", "content": "..."}
      {"type": "done", "suggested_filename": str}
      {"type": "error", "msg": "..."}
    """
    chunks: list[str] = []

    if context_paths:
        try:
            embeddings = await ollama.embed([request], embed_model)
            q_embedding = embeddings[0]
        except Exception as e:
            yield {"type": "error", "msg": f"Ошибка эмбеддинга: {e}. Убедитесь, что Ollama запущена."}
            return
        chunk_texts, _ = retrieve(request, context_paths, q_embedding)
        chunks = chunk_texts

    messages = _build_messages(request, fmt, chunks)

    think_on = think is True
    answer_started = not _supports_thinking(model)
    content_buf = ""
    full_content: list[str] = []

    try:
        async for chunk in ollama.chat_stream(model, messages, think=think):
            msg = chunk.get("message", {}) or {}
            thinking_delta = msg.get("thinking") or ""
            content_delta = msg.get("content") or ""

            if thinking_delta:
                if think_on:
                    yield {"type": "thinking", "content": thinking_delta}
                answer_started = True

            if content_delta:
                if answer_started:
                    full_content.append(content_delta)
                    yield {"type": "token", "content": content_delta}
                else:
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
                            full_content.append(after)
                            yield {"type": "token", "content": after}

            if chunk.get("done"):
                break
    except Exception as e:
        yield {"type": "error", "msg": f"Ошибка генерации: {e}. Убедитесь, что Ollama запущена."}
        return

    if not answer_started and content_buf:
        answer = content_buf.lstrip("\n")
        if answer:
            full_content.append(answer)
            yield {"type": "token", "content": answer}

    text = "".join(full_content)
    yield {"type": "done", "suggested_filename": suggest_filename(text, fmt)}
