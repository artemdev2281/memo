from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from memo.services import chat_store
from memo.services.indexer import index_files
from memo.services.ollama_client import OllamaClient, get_client
from memo.services.rag import answer_stream
from memo.settings import settings

router = APIRouter(prefix="/chats", tags=["chats"])


def _make_ollama() -> OllamaClient:
    return get_client()


class CreateChatRequest(BaseModel):
    model: str
    context_type: str = "none"
    context_paths: list[str] = []
    include_subfolders: bool = False


class UpdateChatRequest(BaseModel):
    title: str | None = None
    model: str | None = None
    context_type: str | None = None
    context_paths: list[str] | None = None
    include_subfolders: bool | None = None


class SendMessageRequest(BaseModel):
    content: str
    model: str | None = None
    context_paths: list[str] | None = None
    thinking: bool | None = None


@router.get("")
def get_chats() -> list[dict]:
    return chat_store.list_chats()


@router.post("")
def create_chat(body: CreateChatRequest) -> dict:
    return chat_store.create_chat(
        model=body.model,
        context_type=body.context_type,
        context_paths=body.context_paths,
        include_subfolders=body.include_subfolders,
    )


@router.patch("/{chat_id}")
def update_chat(chat_id: int, body: UpdateChatRequest) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = chat_store.update_chat(chat_id, **updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return result


@router.delete("/{chat_id}")
def delete_chat(chat_id: int) -> dict:
    if not chat_store.delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"ok": True}


@router.get("/{chat_id}/messages")
def get_messages(chat_id: int) -> list[dict]:
    chat = chat_store.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat_store.list_messages(chat_id)


@router.post("/{chat_id}/messages")
async def send_message(chat_id: int, body: SendMessageRequest) -> StreamingResponse:
    chat = chat_store.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    model = body.model or chat["model"]
    context_paths = body.context_paths if body.context_paths is not None else chat["context_paths"]

    if not model:
        raise HTTPException(status_code=400, detail="No model selected")

    # Prior turns BEFORE the current user message — conversational memory.
    history = chat_store.list_messages(chat_id)

    chat_store.add_message(chat_id, "user", body.content)

    is_first_message = len(history) == 0
    if is_first_message or chat["title"] == "Новый чат":
        chat_store.set_chat_title_from_question(chat_id, body.content)

    if context_paths:
        ollama = _make_ollama()
        async def _auto_index():
            from memo.db.models import IndexState
            from memo.db.session import SessionLocal
            from memo.services.indexer import _expand_paths
            expanded = _expand_paths(context_paths)
            needs_index = []
            with SessionLocal() as db:
                for fp in expanded:
                    row = db.query(IndexState).filter(IndexState.file_path == fp).first()
                    if not row or row.status in ("stale", "error"):
                        needs_index.append(fp)
            if needs_index:
                async for _ in index_files(needs_index, ollama, settings.embed_model):
                    pass
        await _auto_index()

    async def stream():
        ollama = _make_ollama()
        full_content: list[str] = []
        full_thinking: list[str] = []

        async for event in answer_stream(
            question=body.content,
            context_paths=context_paths,
            model=model,
            ollama=ollama,
            embed_model=settings.embed_model,
            history=history,
            think=body.thinking,
        ):
            if event["type"] == "token":
                full_content.append(event["content"])
                yield f"data: {json.dumps(event)}\n\n"
            elif event["type"] == "thinking":
                full_thinking.append(event["content"])
                yield f"data: {json.dumps(event)}\n\n"
            elif event["type"] == "done":
                sources = event.get("sources", [])
                stale_warning = event.get("stale_warning", False)
                thinking = "".join(full_thinking) or None
                chat_store.add_message(
                    chat_id, "assistant", "".join(full_content), sources, thinking=thinking
                )
                yield f"data: {json.dumps({'type': 'done', 'sources': sources, 'stale_warning': stale_warning})}\n\n"
            elif event["type"] == "error":
                yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
