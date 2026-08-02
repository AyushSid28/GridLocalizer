from fastapi import APIRouter, status

from app.schemas import TelemetryIn

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def ingest(event: TelemetryIn) -> dict:
    """Accept a device event. Queue wiring lands in P2; for now we ack shape only."""
    return {
        "accepted": True,
        "pole_id": event.pole_id,
        "seq": event.seq,
        "queued": False,
        "note": "ingest queue not wired yet",
    }
