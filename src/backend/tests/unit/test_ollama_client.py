import httpx
import respx

from memo.services.ollama_client import OllamaClient

TAGS_URL = "http://localhost:11434/api/tags"


@respx.mock
async def test_is_available_true():
    respx.get(TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
    assert await OllamaClient().is_available() is True


@respx.mock
async def test_is_available_connection_error():
    respx.get(TAGS_URL).mock(side_effect=httpx.ConnectError("refused"))
    assert await OllamaClient().is_available() is False


@respx.mock
async def test_is_available_non_200():
    respx.get(TAGS_URL).mock(return_value=httpx.Response(503))
    assert await OllamaClient().is_available() is False


@respx.mock
async def test_list_models():
    respx.get(TAGS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "qwen3:4b"}, {"name": "bge-m3"}]},
        )
    )
    models = await OllamaClient().list()
    assert models == ["qwen3:4b", "bge-m3"]


@respx.mock
async def test_list_models_empty():
    respx.get(TAGS_URL).mock(return_value=httpx.Response(200, json={"models": []}))
    assert await OllamaClient().list() == []
