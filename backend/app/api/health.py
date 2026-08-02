from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.db import SessionLocal
from app.schemas import HealthOut
from app.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok", service="api", time=datetime.now(timezone.utc))


@router.get("/health/ready")
def ready() -> dict:
    """Liveness is cheap; readiness checks Postgres."""
    settings = get_settings()
    db_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:  # noqa: BLE001 — surface for operators
        return {
            "status": "not_ready",
            "database": False,
            "redis_url_set": bool(settings.redis_url),
            "error": str(exc),
        }

    return {
        "status": "ready" if db_ok else "not_ready",
        "database": db_ok,
        "redis_url_set": bool(settings.redis_url),
    }
