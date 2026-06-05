import pytest

from memo.services.rag import build_prompt, retrieve


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


def test_retrieve_multi_path_uses_in_filter(mock_chroma, tmp_path):
    fa = tmp_path / "a.txt"
    fb = tmp_path / "b.txt"
    fa.write_text("a")
    fb.write_text("b")
    mock_chroma.query.return_value = {"documents": [[]], "metadatas": [[]]}
    retrieve("q", [str(fa), str(fb)], [0.1])
    call_kwargs = mock_chroma.query.call_args[1]
    assert call_kwargs["where"]["file_path"]["$in"] == [str(fa), str(fb)]
