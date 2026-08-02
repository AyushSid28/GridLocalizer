from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DistributionTransformer, Pole, PoleState, TopologySource
from app.services.topo_index import get_topology

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/summary")
def network_summary(db: Session = Depends(get_db)) -> dict:
    poles = db.scalar(select(func.count()).select_from(Pole)) or 0
    dts = db.scalar(select(func.count()).select_from(DistributionTransformer)) or 0
    devices = db.scalar(select(func.count()).select_from(PoleState)) or 0
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
        "wiring_known_dts": known,
        "wiring_unknown_dts": dts - known,
        "inferred_poles": inferred_poles,
        "topo_cached_dts": len(topo.by_dt),
    }


@router.get("/dts")
def list_dts(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(DistributionTransformer).order_by(DistributionTransformer.id)).all()
    out = []
    for dt in rows:
        n = db.scalar(select(func.count()).select_from(Pole).where(Pole.dt_id == dt.id)) or 0
        out.append(
            {
                "dt_id": dt.id,
                "feeder_id": dt.feeder_id,
                "lat": dt.lat,
                "lon": dt.lon,
                "households": dt.households,
                "wiring_known": dt.wiring_known,
                "pole_count": n,
            }
        )
    return out


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
                "firmware": states[p.id].firmware if p.id in states else None,
            }
            for p in poles
        ],
    }
