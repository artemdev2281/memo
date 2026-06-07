import pytest

from memo.services.rag import answer_stream, build_prompt, retrieve


class FakeOllama:
    """Minimal stand-in for OllamaClient driving answer_stream."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def embed(self, texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def chat_stream(self, model, messages, num_ctx=4096, think=None):
        for c in self._chunks:
            yield c


async def _collect(gen):
    return [e async for e in gen]


def _content(*deltas, thinking=None):
    """Build /api/chat-style chunks; last one carries done=True."""
    chunks = []
    for d in deltas:
        chunks.append({"message": {"content": d}})
    if thinking is not None:
        chunks = [{"message": {"thinking": t}} for t in thinking] + chunks
    if chunks:
        chunks[-1]["done"] = True
    return chunks


async def test_splitter_think_off_strips_inline_reasoning():
    # qwen3:4b ignores think=false: reasoning inline, terminated by </think>.
    chunks = _content("reason aloud ", "</think>", "Hello", " world")
    events = await _collect(
        answer_stream("q", [], "qwen3:4b", FakeOllama(chunks), "bge-m3", think=False)
    )
    assert not any(e["type"] == "thinking" for e in events)
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert answer == "Hello world"
    assert events[-1]["type"] == "done"


async def test_splitter_think_on_emits_reasoning():
    chunks = _content("reason aloud ", "</think>", "Hello", " world")
    events = await _collect(
        answer_stream("q", [], "qwen3:4b", FakeOllama(chunks), "bge-m3", think=True)
    )
    thinking = "".join(e["content"] for e in events if e["type"] == "thinking")
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert "reason aloud" in thinking
    assert answer == "Hello world"


async def test_clean_answer_non_reasoning_model_streams_directly():
    # mistral has no hidden reasoning → tokens flow immediately, no buffering.
    chunks = _content("Hello", " world")
    events = await _collect(
        answer_stream("q", [], "mistral:latest", FakeOllama(chunks), "bge-m3", think=False)
    )
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert answer == "Hello world"
    assert not any(e["type"] == "thinking" for e in events)


async def test_separate_thinking_field_on():
    # qwen3:1.7b respects the param: reasoning in `thinking`, content clean.
    chunks = _content("Answer", thinking=["reason ", "more"])
    events = await _collect(
        answer_stream("q", [], "qwen3:1.7b", FakeOllama(chunks), "bge-m3", think=True)
    )
    thinking = "".join(e["content"] for e in events if e["type"] == "thinking")
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert thinking == "reason more"
    assert answer == "Answer"


async def test_separate_thinking_field_streams_incrementally():
    # Regression: with reasoning on the dedicated `thinking` field, the answer
    # content carries no </think> marker. The splitter must NOT buffer it until
    # the end — each content delta should surface as its own token event.
    chunks = _content("Hello", " world", thinking=["reason"])
    events = await _collect(
        answer_stream("q", [], "qwen3:1.7b", FakeOllama(chunks), "bge-m3", think=True)
    )
    token_events = [e for e in events if e["type"] == "token"]
    assert [e["content"] for e in token_events] == ["Hello", " world"]


async def test_separate_thinking_field_discarded_when_off():
    chunks = _content("Answer", thinking=["reason ", "more"])
    events = await _collect(
        answer_stream("q", [], "qwen3:1.7b", FakeOllama(chunks), "bge-m3", think=False)
    )
    assert not any(e["type"] == "thinking" for e in events)
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert answer == "Answer"


def test_build_prompt_with_chunks():
    prompt = build_prompt("What is X?", ["chunk A", "chunk B"])
    assert "chunk A" in prompt
    assert "chunk B" in prompt
    assert "What is X?" in prompt


def test_build_prompt_empty_chunks():
    prompt = build_prompt("What is X?", [])
    assert "What is X?" in prompt


def test_retrieve_empty_collection(mock_chroma):
    mock_chroma.query.return_value = {"documents": [[]], "metadatas": [[]]}
    docs, metas = retrieve("question", ["/some/file.txt"], [0.1, 0.2, 0.3])
    assert docs == []
    assert metas == []


def test_retrieve_with_results(mock_chroma, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("content")
    mock_chroma.query.return_value = {
        "documents": [["chunk text"]],
        "metadatas": [[{"file_path": str(f), "file_name": "a.txt", "chunk_index": 0, "file_hash": "abc"}]],
    }
    docs, metas = retrieve("question", [str(f)], [0.1, 0.2, 0.3])
    assert len(docs) == 1
    assert docs[0] == "chunk text"
    assert metas[0]["file_name"] == "a.txt"


def test_retrieve_no_context(mock_chroma):
    mock_chroma.query.return_value = {"documents": [[]], "metadatas": [[]]}
    docs, metas = retrieve("question", [], [0.1, 0.2, 0.3])
    assert docs == []


def test_retrieve_uses_context_filter(mock_chroma, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("content")
    mock_chroma.query.return_value = {"documents": [[]], "metadatas": [[]]}
    retrieve("question", [str(f)], [0.1])
    call_kwargs = mock_chroma.query.call_args[1]
    assert "where" in call_kwargs
    assert call_kwargs["where"] == {"file_path": str(f)}


def test_retrieve_drops_chunks_beyond_distance_threshold(mock_chroma, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("content")
    mock_chroma.query.return_value = {
        "documents": [["close chunk", "far chunk"]],
        "metadatas": [
            [
                {"file_path": str(f), "file_name": "a.txt", "chunk_index": 0},
                {"file_path": str(f), "file_name": "a.txt", "chunk_index": 1},
            ]
        ],
        "distances": [[0.2, 1.5]],  # second chunk is well past the threshold
    }
    docs, metas = retrieve("question", [str(f)], [0.1, 0.2, 0.3])
    assert docs == ["close chunk"]
    assert len(metas) == 1


def test_retrieve_keeps_all_when_distances_absent(mock_chroma, tmp_path):
    # Back-compat: a query result without a distances field must not be filtered.
    f = tmp_path / "a.txt"
    f.write_text("content")
    mock_chroma.query.return_value = {
        "documents": [["chunk text"]],
        "metadatas": [[{"file_path": str(f), "file_name": "a.txt", "chunk_index": 0}]],
    }
    docs, _ = retrieve("question", [str(f)], [0.1, 0.2, 0.3])
    assert docs == ["chunk text"]


def test_retrieve_multi_path_uses_in_filter(mock_chroma, tmp_path):
    fa = tmp_path / "a.txt"
    fb = tmp_path / "b.txt"
    fa.write_text("a")
    fb.write_text("b")
    mock_chroma.query.return_value = {"documents": [[]], "metadatas": [[]]}
    retrieve("q", [str(fa), str(fb)], [0.1])
    call_kwargs = mock_chroma.query.call_args[1]
    assert call_kwargs["where"]["file_path"]["$in"] == [str(fa), str(fb)]
