"""
Base de données — SQLite local ou PostgreSQL Neon/Render
Connexion LAZY : pas de connexion au démarrage, seulement à la première requête
"""
import os, ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

_raw_url = os.getenv("DATABASE_URL", "").strip()

if _raw_url:
    _url = _raw_url
    for old in ("postgres://", "postgresql://"):
        if _url.startswith(old):
            _url = "postgresql+asyncpg://" + _url[len(old):]
            break
    # Supprimer ?sslmode=... (syntaxe psycopg2, pas asyncpg)
    if "?" in _url:
        base, qs = _url.split("?", 1)
        kept = [p for p in qs.split("&") if not p.startswith("sslmode")]
        _url = base + ("?" + "&".join(kept) if kept else "")

    _ssl = ssl.create_default_context()
    _ssl.check_hostname = False
    _ssl.verify_mode   = ssl.CERT_NONE   # Neon cert OK sans vérification CA

    DATABASE_URL = _url
    DB_MODE      = "postgresql"
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"ssl": _ssl},
        # pool_pre_ping désactivé pour éviter crash au démarrage
    )
else:
    DATABASE_URL = "sqlite+aiosqlite:///./codiss_local.db"
    DB_MODE      = "sqlite"
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
