from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


# connect_timeout: fail fast (seconds) instead of hanging when the DB host does not answer.
# timezone=UTC: TIMESTAMPTZ values come back in UTC.
def connect_args() -> dict[str, Any]:
    options = (
        "-c timezone=UTC"
        f" -c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS}"
        f" -c lock_timeout={settings.DB_LOCK_TIMEOUT_MS}"
        f" -c idle_in_transaction_session_timeout={settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS}"
    )
    return {"connect_timeout": 5, "options": options}


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    hide_parameters=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    connect_args=connect_args(),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    """FastAPI dependency: opens a DB session per request and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
