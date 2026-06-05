from __future__ import annotations

import httpx


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def list(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            r = await client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            data = r.json()
            return [m["name"] for m in data.get("models", [])]

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        BATCH = 32
        results: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            batch = texts[i : i + BATCH]
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                r = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": model, "input": batch},
                )
                r.raise_for_status()
                results.extend(r.json()["embeddings"])
        return results

    async def generate_stream(self, model: str, prompt: str, num_ctx: int = 4096, think: bool | None = None):
        payload: dict = {"model": model, "prompt": prompt, "stream": True, "options": {"num_ctx": num_ctx}}
        if think is not None:
            payload["think"] = think
        async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line:
                        import json
                        yield json.loads(line)
