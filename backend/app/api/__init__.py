from fastapi import APIRouter

from app.api import health, network, telemetry, incidents, sim, breadcrumb

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(telemetry.router)
api_router.include_router(network.router)
api_router.include_router(incidents.router)
api_router.include_router(sim.router)
api_router.include_router(breadcrumb.router)


