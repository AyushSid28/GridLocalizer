from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DistributionTransformer, Pole, PoleState
from app.services.topo_index import get_topology

router = APIRouter(prefix="/breadcrumb", tags=["breadcrumb"])


@router.get("/dt/{dt_id}")
def get_dt_breadcrumb(dt_id: str, db: Session = Depends(get_db)):
    """Hierarchy chip for a DT: subdivision › feeder › DT, plus live dark count."""
    dt = db.get(DistributionTransformer, dt_id)
    if not dt:
        raise HTTPException(status_code=404, detail="Transformer not found")

    feeder_bits = dt.feeder_id.split("-")
    substation_id = f"SD-{feeder_bits[1]}" if len(feeder_bits) >= 2 else "SD-07"

    topo = get_topology()
    tree = topo.by_dt.get(dt_id)
    pole_count = len(tree.pole_ids) if tree else 0

    dark_now = (
        db.scalar(
            select(func.count())
            .select_from(PoleState)
            .join(Pole, Pole.id == PoleState.pole_id)
            .where(Pole.dt_id == dt_id, PoleState.energized.is_(False))
        )
        or 0
    )

    return {
        "substation_id": substation_id,
        "feeder_id": dt.feeder_id,
        "dt_id": dt_id,
        "pole_count": pole_count,
        "affected_poles": dark_now,
    }
