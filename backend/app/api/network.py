from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DistributionTransformer, Pole, PoleState, ProcessedEvent, TopologySource
from app.services.topo_index import get_topology

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/summary")
def network_summary(db: Session = Depends(get_db)) -> dict:
    poles = db.scalar(select(func.count()).select_from(Pole)) or 0
    dts = db.scalar(select(func.count()).select_from(DistributionTransformer)) or 0
    devices = db.scalar(select(func.count()).select_from(PoleState)) or 0
    active_devices = db.scalar(
        select(func.count())
        .select_from(PoleState)
        .where(PoleState.last_seen_at.is_not(None))
    ) or 0
    latest_seen = db.scalar(select(func.max(PoleState.last_seen_at)))
    now = datetime.now(timezone.utc)
    if latest_seen and latest_seen.tzinfo is None:
        latest_seen = latest_seen.replace(tzinfo=timezone.utc)
    heartbeat_freshness_sec = int((now - latest_seen).total_seconds()) if latest_seen else None
    one_minute_ago = now - timedelta(minutes=1)
    if db.bind.dialect.name == "sqlite":
        one_minute_ago = one_minute_ago.replace(tzinfo=None)
    processed_events = db.scalar(select(func.count()).select_from(ProcessedEvent)) or 0
    ingestion_rate_per_min = db.scalar(
        select(func.count())
        .select_from(ProcessedEvent)
        .where(ProcessedEvent.received_at >= one_minute_ago)
    ) or 0
    known = (
        db.scalar(
            select(func.count())
            .select_from(DistributionTransformer)
            .where(DistributionTransformer.wiring_known.is_(True))
        )
        or 0
    )
    inferred_poles = (
        db.scalar(
            select(func.count()).select_from(Pole).where(Pole.topology_source == TopologySource.inferred)
        )
        or 0
    )
    topo = get_topology()
    return {
        "poles": poles,
        "dts": dts,
        "devices": devices,
        "active_devices": active_devices,
        "heartbeat_freshness_sec": heartbeat_freshness_sec,
        "ingestion_rate_per_min": ingestion_rate_per_min,
        "processed_events": processed_events,
        "processing_latency_ms": heartbeat_freshness_sec * 1000 if heartbeat_freshness_sec is not None else None,
        "wiring_known_dts": known,
        "wiring_unknown_dts": dts - known,
        "inferred_poles": inferred_poles,
        "topo_cached_dts": len(topo.by_dt),
    }


@router.get("/dts")
def list_dts(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(DistributionTransformer).order_by(DistributionTransformer.id)).all()
    pole_counts = dict(
        db.execute(
            select(Pole.dt_id, func.count())
            .where(Pole.dt_id.is_not(None))
            .group_by(Pole.dt_id)
        ).all()
    )
    dark_counts = dict(
        db.execute(
            select(Pole.dt_id, func.count())
            .select_from(PoleState)
            .join(Pole, Pole.id == PoleState.pole_id)
            .where(PoleState.energized.is_(False))
            .group_by(Pole.dt_id)
        ).all()
    )
    return [
        {
            "dt_id": dt.id,
            "feeder_id": dt.feeder_id,
            "lat": dt.lat,
            "lon": dt.lon,
            "households": dt.households,
            "wiring_known": dt.wiring_known,
            "pole_count": pole_counts.get(dt.id, 0),
            "dark_poles": dark_counts.get(dt.id, 0),
        }
        for dt in rows
    ]



@router.get("/dts/{dt_id}")
def dt_detail(dt_id: str, db: Session = Depends(get_db)) -> dict:
    dt = db.get(DistributionTransformer, dt_id)
    if not dt:
        raise HTTPException(404, f"unknown dt {dt_id}")

    poles = db.scalars(select(Pole).where(Pole.dt_id == dt_id).order_by(Pole.id)).all()
    states = {
        s.pole_id: s
        for s in db.scalars(
            select(PoleState).where(PoleState.pole_id.in_([p.id for p in poles]))
        ).all()
    }

    return {
        "dt_id": dt.id,
        "feeder_id": dt.feeder_id,
        "lat": dt.lat,
        "lon": dt.lon,
        "wiring_known": dt.wiring_known,
        "poles": [
            {
                "pole_id": p.id,
                "lat": p.lat,
                "lon": p.lon,
                "parent_id": p.parent_id,
                "true_parent_id": p.true_parent_id,
                "seq_on_line": p.seq_on_line,
                "pincode": p.pincode,
                "device_id": p.device_id,
                "topology_source": p.topology_source.value,
                "energized": states[p.id].energized if p.id in states else None,
                "status": "suspect_sensor" if p.id in states and states[p.id].suspect_sensor else ("offline" if p.id in states and states[p.id].energized is False else "healthy"),
                "suspect_sensor": states[p.id].suspect_sensor if p.id in states else False,
                "battery_mv": states[p.id].battery_mv if p.id in states else None,
                "firmware": states[p.id].firmware if p.id in states else None,
                "last_event": states[p.id].last_event if p.id in states else None,
                "last_seen_at": states[p.id].last_seen_at.isoformat() if p.id in states and states[p.id].last_seen_at else None,
                "last_power_restored_seq": states[p.id].last_power_restored_seq if p.id in states else None,
                "last_boot_seq": states[p.id].last_boot_seq if p.id in states else None,
            }
            for p in poles
        ],
    }
