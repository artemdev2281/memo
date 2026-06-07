import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from memo.db.models import Base
from memo.settings import settings


def _make_engine():
    data_dir = os.path.abspath(settings.data_dir)
    os.makedirs(data_dir, exist_ok=True)
    eng = create_engine(
        f"sqlite:///{os.path.join(data_dir, 'memo.db')}",
        connect_args={"check_same_thread": False},
    )

    # The app writes to SQLite from several threads concurrently — the watchdog
    # observer, the startup reconcile daemon, background /refresh-stale tasks and
    # the chat auto-index inside the request stream. WAL lets readers and a
    # writer coexist, and busy_timeout makes a blocked writer wait instead of
    # raising "database is locked" immediately.
    @event.listens_for(eng, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return eng


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
