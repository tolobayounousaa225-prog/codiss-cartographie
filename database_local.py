"""
Base de données — SQLite (local) ou PostgreSQL Neon/Render (prod)
DATABASE_URL fourni par Render ou variable d'env → PostgreSQL
Sinon → SQLite local
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

_raw_url = os.getenv("DATABASE_URL", "").strip()

if _raw_url:
    # Convertir postgres:// ou postgresql:// → postgresql+asyncpg://
    _url = _raw_url
    for old in ("postgres://", "postgresql://"):
        if _url.startswith(old):
            _url = "postgresql+asyncpg://" + _url[len(old):]
            break

    # asyncpg utilise ?ssl=true, PAS ?sslmode=require (syntaxe psycopg2)
    # On supprime sslmode et on passe ssl via connect_args
    if "?" in _url:
        base, qs = _url.split("?", 1)
        params = [p for p in qs.split("&") if not p.startswith("sslmode")]
        _url = base + ("?" + "&".join(params) if params else "")

    DATABASE_URL = _url
    DB_MODE = "postgresql"
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"ssl": True},   # SSL requis pour Neon
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
