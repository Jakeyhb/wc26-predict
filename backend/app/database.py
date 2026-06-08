from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.postgres_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _ensure_postgres_extensions(dbapi_connection, connection_record):  # pragma: no cover - exercised in runtime
    if not settings.postgres_url.startswith("postgresql"):
        return
    cursor = None
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    except Exception:
        # Local sqlite / misconfigured postgres should not break import-time engine setup.
        import logging
        logging.getLogger(__name__).warning(
            "Failed to create PostgreSQL extensions (pgvector may be missing) — "
            "vector similarity search will be unavailable",
            exc_info=True,
        )
    finally:
        if cursor is not None:
            cursor.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
