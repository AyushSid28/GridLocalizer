from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class TelemetryIn(BaseModel):
    device_id: str
    pole_id: str
    event: Literal["heartbeat", "power_lost", "power_restored", "boot"]
    energized: bool
    ts: datetime
    seq: int
    battery_mv: int | None = None
    rssi: int | None = None
    fw: str = "1.4.2"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HealthOut(BaseModel):
    status: str
    service: str
    time: datetime = Field(default_factory=_now)
