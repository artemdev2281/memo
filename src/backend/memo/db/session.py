import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from memo.db.models import Base
from memo.settings import settings


def _make_engine():
    data_dir = os.path.abspath(settings.data_dir)
    os.makedirs(data_dir, exist_ok=True)
    return create_engine(
        f"sqlite:///{os.path.join(data_dir, 'memo.db')}",
        connect_args={"check_same_thread": False},
    )


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
