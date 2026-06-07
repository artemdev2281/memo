from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from memo.services import doc_generator, fs
from memo.services.ollama_client import get_client
from memo.settings import settings

router = APIRouter(prefix="/generate", tags=["generate"])


class GenerateRequest(BaseModel):
    request: str
    format: str = ".txt"
    context_paths: list[str] = []
    model: str
    thinking: bool | None = None


class SaveRequest(BaseModel):
    folder: str
    filename: str
    content: str


@router.post("/document")
async def generate_document(body: GenerateRequest) -> StreamingResponse:
    if body.format not in (".txt", ".md"):
        raise HTTPException(status_code=400, detail="format must be .txt or .md")

    ollama = get_client()

    async def stream():
        async for event in doc_generator.generate_stream(
            request=body.request,
            fmt=body.format,
            context_paths=body.context_paths,
            model=body.model,
            ollama=ollama,
            embed_model=settings.embed_model,
            think=body.thinking,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/save")
def save_document(body: SaveRequest) -> dict:
    try:
        path = fs.save_document(body.folder, body.filename, body.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"path": path, "name": body.filename}
