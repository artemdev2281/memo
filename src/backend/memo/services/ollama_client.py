from __future__ import annotations

import httpx

_THINKING_MODELS = frozenset({"qwen3", "deepseek-r1", "phi4-mini-reasoning", "marco-o1"})


def _supports_thinking(model: str) -> bool:
    return any(name in model.lower() for name in _THINKING_MODELS)


_shared: "OllamaClient | None" = None


def get_client() -> "OllamaClient":
    """Process-wide singleton — reuses one httpx connection pool."""
    global _shared
    if _shared is None:
        from memo.settings import settings

        _shared = OllamaClient(settings.ollama_url)
    return _shared


async def close_client() -> None:
    global _shared
    if _shared is not None:
        await _shared.close()
        _shared = None


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        # Single reusable client: connection pooling across batches/requests.
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=300.0, trust_env=False)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def is_available(self) -> bool:
        try:
            r = await self._http().get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    async def list(self) -> list[str]:
        r = await self._http().get(f"{self.base_url}/api/tags", timeout=10.0)
        r.raise_for_status()
        data = r.json()
        return [m["name"] for m in data.get("models", [])]

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        import asyncio

        BATCH = 32
        RETRIES = 4
        results: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            batch = texts[i : i + BATCH]
            for attempt in range(RETRIES):
                try:
                    r = await self._http().post(
                        f"{self.base_url}/api/embed",
                        json={"model": model, "input": batch},
                        timeout=120.0,
                    )
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
                    # A cold Ollama refuses/times out before it can answer (no
                    # 500) — retry with backoff instead of aborting the whole
                    # index on the first chunk.
                    if attempt < RETRIES - 1:
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    raise
                if r.status_code == 500 and attempt < RETRIES - 1:
                    # Ollama returns 500 while loading a model into memory.
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                r.raise_for_status()
                embeddings = r.json()["embeddings"]
                if len(embeddings) != len(batch):
                    raise ValueError(
                        f"Ollama returned {len(embeddings)} embeddings for "
                        f"{len(batch)} inputs"
                    )
                results.extend(embeddings)
                break
        return results

    async def generate_stream(self, model: str, prompt: str, num_ctx: int = 4096, think: bool | None = None):
        payload: dict = {"model": model, "prompt": prompt, "stream": True, "options": {"num_ctx": num_ctx}}
        if _supports_thinking(model):
            payload["think"] = think is True
        async with self._http().stream(
            "POST",
            f"{self.base_url}/api/generate",
            json=payload,
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line:
                    import json
                    yield json.loads(line)

    async def chat_stream(
        self,
        model: str,
        messages: list[dict],
        num_ctx: int = 4096,
        think: bool | None = None,
    ):
        """Stream from /api/chat. Each yielded chunk may carry message.content
        and/or message.thinking (separate reasoning field on supporting models)."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": num_ctx},
        }
        if _supports_thinking(model):
            payload["think"] = think is True
        async with self._http().stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line:
                    import json
                    yield json.loads(line)
