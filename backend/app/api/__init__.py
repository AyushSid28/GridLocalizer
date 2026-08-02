from fastapi import APIRouter

from app.api import health, network, telemetry

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(telemetry.router)
api_router.include_router(network.router)
