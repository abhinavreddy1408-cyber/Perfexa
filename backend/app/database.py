"""
Database setup using SQLAlchemy and async SQLite (aiosqlite).
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from backend.app.config import DATABASE_URL

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


async def init_db():
    """Creates database tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency for database session."""
    async with async_session() as session:
        yield session
