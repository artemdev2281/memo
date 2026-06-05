from fastapi import APIRouter

from memo.services.ollama_client import get_client

router = APIRouter(tags=["models"])

_EMBED_PREFIXES = ("bge-", "nomic-embed", "all-minilm", "mxbai-embed", "snowflake-arctic-embed")


def _is_embed_model(name: str) -> bool:
    lower = name.lower()
    return any(lower.startswith(p) or f"/{p}" in lower for p in _EMBED_PREFIXES)


@router.get("/models")
async def list_models() -> list[str]:
    try:
        all_models = await get_client().list()
        return [m for m in all_models if not _is_embed_model(m)]
    except Exception:
        return []
