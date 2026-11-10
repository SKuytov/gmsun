from __future__ import annotations

from collections.abc import Generator

import logging

from sqlalchemy import String, Text, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


_log = logging.getLogger("gmsun.db")


@event.listens_for(Session, "before_flush")
def _fit_string_lengths(session: Session, _ctx, _instances) -> None:
    """Safety net: a text longer than its VARCHAR column would make PostgreSQL reject the whole request (HTTP 500).
    Long free texts use TEXT columns; anything else that is still too long is shortened here instead of failing."""
    for obj in list(session.new) + list(session.dirty):
        table = getattr(obj, "__table__", None)
        if table is None:
            continue
        for col in table.columns:
            if not isinstance(col.type, String) or isinstance(col.type, Text) or not col.type.length:
                continue
            v = getattr(obj, col.key, None)
            if isinstance(v, str) and len(v) > col.type.length:
                _log.warning("%s.%s shortened from %d to %d characters", table.name, col.name, len(v), col.type.length)
                setattr(obj, col.key, v[: col.type.length])


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns() -> list[str]:
    """Minimal forward migration: add columns that exist in the models but not in the database
    (SQLite/PostgreSQL ``ALTER TABLE … ADD COLUMN``). Returns the list of added ``table.column``."""
    added: list[str] = []
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ctype = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ctype}'))
                added.append(f"{table.name}.{col.name}")
    if engine.dialect.name == "postgresql":
        # widen VARCHAR columns that became TEXT in the models (e.g. long custom quote-line texts)
        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue
                db_cols = {c["name"]: c["type"] for c in insp.get_columns(table.name)}
                for col in table.columns:
                    t = db_cols.get(col.name)
                    if isinstance(col.type, Text) and t is not None and getattr(t, "length", None):
                        conn.execute(text(f'ALTER TABLE {table.name} ALTER COLUMN {col.name} TYPE TEXT'))
                        added.append(f"{table.name}.{col.name}:text")
    return added
