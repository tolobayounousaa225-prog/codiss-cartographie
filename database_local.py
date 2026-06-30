"""
Base de données — supporte SQLite (local) ET PostgreSQL (Render prod)
Si DATABASE_URL est défini dans les variables d'environnement → PostgreSQL
Sinon → SQLite local
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

_raw_url = os.getenv("DATABASE_URL", "")

if _raw_url:
    # Render fournit postgresql:// ou postgres:// — on convertit en asyncpg
    DATABASE_URL = (
        _raw_url
        .replace("postgres://", "postgresql+asyncpg://", 1)
        .replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
else:
    # Fallback SQLite local
    DATABASE_URL = "sqlite+aiosqlite:///./codiss_local.db"
    engine = create_async_engine(
        DATABASE_URL, echo=False,
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
