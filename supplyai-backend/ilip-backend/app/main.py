from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from psycopg import Error
from psycopg_pool import PoolTimeout
from .config import get_settings
from .db import make_pool
from .routes import router
from .dashboard import router as dashboard_router
from .departments import router as departments_router
from .alert_engine import router as alert_router
from .investigations import router as investigations_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = None
    # Supprimer les logs tiers pouvant inclure les détails d'une connexion.
    logging.getLogger('psycopg.pool').disabled = True
    try:
        app.state.pool = make_pool(get_settings().database_url.get_secret_value())
        if app.state.pool is not None: app.state.pool.open()
    except (ValueError, Error):
        logging.getLogger('ilip').warning('Configuration DATABASE_URL invalide; consulter .env. Aucun secret affiché.')
    try:
        yield
    finally:
        if app.state.pool is not None: app.state.pool.close()


app = FastAPI(title='ILIP - API locale', version='0.9.0', lifespan=lifespan,
              description='Développement local. Données lues depuis Neon, sans création ni import automatique.')
app.include_router(router)
app.include_router(dashboard_router)
app.include_router(departments_router)
app.include_router(alert_router)
app.include_router(investigations_router)


@app.exception_handler(Error)
@app.exception_handler(PoolTimeout)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Base indisponible ou schéma incompatible. Vérifier la connexion et le schéma ILIP.'})
