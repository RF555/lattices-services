"""Database session management."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

# Supabase uses Supavisor (connection pooler) in transaction mode.
# asyncpg's prepared statement cache is incompatible with transaction-mode
# pooling, so we disable it when connecting through the pooler.
_connect_args: dict = {}
if "supabase.com" in settings.database_url or "pooler.supabase.com" in settings.database_url:
    _connect_args["statement_cache_size"] = 0

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

# Create async session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
