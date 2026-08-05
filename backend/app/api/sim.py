import json
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status
import redis
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FaultKind, Pole, PoleState, Incident, TicketStatus
from app.services.dt_dirty import mark_dt_dirty
from app.services.localization import check_incident_restorations, run_global_localization
from app.services.topo_index import get_topology
from app.settings import get_settings, Settings

router = APIRouter(prefix="/sim", tags=["simulation"])
log = logging.getLogger(__name__)


def _incident_asset_match(inc: Incident):
    return (
        Incident.kind == inc.kind,
        Incident.feeder_id == inc.feeder_id,
        Incident.dt_id == inc.dt_id,
        Incident.span_from == inc.span_from,
        Incident.span_to == inc.span_to,
    )


class FaultInjectionIn(BaseModel):
    kind: Literal["feeder", "dt", "span", "pole"]
    target_id: str | None = None  # for feeder or dt or pole
    span_from: str | None = None  # for span
    span_to: str | None = None  # for span


def _clear_closed_incidents_for_inject(db: Session, data: FaultInjectionIn) -> None:
    """Remove closed tickets for this scope so inject can raise a fresh detected incident."""
    if data.kind == "dt" and data.target_id:
        stmt = select(Incident).where(
            Incident.dt_id == data.target_id, Incident.status == TicketStatus.closed
        )
    elif data.kind == "feeder" and data.target_id:
        stmt = select(Incident).where(
            Incident.feeder_id == data.target_id, Incident.status == TicketStatus.closed
        )
    elif data.kind == "span" and data.span_to:
        conditions = [
            Incident.kind == FaultKind.span,
            Incident.span_to == data.span_to,
            Incident.status == TicketStatus.closed,
        ]
        if data.span_from:
            conditions.append(Incident.span_from == data.span_from)
        stmt = select(Incident).where(*conditions)
    elif data.kind == "pole" and data.target_id:
        stmt = select(Incident).where(
            Incident.kind == FaultKind.span,
            Incident.span_to == data.target_id,
            Incident.status == TicketStatus.closed,
        )
    else:
        return

    for inc in db.scalars(stmt).all():
        db.delete(inc)


def _closed_incident_exists_for_asset(db: Session, inc: Incident) -> bool:
    return (
        db.scalar(
            select(Incident.id)
            .where(*_incident_asset_match(inc), Incident.status == TicketStatus.closed)
            .limit(1)
        )
        is not None
    )


class ScenarioFault(BaseModel):
    kind: Literal["feeder", "dt", "span", "pole", "noise"]
    target_id: str | None = None
    span_from: str | None = None
    span_to: str | None = None
    noise_kind: Literal["dead_sensor", "duplicate", "delayed", "reorder"] | None = "dead_sensor"


class ScenarioIn(BaseModel):
    faults: list[ScenarioFault]


class NoiseInjectionIn(BaseModel):
    kind: Literal["dead_sensor", "duplicate", "delayed", "reorder"]
    target_id: str  # pole_id / device_id


class ClearNoiseIn(BaseModel):
    target_id: str


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


def _event_payload(
    pole: Pole,
    event: str,
    energized: bool,
    seq: int,
    ts: datetime,
    fw: str,
    battery_mv: int,
    rssi: int,
) -> dict:
    return {
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
    payload = _event_payload(pole, event, energized, seq, ts, fw, battery_mv, rssi)
    r.xadd(stream, {"payload": json.dumps(payload)})


def queue_event(
    pipe: redis.client.Pipeline,
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
    payload = _event_payload(pole, event, energized, seq, ts, fw, battery_mv, rssi)
    pipe.xadd(stream, {"payload": json.dumps(payload)})


def mark_pole_dark(
    db: Session,
    r: redis.Redis,
    stream: str,
    pole: Pole,
    now: datetime,
    *,
    publish: bool = True,
    state: PoleState | None = None,
    pipe: redis.client.Pipeline | None = None,
) -> bool:
    """
    Apply physical outage to one pole.

    Always updates PoleState when a device exists (so the map goes dark immediately).
    Telemetry publish is best-effort / firmware-aware:
    - fw 1.2.x never sends power_lost (silence)
    - ~30% of other devices fail to send the dying message
    """
    if not pole.device_id:
        return False

    if state is None:
        state = db.get(PoleState, pole.id)
    if state is None:
        state = PoleState(pole_id=pole.id, device_id=pole.device_id, firmware="1.4.2")
        db.add(state)
        db.flush()

    fw = state.firmware or "1.4.2"
    seq = next_seq(state)

    state.energized = False
    state.last_event = "power_lost"
    state.last_seq = seq
    state.last_seen_at = now
    state.suspect_sensor = False
    # Outage invalidates prior restore evidence — resolve must wait for new telemetry.
    state.last_boot_seq = None
    state.last_power_restored_seq = None
    state.last_boot_at = None
    state.last_power_restored_at = None

    should_publish = publish
    if fw.startswith("1.2"):
        should_publish = False
    elif random.random() >= 0.70:
        # 30% capacitor / radio failure — no dying packet, but power is still gone
        should_publish = False

    if should_publish:
        if pipe is not None:
            queue_event(pipe, stream, pole, "power_lost", False, seq, now, fw, 3400, -85)
        else:
            publish_event(
                r,
                stream,
                pole,
                "power_lost",
                False,
                seq,
                now,
                fw,
                3400,
                -85,
            )

    return True


@router.post("/inject", status_code=status.HTTP_202_ACCEPTED)
def inject_fault(
    data: FaultInjectionIn,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    poles = get_affected_poles(db, data)
    affected_count = 0

    if not poles:
        return {
            "injected": True,
            "kind": data.kind,
            "target_id": data.target_id or f"{data.span_from}->{data.span_to}",
            "affected_devices": 0,
            "poles_in_scope": 0,
            "unmonitored_poles": 0,
            "warning": "No poles matched this fault scope; check target IDs.",
        }

    _clear_closed_incidents_for_inject(db, data)

    now = datetime.now(timezone.utc)
    
    pole_ids = [p.id for p in poles]
    states = {s.pole_id: s for s in db.scalars(select(PoleState).where(PoleState.pole_id.in_(pole_ids))).all()}

    pipe = r.pipeline()
    for p in poles:
        if mark_pole_dark(
            db, r, settings.telemetry_stream, p, now, state=states.get(p.id), pipe=pipe
        ):
            affected_count += 1

    try:
        pipe.execute()
    except redis.RedisError as e:
        log.warning("Redis pipeline failed during inject (DB state still updated): %s", e)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger(__name__).warning("Concurrency error during sync inject commit, falling back to worker: %s", e)

    dt_ids = {p.dt_id for p in poles}
    for dt_id in dt_ids:
        mark_dt_dirty(r, dt_id)

    try:
        run_global_localization(db)
    except Exception as e:
        log.warning("Sync localization after inject failed (worker will retry): %s", e)

    return {
        "injected": True,
        "kind": data.kind,
        "target_id": data.target_id or f"{data.span_from}->{data.span_to}",
        "affected_devices": affected_count,
        "poles_in_scope": len(poles),
        "unmonitored_poles": len(poles) - affected_count,
        **(
            {"warning": "Scope has poles but none have telemetry devices; map may not change until worker runs."}
            if affected_count == 0 and len(poles) > 0
            else {}
        ),
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

    if not poles:
        return {
            "repaired": True,
            "kind": data.kind,
            "target_id": data.target_id or f"{data.span_from}->{data.span_to}",
            "affected_devices": 0,
        }

    now = datetime.now(timezone.utc)
    
    dt_ids = {p.dt_id for p in poles}

    pole_ids = [p.id for p in poles]
    states = {s.pole_id: s for s in db.scalars(select(PoleState).where(PoleState.pole_id.in_(pole_ids))).all()}

    pipe = r.pipeline()
    for p in poles:
        if not p.device_id:
            continue

        state = states.get(p.id)
        if state is None:
            # Create dummy state if none exists yet, so repair works
            state = PoleState(pole_id=p.id, device_id=p.device_id, firmware="1.4.2")
            db.add(state)

        fw = state.firmware if state else "1.4.2"
        
        b_seq = next_seq(state)
        r_seq = next_seq(state, 2)

        queue_event(
            pipe, settings.telemetry_stream, p, "boot", True, b_seq, now, fw, 3750, -72
        )
        queue_event(
            pipe,
            settings.telemetry_stream,
            p,
            "power_restored",
            True,
            r_seq,
            now + timedelta(milliseconds=100),
            fw,
            3800,
            -70,
        )
        
        # Synchronously update DB for instant demo response
        if state:
            state.energized = True
            state.last_event = "power_restored"
            state.last_seq = r_seq
            state.last_boot_seq = b_seq
            state.last_power_restored_seq = r_seq
            state.last_boot_at = now
            state.last_power_restored_at = now + timedelta(milliseconds=100)
            state.last_seen_at = now + timedelta(milliseconds=100)

        affected_count += 1

    try:
        pipe.execute()
    except redis.RedisError as e:
        log.warning("Redis pipeline failed during repair (DB state still updated): %s", e)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger(__name__).warning("Concurrency error during sync repair commit, falling back to worker: %s", e)
    else:
        check_incident_restorations(db)

    # Trigger dirty flag
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
    return _apply_noise(db, r, settings, data)


def _apply_noise(
    db: Session,
    r: redis.Redis,
    settings: Settings,
    data: NoiseInjectionIn,
) -> dict:
    pole = db.get(Pole, data.target_id)
    if not pole:
        raise HTTPException(404, f"Pole {data.target_id} not found")

    state = db.get(PoleState, pole.id)
    fw = state.firmware if state else "1.4.2"
    now = datetime.now(timezone.utc)

    if data.kind == "dead_sensor":
        if pole.device_id:
            if state is None:
                state = PoleState(pole_id=pole.id, device_id=pole.device_id, firmware=fw)
                db.add(state)
            current_energized = state.energized if state.energized is not None else True
            state.suspect_sensor = True
            state.last_seen_at = now - timedelta(seconds=400)
            state.energized = current_energized
            state.last_event = "heartbeat"
            seq = next_seq(state)
            state.last_seq = seq
            db.flush()
            publish_event(
                r,
                settings.telemetry_stream,
                pole,
                "heartbeat",
                current_energized,
                seq,
                state.last_seen_at,
                fw,
                3300,
                -95,
            )
            r.set(f"dt_dirty:{pole.dt_id}", time.time())
            db.commit()

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


@router.post("/clear_noise", status_code=status.HTTP_202_ACCEPTED)
def clear_noise(
    data: ClearNoiseIn,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    pole = db.get(Pole, data.target_id)
    if not pole:
        raise HTTPException(404, f"Pole {data.target_id} not found")

    state = db.get(PoleState, pole.id)
    fw = state.firmware if state else "1.4.2"
    now = datetime.now(timezone.utc)

    if pole.device_id:
        seq = next_seq(state)
        publish_event(
            r,
            settings.telemetry_stream,
            pole,
            "heartbeat",
            True,
            seq,
            now,
            fw,
            3800,
            -70,
        )
        if state is None:
            state = PoleState(pole_id=pole.id, device_id=pole.device_id, firmware=fw)
            db.add(state)
        state.suspect_sensor = False
        state.energized = True
        state.last_event = "heartbeat"
        state.last_seen_at = now
        state.last_seq = seq
        db.commit()
        r.set(f"dt_dirty:{pole.dt_id}", time.time())
    else:
        db.commit()

    return {"noise_cleared": True, "target_id": pole.id}


@router.post("/demo/purge_closed_incidents", status_code=status.HTTP_200_OK)
def purge_closed_incidents(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.allow_demo_admin:
        raise HTTPException(status_code=403, detail="Demo admin endpoints are disabled")
    result = db.execute(delete(Incident).where(Incident.status == TicketStatus.closed))
    db.commit()
    return {"purged": result.rowcount or 0}


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
        payload_for_log = [fault.model_dump() for fault in data.faults]
        log.info("Scenario simulation requested: %s", payload_for_log)

        pipe = r.pipeline()
        outcomes: list[dict] = []
        for fault in data.faults:
            if fault.kind == "noise":
                pole_id = fault.target_id.strip() if fault.target_id else None
                if not pole_id:
                    outcomes.append(
                        {"kind": "noise", "ok": False, "error": "target_id required for noise"}
                    )
                    continue
                try:
                    nk = fault.noise_kind or "dead_sensor"
                    _apply_noise(
                        db,
                        r,
                        settings,
                        NoiseInjectionIn(kind=nk, target_id=pole_id),
                    )
                    outcomes.append(
                        {"kind": "noise", "ok": True, "target_id": pole_id, "noise_kind": nk}
                    )
                except HTTPException as exc:
                    outcomes.append(
                        {
                            "kind": "noise",
                            "ok": False,
                            "target_id": pole_id,
                            "error": str(exc.detail),
                        }
                    )
                continue

            fault_in = FaultInjectionIn(
                kind=fault.kind,
                target_id=fault.target_id.strip() if fault.target_id else None,
                span_from=fault.span_from.strip() if fault.span_from else None,
                span_to=fault.span_to.strip() if fault.span_to else None,
            )
            try:
                poles = get_affected_poles(db, fault_in)
            except HTTPException as exc:
                outcomes.append(
                    {
                        "kind": fault.kind,
                        "ok": False,
                        "target": fault_in.target_id
                        or f"{fault_in.span_from}->{fault_in.span_to}",
                        "error": str(exc.detail),
                    }
                )
                continue

            if not poles:
                target = fault_in.target_id or f"{fault_in.span_from}->{fault_in.span_to}"
                outcomes.append(
                    {"kind": fault.kind, "ok": False, "target": target, "error": "no poles in scope"}
                )
                continue

            _clear_closed_incidents_for_inject(db, fault_in)

            pole_ids = [p.id for p in poles]
            states = {
                s.pole_id: s
                for s in db.scalars(
                    select(PoleState).where(PoleState.pole_id.in_(pole_ids))
                ).all()
            }

            fault_affected = 0
            for p in poles:
                all_dt_ids.add(p.dt_id)
                if mark_pole_dark(
                    db,
                    r,
                    settings.telemetry_stream,
                    p,
                    now,
                    state=states.get(p.id),
                    pipe=pipe,
                ):
                    fault_affected += 1
                    total_affected += 1

            outcomes.append(
                {
                    "kind": fault.kind,
                    "ok": True,
                    "target": fault_in.target_id
                    or f"{fault_in.span_from}->{fault_in.span_to}",
                    "affected_devices": fault_affected,
                }
            )

        if not any(item.get("ok") for item in outcomes):
            raise HTTPException(
                status_code=400,
                detail={"message": "No scenario faults could be applied", "results": outcomes},
            )

        try:
            pipe.execute()
        except redis.RedisError as e:
            log.warning("Redis pipeline failed during scenario inject: %s", e)

        db.commit()

        for dt_id in all_dt_ids:
            mark_dt_dirty(r, dt_id)

        try:
            run_global_localization(db)
        except Exception as e:
            log.warning("Sync localization after scenario failed (worker will retry): %s", e)

        status = "injected" if all(item.get("ok") for item in outcomes) else "partial"
        return {
            "status": status,
            "affected_devices": total_affected,
            "dts": sorted(all_dt_ids),
            "results": outcomes,
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Scenario simulation failed for payload: %s", data.model_dump())
        raise HTTPException(500, f"Scenario simulation failed: {type(exc).__name__}") from exc
