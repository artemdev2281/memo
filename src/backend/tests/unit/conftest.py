from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memo.db.models import Base


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    monkeypatch.setattr("memo.db.session.SessionLocal", TestSession)
    monkeypatch.setattr("memo.services.indexer.SessionLocal", TestSession)
    monkeypatch.setattr("memo.services.watcher.SessionLocal", TestSession)
    monkeypatch.setattr("memo.services.fs.SessionLocal", TestSession)

    return TestSession


@pytest.fixture
def mock_chroma(monkeypatch):
    col = MagicMock()
    col.get.return_value = {
        "ids": [],
        "documents": [],
        "metadatas": [],
        "embeddings": [],
    }
    col.add.return_value = None
    col.delete.return_value = None

    monkeypatch.setattr("memo.chroma.get_collection", lambda: col)
    monkeypatch.setattr("memo.services.indexer.get_collection", lambda: col)

    return col
