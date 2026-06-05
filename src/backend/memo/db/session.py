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
    _migrate_add_missing_columns()


def _migrate_add_missing_columns() -> None:
    """Add columns that exist in models but not yet in the DB (forward-only migration)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    col_type = col.type.compile(engine.dialect)
                    nullable = "NULL" if col.nullable else "NOT NULL"
                    default = ""
                    if col.default is not None and col.default.is_scalar:
                        val = col.default.arg
                        default = f" DEFAULT '{val}'" if isinstance(val, str) else f" DEFAULT {int(val)}"
                    conn.execute(text(
                        f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type} {nullable}{default}"
                    ))
            conn.commit()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
