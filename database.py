from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from models import *
from config import DATABASE_URL
import logging
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    poolclass=NullPool,  
    # pool_size=10,  # Adjust based on load
    # max_overflow=20,
    # pool_timeout=30,
    # pool_recycle=3600,
    # pool_pre_ping=True,  # Checks connection health
    connect_args={"ssl": "require"}
    # connect_args={"server_settings": {"jit": "off"}, 'statement_cache_size': 0, 'prepared_statement_name_func': lambda: str(uuid.uuid4())}
)
# Async session maker
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False,
)

async def init_db():
    async with engine.begin() as conn:
        logger.info(f"Creating database tables...")
        # Will create all tables, if not present.
        await conn.run_sync(SQLModel.metadata.create_all)


# await conn.run_sync(SQLModel.metadata.drop_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for request-scoped sessions"""
    async with async_session() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Production-ready context manager for database sessions.
    Use this for all business logic operations.
    """
    session = None
    try:
        session = async_session()
        yield session
        await session.commit()
    except Exception as e:
        if session:
            await session.rollback()
        logger.error(f"Database session error: {e}")
        raise e
    finally:
        if session:
            await session.close()
