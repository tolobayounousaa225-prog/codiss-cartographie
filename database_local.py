"""
Base de données SQLite — stable et sans dépendances externes
Le fichier DB est recréé automatiquement au démarrage si vide (auto-seed)
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Chemin du fichier SQLite : configurable via la variable d'environnement DB_PATH.
# En production sur Render, DB_PATH doit pointer vers le disque persistant monté
# (ex. /data/codiss_local.db) pour que les données survivent aux redéploiements.
# Sans cette variable (développement local), on garde l'ancien comportement.
DB_PATH = os.environ.get("DB_PATH", "./codiss_local.db")
# S'assurer que le dossier cible existe (utile la première fois sur un disque neuf)
_db_dir = os.path.dirname(DB_PATH)
if _db_dir and not os.path.exists(_db_dir):
    os.makedirs(_db_dir, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
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
