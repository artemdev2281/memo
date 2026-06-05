from fastapi import APIRouter

from memo.services.ollama_client import OllamaClient
from memo.settings import settings

router = APIRouter(tags=["models"])
_client = OllamaClient(settings.ollama_url)


@router.get("/models")
async def list_models() -> list[str]:
    try:
        return await _client.list()
    except Exception:
        return []
