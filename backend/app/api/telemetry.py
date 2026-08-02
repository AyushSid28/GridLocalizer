import json
import redis
from fastapi import APIRouter, Depends, status

from app.schemas import TelemetryIn
from app.settings import get_settings, Settings

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


def get_redis(settings: Settings = Depends(get_settings)):
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        client.close()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def ingest(
    event: TelemetryIn,
    settings: Settings = Depends(get_settings),
    r: redis.Redis = Depends(get_redis),
) -> dict:
    """Accept a device event and publish to Redis Stream."""
    data = event.model_dump()
    data["ts"] = event.ts.isoformat()

    r.xadd(settings.telemetry_stream, {"payload": json.dumps(data)})

    return {
        "accepted": True,
        "pole_id": event.pole_id,
        "seq": event.seq,
        "queued": True,
    }

