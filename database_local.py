"""
Base de données — supporte SQLite (local) ET PostgreSQL Neon/Render (prod)
DATABASE_URL défini → PostgreSQL avec SSL
Sinon → SQLite local
"""
import os
import ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

_raw_url = os.getenv("DATABASE_URL", "").strip()

if _raw_url:
    # Convertir postgres:// ou postgresql:// → postgresql+asyncpg://
    _url = _raw_url
    if _url.startswith("postgres://"):
        _url = "postgresql+asyncpg://" + _url[len("postgres://"):]
    elif _url.startswith("postgresql://"):
        _url = "postgresql+asyncpg://" + _url[len("postgresql://"):]

    # Supprimer ?sslmode=... de l'URL (géré via connect_args)
    if "?" in _url:
        _url = _url.split("?")[0]

    # Contexte SSL pour Neon (certificat serveur requis)
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE  # Neon free tier

    DATABASE_URL = _url
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"ssl": _ssl_ctx},
    )
    DB_MODE = "postgresql"
else:
    DATABASE_URL = "sqlite+aiosqlite:///./codiss_local.db"
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    DB_MODE = "sqlite"

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
