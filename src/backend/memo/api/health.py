from fastapi import APIRouter

from memo.services.ollama_client import get_client

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "ollama": await get_client().is_available()}
