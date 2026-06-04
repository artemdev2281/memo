from fastapi import APIRouter

from memo.services.ollama_client import OllamaClient
from memo.settings import settings

router = APIRouter(tags=["health"])
_client = OllamaClient(settings.ollama_url)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "ollama": await _client.is_available()}
