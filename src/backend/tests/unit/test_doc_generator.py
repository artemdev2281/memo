import pytest

from memo.services.doc_generator import generate_stream, suggest_filename
from memo.services.fs import save_document


class FakeOllama:
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
    chunks = []
    for d in deltas:
        chunks.append({"message": {"content": d}})
    if thinking is not None:
        chunks = [{"message": {"thinking": t}} for t in thinking] + chunks
    if chunks:
        chunks[-1]["done"] = True
    return chunks


# --- suggest_filename ---

def test_suggest_filename_md_heading():
    assert suggest_filename("# Мой документ\n\nТекст", ".md") == "Мой документ.md"


def test_suggest_filename_md_heading_no_space():
    assert suggest_filename("#Без пробела\n\nТекст", ".md") == "Без пробела.md"


def test_suggest_filename_md_no_heading_uses_first_line():
    assert suggest_filename("Первая строка\nВторая", ".md") == "Первая строка.md"


def test_suggest_filename_txt_uses_first_line():
    assert suggest_filename("Заголовок\nДальше", ".txt") == "Заголовок.txt"


def test_suggest_filename_sanitizes_invalid_chars():
    name = suggest_filename('# Имя: "файл"/документ\\test', ".md")
    for ch in r'\/:*?"<>|':
        assert ch not in name
    assert name.endswith(".md")


def test_suggest_filename_collapses_double_dots():
    name = suggest_filename("# Протокол..2025", ".md")
    assert ".." not in name
    assert name.endswith(".md")


def test_suggest_filename_truncates_long_name():
    long_text = "# " + "А" * 100
    name = suggest_filename(long_text, ".md")
    assert len(name) <= 63  # 60 chars base + ".md" extension


def test_suggest_filename_empty_text():
    name = suggest_filename("", ".txt")
    assert name == "document.txt"


def test_suggest_filename_whitespace_only():
    name = suggest_filename("   \n  ", ".md")
    assert name == "document.md"


# --- generate_stream ---

async def test_generate_stream_basic_tokens():
    chunks = _content("Привет", " мир")
    events = await _collect(
        generate_stream("запрос", ".txt", [], "mistral:latest", FakeOllama(chunks), "bge-m3", think=False)
    )
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert tokens == "Привет мир"
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["suggested_filename"].endswith(".txt")


async def test_generate_stream_md_filename_from_heading():
    chunks = _content("# Отчёт за неделю\n\nТекст")
    events = await _collect(
        generate_stream("создай", ".md", [], "mistral:latest", FakeOllama(chunks), "bge-m3")
    )
    done = next(e for e in events if e["type"] == "done")
    assert done["suggested_filename"] == "Отчёт за неделю.md"


async def test_generate_stream_strips_thinking_when_off(mock_chroma):
    chunks = _content("рассуждение </think>", "Результат")
    events = await _collect(
        generate_stream("создай", ".txt", [], "qwen3:4b", FakeOllama(chunks), "bge-m3", think=False)
    )
    assert not any(e["type"] == "thinking" for e in events)
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert "рассуждение" not in tokens
    assert "Результат" in tokens


async def test_generate_stream_emits_thinking_when_on():
    chunks = _content("Результат", thinking=["думаю"])
    events = await _collect(
        generate_stream("создай", ".md", [], "qwen3:1.7b", FakeOllama(chunks), "bge-m3", think=True)
    )
    thinking = "".join(e["content"] for e in events if e["type"] == "thinking")
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert "думаю" in thinking
    assert "Результат" in tokens


async def test_generate_stream_no_content_after_thinking_fallback():
    # Buffer never sees </think> → whole buffer becomes the answer.
    chunks = _content("Весь текст без тега")
    events = await _collect(
        generate_stream("создай", ".txt", [], "qwen3:4b", FakeOllama(chunks), "bge-m3", think=False)
    )
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert "Весь текст без тега" in tokens


# --- save_document ---

def test_save_document_success(tmp_path):
    path = save_document(str(tmp_path), "test.txt", "Hello")
    assert (tmp_path / "test.txt").read_text(encoding="utf-8") == "Hello"
    assert path.endswith("test.txt")


def test_save_document_collision_raises(tmp_path):
    (tmp_path / "exists.txt").write_text("old")
    with pytest.raises(ValueError, match="already exists"):
        save_document(str(tmp_path), "exists.txt", "new")


def test_save_document_path_separator_raises(tmp_path):
    with pytest.raises(ValueError):
        save_document(str(tmp_path), "sub/file.txt", "content")


def test_save_document_backslash_raises(tmp_path):
    with pytest.raises(ValueError):
        save_document(str(tmp_path), "sub\\file.txt", "content")


def test_save_document_dotdot_raises(tmp_path):
    with pytest.raises(ValueError):
        save_document(str(tmp_path), "../escape.txt", "content")


def test_save_document_nonexistent_folder_raises(tmp_path):
    with pytest.raises(ValueError):
        save_document(str(tmp_path / "nonexistent"), "file.txt", "content")


def test_save_document_empty_name_raises(tmp_path):
    with pytest.raises(ValueError):
        save_document(str(tmp_path), "", "content")
