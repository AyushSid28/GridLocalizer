import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status
import redis
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Pole, PoleState
from app.services.topo_index import get_topology
from app.settings import get_settings, Settings

router = APIRouter(prefix="/sim", tags=["simulation"])
log = logging.getLogger(__name__)


class FaultInjectionIn(BaseModel):
    kind: Literal["feeder", "dt", "span", "pole"]
    target_id: str | None = None  # for feeder or dt or pole
    span_from: str | None = None  # for span
    span_to: str | None = None  # for span


class ScenarioFault(BaseModel):
    kind: Literal["feeder", "dt", "span", "pole"]
    target_id: str | None = None
    span_from: str | None = None
    span_to: str | None = None


class ScenarioIn(BaseModel):
    faults: list[ScenarioFault]


class NoiseInjectionIn(BaseModel):
    kind: Literal["dead_sensor", "duplicate", "delayed", "reorder"]
    target_id: str  # pole_id / device_id


def get_redis_client():
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        client.close()


def get_affected_poles(db: Session, data: FaultInjectionIn) -> list[Pole]:
    target_id = data.target_id.strip() if data.target_id else None
    span_from = data.span_from.strip() if data.span_from else None
    span_to = data.span_to.strip() if data.span_to else None
    topo = get_topology()
    if data.kind == "feeder":
        if not target_id:
            raise HTTPException(400, "target_id required for feeder scope")
        return db.scalars(select(Pole).where(Pole.feeder_id == target_id)).all()
    elif data.kind == "dt":
        if not target_id:
            raise HTTPException(400, "target_id required for dt scope")
        return db.scalars(select(Pole).where(Pole.dt_id == target_id)).all()
    elif data.kind == "span":
        if not span_to:
            raise HTTPException(400, "span_to required for span scope")
        pole = db.get(Pole, span_to)
        if not pole:
            raise HTTPException(404, f"Pole {span_to} not found")
        desc_ids = topo.descendants(pole.dt_id, pole.id)
        return db.scalars(select(Pole).where(Pole.id.in_(desc_ids))).all()
    elif data.kind == "pole":
        if not target_id:
            raise HTTPException(400, "target_id required for pole scope")
        pole = db.get(Pole, target_id)
        if not pole:
            raise HTTPException(404, f"Pole {target_id} not found")
        return [pole]
    else:
        raise HTTPException(400, f"Unknown fault kind: {data.kind}")


def next_seq(state: PoleState | None, offset: int = 1) -> int:
    return ((state.last_seq if state else 0) or 0) + offset


def publish_event(
    r: redis.Redis,
    stream: str,
    pole: Pole,
    event: str,
    energized: bool,
    seq: int,
    ts: datetime,
    fw: str,
    battery_mv: int,
    rssi: int,
) -> None:
    payload = {
        "device_id": pole.device_id,
        "pole_id": pole.id,
        "event": event,
        "energized": energized,
        "ts": ts.isoformat(),
        "seq": seq,
        "battery_mv": battery_mv,
        "rssi": rssi,
        "fw": fw,
    }
    r.xadd(stream, {"payload": json.dumps(payload)})


@router.post("/inject", status_code=status.HTTP_202_ACCEPTED)
def inject_fault(
    data: FaultInjectionIn,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    poles = get_affected_poles(db, data)
    affected_count = 0

    now = datetime.now(timezone.utc)

    for p in poles:
        if not p.device_id:
            continue

        state = db.get(PoleState, p.id)
        fw = state.firmware if state else "1.4.2"

        # Telemetry Stream event (skip power_lost for fw 1.2 to simulate heartbeat silence)
        if fw and fw.startswith("1.2"):
            # Omit stream message, simulating silence
            pass
        else:
            publish_event(
                r,
                settings.telemetry_stream,
                p,
                "power_lost",
                False,
                next_seq(state),
                now,
                fw,
                3400,
                -85,
            )

        affected_count += 1

    # Trigger dirty DT flag in Redis for each affected DT
    dt_ids = {p.dt_id for p in poles}
    for dt_id in dt_ids:
        r.set(f"dt_dirty:{dt_id}", time.time())

    return {
        "injected": True,
        "kind": data.kind,
        "target_id": data.target_id or f"{data.span_from}->{data.span_to}",
        "affected_devices": affected_count,
    }


@router.post("/repair", status_code=status.HTTP_202_ACCEPTED)
def repair_fault(
    data: FaultInjectionIn,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    poles = get_affected_poles(db, data)
    affected_count = 0

    now = datetime.now(timezone.utc)

    for p in poles:
        if not p.device_id:
            continue

        state = db.get(PoleState, p.id)
        fw = state.firmware if state else "1.4.2"

        publish_event(
            r,
            settings.telemetry_stream,
            p,
            "boot",
            True,
            next_seq(state),
            now,
            fw,
            3750,
            -72,
        )
        publish_event(
            r,
            settings.telemetry_stream,
            p,
            "power_restored",
            True,
            next_seq(state, 2),
            now + timedelta(milliseconds=100),
            fw,
            3800,
            -70,
        )
        affected_count += 1

    # Trigger dirty flag
    dt_ids = {p.dt_id for p in poles}
    for dt_id in dt_ids:
        r.set(f"dt_dirty:{dt_id}", time.time())

    return {
        "repaired": True,
        "kind": data.kind,
        "target_id": data.target_id or f"{data.span_from}->{data.span_to}",
        "affected_devices": affected_count,
    }


@router.post("/noise", status_code=status.HTTP_202_ACCEPTED)
def inject_noise(
    data: NoiseInjectionIn,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    pole = db.get(Pole, data.target_id)
    if not pole:
        raise HTTPException(404, f"Pole {data.target_id} not found")

    state = db.get(PoleState, pole.id)
    fw = state.firmware if state else "1.4.2"

    if data.kind == "dead_sensor":
        if pole.device_id:
            publish_event(
                r,
                settings.telemetry_stream,
                pole,
                "heartbeat",
                False,
                next_seq(state),
                datetime.now(timezone.utc) - timedelta(seconds=400),
                fw,
                3300,
                -95,
            )
            r.set(f"dt_dirty:{pole.dt_id}", time.time())

        return {"noise_injected": True, "kind": "dead_sensor", "pole_id": pole.id}

    elif data.kind == "duplicate":
        # Send a duplicate heartbeat event to the stream
        payload = {
            "device_id": pole.device_id,
            "pole_id": pole.id,
            "event": "heartbeat",
            "energized": True,
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": state.last_seq if state else 1,
            "battery_mv": 3800,
            "rssi": -75,
            "fw": fw,
        }
        r.xadd(settings.telemetry_stream, {"payload": json.dumps(payload)})
        return {"noise_injected": True, "kind": "duplicate", "pole_id": pole.id}

    elif data.kind == "delayed":
        if pole.device_id:
            publish_event(
                r,
                settings.telemetry_stream,
                pole,
                "heartbeat",
                True,
                next_seq(state),
                datetime.now(timezone.utc) - timedelta(seconds=120),
                fw,
                3700,
                -80,
            )
        return {"noise_injected": True, "kind": "delayed", "pole_id": pole.id}

    elif data.kind == "reorder":
        if pole.device_id:
            now = datetime.now(timezone.utc)
            publish_event(
                r,
                settings.telemetry_stream,
                pole,
                "heartbeat",
                True,
                next_seq(state, 2),
                now,
                fw,
                3800,
                -75,
            )
            publish_event(
                r,
                settings.telemetry_stream,
                pole,
                "heartbeat",
                False,
                next_seq(state),
                now - timedelta(seconds=1),
                fw,
                3400,
                -90,
            )
        return {"noise_injected": True, "kind": "reorder", "pole_id": pole.id}

    else:
        raise HTTPException(400, f"Unsupported noise kind: {data.kind}")


@router.post("/scenario", status_code=status.HTTP_202_ACCEPTED)
def run_scenario(
    data: ScenarioIn,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        if not data.faults:
            raise HTTPException(400, "At least one scenario fault is required")

        total_affected = 0
        now = datetime.now(timezone.utc)
        all_dt_ids = set()
        published_by_pole: dict[str, int] = {}
        payload_for_log = [fault.model_dump() for fault in data.faults]
        log.info("Scenario simulation requested: %s", payload_for_log)

        for fault in data.faults:
            fault_in = FaultInjectionIn(
                kind=fault.kind,
                target_id=fault.target_id.strip() if fault.target_id else None,
                span_from=fault.span_from.strip() if fault.span_from else None,
                span_to=fault.span_to.strip() if fault.span_to else None,
            )
            poles = get_affected_poles(db, fault_in)
            if not poles:
                target = fault_in.target_id or f"{fault_in.span_from}->{fault_in.span_to}"
                raise HTTPException(404, f"No poles found for {fault.kind} fault target {target}")

            for p in poles:
                all_dt_ids.add(p.dt_id)
                if not p.device_id:
                    continue

                state = db.get(PoleState, p.id)
                fw = state.firmware if state else "1.4.2"
                pole_offset = published_by_pole.get(p.id, 0) + 1
                published_by_pole[p.id] = pole_offset

                if fw and fw.startswith("1.2"):
                    pass
                else:
                    publish_event(
                        r,
                        settings.telemetry_stream,
                        p,
                        "power_lost",
                        False,
                        next_seq(state, pole_offset),
                        now,
                        fw,
                        3400,
                        -85,
                    )

                total_affected += 1

        for dt_id in all_dt_ids:
            r.set(f"dt_dirty:{dt_id}", time.time())

        return {"status": "injected", "affected_devices": total_affected, "dts": sorted(all_dt_ids)}
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Scenario simulation failed for payload: %s", data.model_dump())
        raise HTTPException(500, f"Scenario simulation failed: {type(exc).__name__}") from exc
