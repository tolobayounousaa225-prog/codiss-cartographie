"""
Base de données — SQLite (local) ou PostgreSQL Neon/Render (prod)
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

_raw_url = os.getenv("DATABASE_URL", "").strip()

if _raw_url:
    # Neon/Render donnent postgresql:// ou postgres://
    # asyncpg a besoin de postgresql+asyncpg://
    _url = _raw_url
    for prefix in ("postgres://", "postgresql://"):
        if _url.startswith(prefix):
            _url = "postgresql+asyncpg://" + _url[len(prefix):]
            break

    # Garder ?sslmode=require tel quel — asyncpg le gère nativement
    # Juste s'assurer qu'on n'a pas de doublon asyncpg
    DATABASE_URL = _url
    DB_MODE = "postgresql"
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        # Pas de pool_pre_ping sur free tier (évite crash au démarrage)
        pool_size=2,
        max_overflow=3,
    )
else:
    DATABASE_URL = "sqlite+aiosqlite:///./codiss_local.db"
    DB_MODE = "sqlite"
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
