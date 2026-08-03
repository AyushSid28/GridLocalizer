from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db
from app.services.topo_index import get_topology
from app.models import DistributionTransformer, Incident, TicketStatus, FaultKind

router = APIRouter(prefix="/breadcrumb", tags=["breadcrumb"])

@router.get("/dt/{dt_id}")
def get_dt_breadcrumb(dt_id: str, db: Session = Depends(get_db)):
    """Return hierarchical context for a Distribution Transformer.
    Includes substation ID (derived from DT ID prefix), feeder ID, DT ID,
    total pole count, and affected pole count (based on active incident).
    """
    dt = db.get(DistributionTransformer, dt_id)
    if not dt:
        raise HTTPException(status_code=404, detail="Transformer not found")
    # Derive substation ID from DT ID prefix before '-'
    substation_id = dt_id.split('-')[0] if '-' in dt_id else dt_id
    topo = get_topology()
    tree = topo.by_dt.get(dt_id)
    pole_count = len(tree.pole_ids) if tree else 0
    # Determine affected poles from any active DT incident
    active_inc = db.scalar(
        select(Incident)
        .where(
            Incident.dt_id == dt_id,
            Incident.kind == FaultKind.dt,
            Incident.status.in_([TicketStatus.detected, TicketStatus.acknowledged, TicketStatus.crew_assigned, TicketStatus.resolved])
        )
        .limit(1)
    )
    affected = active_inc.affected_poles if active_inc else 0
    return {
        "substation_id": substation_id,
        "feeder_id": dt.feeder_id,
        "dt_id": dt_id,
        "pole_count": pole_count,
        "affected_poles": affected,
    }
