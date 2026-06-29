"""
CODISS Cartographie - Backend FastAPI
API principale de l'application de cartographie CODISS
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
from database import engine, Base
from config import settings

# Import des routers (fichiers plats, pas de sous-dossier)
from router_auth     import router as auth_router
from router_branches import router as branches_router
from router_reports  import router as reports_router
from router_map      import router as map_router
from router_admin    import router as admin_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage : créer les tables si elles n'existent pas
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Arrêt : fermer le moteur
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API de cartographie de la représentativité du CODISS sur le territoire national de Côte d'Ivoire",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enregistrement des routers
app.include_router(auth_router,     prefix="/api/auth",     tags=["Authentification"])
app.include_router(branches_router, prefix="/api/branches", tags=["Branches"])
app.include_router(reports_router,  prefix="/api/reports",  tags=["Rapports"])
app.include_router(map_router,      prefix="/api/map",      tags=["Carte"])
app.include_router(admin_router,    prefix="/api/admin",    tags=["Administration"])

@app.get("/", tags=["Santé"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/api/docs"
    }

@app.get("/health", tags=["Santé"])
async def health():
    return {"status": "ok"}
