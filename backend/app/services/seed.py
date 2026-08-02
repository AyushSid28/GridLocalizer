"""Load synthetic network into Postgres when the DB is empty."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    DistributionTransformer,
    Feeder,
    Pole,
    PoleState,
    ScheduledOutage,
    TopologySource,
)
from app.services.network_gen import generate_network

log = logging.getLogger("seed")


def _already_seeded(db: Session) -> bool:
    count = db.scalar(select(func.count()).select_from(Pole)) or 0
    return count > 0


def seed_network(db: Session, seed: int = 7) -> dict:
    if _already_seeded(db):
        n = db.scalar(select(func.count()).select_from(Pole)) or 0
        log.info("seed skipped — %s poles already present", n)
        return {"seeded": False, "poles": n}

    bp = generate_network(seed=seed)

    for f in bp.feeders:
        db.add(Feeder(id=f.feeder_id, name=f.name))
    db.flush()  # feeders must exist before DTs reference them

    for d in bp.dts:
        db.add(
            DistributionTransformer(
                id=d.dt_id,
                feeder_id=d.feeder_id,
                lat=d.lat,
                lon=d.lon,
                capacity_kva=d.capacity_kva,
                households=d.households,
                wiring_known=d.wiring_known,
            )
        )
    db.flush()  # DTs must exist before poles reference them

    for p in bp.poles:
        db.add(
            Pole(
                id=p.pole_id,
                lat=p.lat,
                lon=p.lon,
                feeder_id=p.feeder_id,
                dt_id=p.dt_id,
                parent_id=p.parent_id,
                true_parent_id=p.true_parent_id,
                seq_on_line=p.seq_on_line,
                ward=p.ward,
                pincode=p.pincode,
                device_id=p.device_id,
                topology_source=TopologySource(p.topology_source),
            )
        )
        if p.device_id:
            db.add(
                PoleState(
                    pole_id=p.pole_id,
                    device_id=p.device_id,
                    firmware=p.firmware,
                    energized=True,
                    last_seq=0,
                    last_event="heartbeat",
                    last_seen_at=datetime.now(timezone.utc),
                    battery_mv=3800,
                    rssi=-75,
                    suspect_sensor=False,
                )
            )

    # A couple of sample schedules so P4 has data to lean on.
    now = datetime.now(timezone.utc)
    sample_dt = bp.dts[0].dt_id
    sample_feeder = bp.feeders[0].feeder_id
    db.add_all(
        [
            ScheduledOutage(
                id="SO-SEED-DT",
                scope="dt",
                target_id=sample_dt,
                starts_at=now + timedelta(hours=6),
                ends_at=now + timedelta(hours=8),
                reason="Load shedding",
            ),
            ScheduledOutage(
                id="SO-SEED-FEEDER",
                scope="feeder",
                target_id=sample_feeder,
                starts_at=now + timedelta(days=1),
                ends_at=now + timedelta(days=1, hours=2),
                reason="Planned maintenance - jumper replacement",
            ),
        ]
    )

    db.commit()

    with_device = sum(1 for p in bp.poles if p.device_id)
    known = sum(1 for d in bp.dts if d.wiring_known)
    summary = {
        "seeded": True,
        "feeders": len(bp.feeders),
        "dts": len(bp.dts),
        "poles": len(bp.poles),
        "devices": with_device,
        "wiring_known_dts": known,
        "wiring_unknown_dts": len(bp.dts) - known,
    }
    log.info("seed complete: %s", summary)
    return summary


def ensure_seed(db: Session) -> dict:
    return seed_network(db)
