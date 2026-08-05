import threading
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

    # Start telemetry consumer worker in a background daemon thread
    # so it runs inside the same free Render web service process
    from app.worker import main as worker_main
    t = threading.Thread(target=worker_main, daemon=True, name="telemetry-worker")
    t.start()

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

    from fastapi.responses import JSONResponse
    from fastapi import Request
    import logging
    import traceback

    log = logging.getLogger(__name__)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        if settings.expose_error_details:
            detail = f"Internal Server Error: {traceback.format_exc()}"
        else:
            detail = "Internal Server Error"
        return JSONResponse(status_code=500, content={"detail": detail})

    app.include_router(api_router)
    return app


app = create_app()
