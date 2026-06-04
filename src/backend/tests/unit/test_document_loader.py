import pytest

from memo.services.document_loader import SUPPORTED, Document, compute_hash, load


def test_txt_load(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("Hello, world!", encoding="utf-8")
    doc = load(str(f))
    assert isinstance(doc, Document)
    assert doc.text == "Hello, world!"
    assert doc.file_hash == compute_hash(str(f))
    assert doc.path == str(f)


def test_md_load(tmp_path):
    f = tmp_path / "hello.md"
    f.write_text("# Title\n\nContent goes here.", encoding="utf-8")
    doc = load(str(f))
    assert "Title" in doc.text
    assert "Content" in doc.text


def test_unsupported_format_raises(tmp_path):
    f = tmp_path / "data.xlsx"
    f.write_bytes(b"fake content")
    with pytest.raises(ValueError, match="Unsupported"):
        load(str(f))


def test_supported_formats_set():
    assert ".pdf" in SUPPORTED
    assert ".docx" in SUPPORTED
    assert ".md" in SUPPORTED
    assert ".txt" in SUPPORTED
    assert ".xlsx" not in SUPPORTED
    assert ".csv" not in SUPPORTED


def test_hash_differs_on_content_change(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("original", encoding="utf-8")
    h1 = compute_hash(str(f))
    f.write_text("modified", encoding="utf-8")
    h2 = compute_hash(str(f))
    assert h1 != h2


def test_hash_stable(tmp_path):
    f = tmp_path / "stable.txt"
    f.write_text("same content", encoding="utf-8")
    assert compute_hash(str(f)) == compute_hash(str(f))
