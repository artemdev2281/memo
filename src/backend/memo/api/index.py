import json

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from memo.db.models import IndexState
from memo.db.session import SessionLocal
from memo.services.indexer import index_files
from memo.services.ollama_client import OllamaClient
from memo.settings import settings

router = APIRouter(prefix="/index", tags=["index"])


class IndexRequest(BaseModel):
    paths: list[str]


def _make_ollama() -> OllamaClient:
    return OllamaClient(settings.ollama_url)


@router.post("")
async def index_endpoint(body: IndexRequest) -> StreamingResponse:
    ollama = _make_ollama()

    async def stream():
        async for event in index_files(body.paths, ollama, settings.embed_model):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status")
def get_status() -> list[dict]:
    with SessionLocal() as db:
        rows = db.query(IndexState).all()
        return [
            {
                "file_path": r.file_path,
                "status": r.status,
                "error_msg": r.error_msg,
                "indexed_at": r.indexed_at.isoformat() if r.indexed_at else None,
            }
            for r in rows
        ]


async def _run_index_bg(paths: list[str]) -> None:
    ollama = _make_ollama()
    async for _ in index_files(paths, ollama, settings.embed_model):
        pass


@router.post("/refresh-stale")
async def refresh_stale(bg: BackgroundTasks) -> dict:
    with SessionLocal() as db:
        stale = [r.file_path for r in db.query(IndexState).filter(IndexState.status == "stale").all()]
    if not stale:
        return {"started": 0}
    bg.add_task(_run_index_bg, stale)
    return {"started": len(stale)}
