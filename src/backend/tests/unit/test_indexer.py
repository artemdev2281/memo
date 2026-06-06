import pytest

from memo.db.models import IndexState
from memo.services.indexer import _chunks, _expand_paths, index_files, mark_changed_stale


def test_chunks_basic():
    text = "A" * 2000
    result = _chunks(text, size=1000, overlap=100)
    assert len(result) == 3
    assert len(result[0]) == 1000
    assert len(result[1]) == 1000


def test_chunks_short_text():
    text = "Hello world"
    result = _chunks(text, size=1000, overlap=100)
    assert len(result) == 1
    assert result[0] == text


def test_chunks_empty():
    assert _chunks("") == []
    assert _chunks("   \n  ") == []


def test_chunks_overlap():
    text = "ABCDEFGHIJ"
    result = _chunks(text, size=5, overlap=2)
    assert result[0] == "ABCDE"
    assert result[1] == "DEFGH"


def test_expand_paths_single_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    result = _expand_paths([str(f)])
    assert str(f) in result
    assert len(result) == 1


def test_expand_paths_directory(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    result = _expand_paths([str(tmp_path)])
    assert len(result) == 2


def test_expand_paths_nonexistent():
    result = _expand_paths(["/nonexistent/path/file.txt"])
    assert result == []


class _FakeOllama:
    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.mark.asyncio
async def test_index_unsupported_file(tmp_path, in_memory_db, mock_chroma):
    f = tmp_path / "data.xlsx"
    f.write_bytes(b"fake")
    events = []
    async for e in index_files([str(f)], _FakeOllama(), "bge-m3"):
        events.append(e)
    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) == 1
    assert "Unsupported" in errors[0]["msg"]


@pytest.mark.asyncio
async def test_index_txt_file(tmp_path, in_memory_db, mock_chroma):
    f = tmp_path / "doc.txt"
    f.write_text("The quick brown fox " * 50, encoding="utf-8")
    events = []
    async for e in index_files([str(f)], _FakeOllama(), "bge-m3"):
        events.append(e)
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["file"] == str(f)


@pytest.mark.asyncio
async def test_index_skips_same_hash(tmp_path, in_memory_db, mock_chroma):
    f = tmp_path / "doc.txt"
    f.write_text("Hello world " * 50, encoding="utf-8")
    ollama = _FakeOllama()

    # First pass
    async for _ in index_files([str(f)], ollama, "bge-m3"):
        pass

    embed_calls_after_first = mock_chroma.add.call_count

    # Second pass with same file (hash unchanged) — must skip
    skips = []
    async for e in index_files([str(f)], ollama, "bge-m3"):
        if e["type"] == "skip":
            skips.append(e)

    assert len(skips) == 1
    assert mock_chroma.add.call_count == embed_calls_after_first


@pytest.mark.asyncio
async def test_index_metadata_includes_file_name_and_hash(tmp_path, in_memory_db, mock_chroma):
    f = tmp_path / "myfile.txt"
    f.write_text("Content " * 50, encoding="utf-8")
    async for _ in index_files([str(f)], _FakeOllama(), "bge-m3"):
        pass
    assert mock_chroma.add.called
    call_kwargs = mock_chroma.add.call_args[1]
    meta = call_kwargs["metadatas"][0]
    assert meta["file_name"] == "myfile.txt"
    assert "file_hash" in meta
    assert meta["file_path"] == str(f)


def _status(db_factory, path) -> str | None:
    with db_factory() as db:
        row = db.query(IndexState).filter(IndexState.file_path == path).first()
        return row.status if row else None


@pytest.mark.asyncio
async def test_mark_changed_stale_detects_repeated_edits(tmp_path, in_memory_db, mock_chroma):
    # Reproduces the reported bug: status must flip to stale on EVERY edit, not
    # just the first — even without the filesystem watcher firing.
    f = tmp_path / "doc.txt"
    f.write_text("one " * 50, encoding="utf-8")
    async for _ in index_files([str(f)], _FakeOllama(), "bge-m3"):
        pass
    assert _status(in_memory_db, str(f)) == "indexed"

    # First edit (different size) → detected.
    f.write_text("two longer content " * 50, encoding="utf-8")
    mark_changed_stale([str(f)])
    assert _status(in_memory_db, str(f)) == "stale"

    # Re-index, then a SECOND edit → must be detected again.
    async for _ in index_files([str(f)], _FakeOllama(), "bge-m3"):
        pass
    assert _status(in_memory_db, str(f)) == "indexed"
    f.write_text("three even more different content " * 50, encoding="utf-8")
    mark_changed_stale([str(f)])
    assert _status(in_memory_db, str(f)) == "stale"


@pytest.mark.asyncio
async def test_mark_changed_stale_leaves_unchanged_file_indexed(tmp_path, in_memory_db, mock_chroma):
    f = tmp_path / "doc.txt"
    f.write_text("stable content " * 50, encoding="utf-8")
    async for _ in index_files([str(f)], _FakeOllama(), "bge-m3"):
        pass
    mark_changed_stale([str(f)])
    assert _status(in_memory_db, str(f)) == "indexed"


def test_mark_changed_stale_ignores_untracked_and_missing(tmp_path, in_memory_db):
    # No row → no-op; unreadable/missing path → left untouched, no exception.
    mark_changed_stale([str(tmp_path / "never_indexed.txt")])
    assert _status(in_memory_db, str(tmp_path / "never_indexed.txt")) is None


@pytest.mark.asyncio
async def test_mark_changed_stale_skips_hashing_when_stat_unchanged(
    tmp_path, in_memory_db, mock_chroma, monkeypatch
):
    # The cheap mtime+size pre-filter must avoid re-hashing unchanged files.
    f = tmp_path / "doc.txt"
    f.write_text("content " * 50, encoding="utf-8")
    async for _ in index_files([str(f)], _FakeOllama(), "bge-m3"):
        pass

    import memo.services.indexer as indexer_mod

    calls = {"n": 0}
    real_hash = indexer_mod.compute_hash

    def _counting_hash(path):
        calls["n"] += 1
        return real_hash(path)

    monkeypatch.setattr(indexer_mod, "compute_hash", _counting_hash)
    mark_changed_stale([str(f)])
    assert calls["n"] == 0  # stat matched → no hashing
    assert _status(in_memory_db, str(f)) == "indexed"


@pytest.mark.asyncio
async def test_index_chroma_add_error_yields_error_event(tmp_path, in_memory_db, mock_chroma):
    mock_chroma.add.side_effect = ValueError("dimension mismatch")
    f = tmp_path / "doc.txt"
    f.write_text("Some text " * 50, encoding="utf-8")
    events = []
    async for e in index_files([str(f)], _FakeOllama(), "bge-m3"):
        events.append(e)
    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) == 1
    assert "Chroma add failed" in errors[0]["msg"]
