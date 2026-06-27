from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy import create_engine

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Async engine + session — used by FastAPI route handlers
# ---------------------------------------------------------------------------
_async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    _async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async SQLAlchemy session."""
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Sync engine + session — used by Celery worker tasks
# ---------------------------------------------------------------------------
_sync_engine = create_engine(
    settings.sync_database_url,
    echo=False,
    pool_pre_ping=True,
)
SyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=_sync_engine,
)


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Context manager for synchronous DB access in Celery tasks.

    Automatically commits on success and rolls back on exception.
    """
    session: Session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
