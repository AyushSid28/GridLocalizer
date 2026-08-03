from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.db import SessionLocal, init_db, migrate_db
from app.services.seed import ensure_seed
from app.services.topo_index import refresh_topology
from app.settings import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    migrate_db()
    with SessionLocal() as db:
        ensure_seed(db)
        refresh_topology(db)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Outage Fault Localizer",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
