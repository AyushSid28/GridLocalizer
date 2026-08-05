import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import (
    DistributionTransformer,
    FaultKind,
    Incident,
    Pole,
    PoleState,
    ScheduledOutage,
    TicketStatus,
)
from app.services.topo_index import get_topology


def get_nearest_pincode(db: Session, lat: float, lon: float) -> str | None:
    """Find the nearest pole with a non-null pincode and return it."""
    # SQLite / Postgres compatible query to find closest pole with pincode
    stmt = (
        select(Pole.pincode)
        .where(Pole.pincode.is_not(None))
        .order_by(
            (Pole.lat - lat) * (Pole.lat - lat) + (Pole.lon - lon) * (Pole.lon - lon)
        )
        .limit(1)
    )
    return db.scalar(stmt)


def calculate_confidence_breakdown(
    db: Session,
    kind: FaultKind,
    dt_id: str | None,
    feeder_id: str | None,
    span_from: str | None,
    span_to: str | None,
    affected_poles_count: int,
    wiring_known: bool
) -> tuple[float, dict]:
    """Calculate deterministic confidence and generate evidence explanation breakdown."""
    positive = []
    negative = []
    
    # Base confidence based on topology registry
    if wiring_known:
        base_conf = 0.90
        positive.append("Topology information available")
    else:
        base_conf = 0.60
        negative.append("Partial topology / geo-inferred registry wiring")

    confidence = base_conf

    # Positive & Negative factors based on fault kind
    if kind == FaultKind.feeder:
        confidence = 0.98
        positive.append("High confidence feeder-level outage")
        positive.append(f"Substation telemetry shows feeder {feeder_id} is dead")
        if affected_poles_count > 50:
            positive.append("Corroborated by high volume of offline devices")
    
    elif kind == FaultKind.dt:
        confidence = 0.95 if wiring_known else 0.70
        positive.append(f"All active reporting sensors under DT {dt_id} are offline/dark")
        
        # Check for missing/offline sensors
        poles = db.scalars(select(Pole).where(Pole.dt_id == dt_id)).all()
        poles_with_no_device = [p for p in poles if not p.device_id]
        if poles_with_no_device:
            negative.append(f"{len(poles_with_no_device)} poles lack monitoring modems")
            confidence -= 0.05
            
        suspect_count = db.scalar(
            select(func.count())
            .select_from(PoleState)
            .join(Pole, Pole.id == PoleState.pole_id)
            .where(Pole.dt_id == dt_id, PoleState.suspect_sensor == True)
        ) or 0
        if suspect_count > 0:
            negative.append(f"{suspect_count} suspect sensors ignored in subtree")
            confidence -= 0.05
            
    elif kind == FaultKind.span:
        confidence = 0.90 if wiring_known else 0.60
        
        if span_from:
            parent_state = db.get(PoleState, span_from)
            if parent_state and parent_state.energized:
                positive.append("Parent pole active / energized")
            else:
                confidence -= 0.10
        else:
            positive.append("Parent node (Transformer) active / energized")
            
        if affected_poles_count > 1:
            positive.append(f"{affected_poles_count} downstream poles confirmed dark")
            
        # Downstream check
        topo = get_topology()
        desc_ids = topo.descendants(dt_id, span_to) if span_to else []
        desc_poles = db.scalars(select(Pole).where(Pole.id.in_(desc_ids))).all()
        
        poles_with_no_device = [p for p in desc_poles if not p.device_id]
        if poles_with_no_device:
            negative.append(f"{len(poles_with_no_device)} downstream poles lack sensors")
            confidence -= 0.05
            
        suspect_count = db.scalar(
            select(func.count())
            .select_from(PoleState)
            .where(PoleState.pole_id.in_(desc_ids), PoleState.suspect_sensor == True)
        ) or 0
        if suspect_count > 0:
            negative.append(f"{suspect_count} suspect sensors in downstream path")
            confidence -= 0.05

    confidence = max(0.10, min(0.99, confidence))
    
    return round(confidence, 2), {"positive": positive, "negative": negative}



def is_suppressed_by_schedule(db: Session, feeder_id: str | None, dt_id: str | None) -> bool:
    """Check if there is an active scheduled outage covering the given feeder or DT at the current time."""
    now = datetime.now(timezone.utc)
    if db.bind.dialect.name == "sqlite":
        now = now.replace(tzinfo=None)

    # Check Feeder level scheduled outages
    if feeder_id:
        stmt = select(ScheduledOutage).where(
            ScheduledOutage.scope == "feeder",
            ScheduledOutage.target_id == feeder_id,
            ScheduledOutage.starts_at <= now,
            ScheduledOutage.ends_at >= now
        )
        if db.scalar(stmt.limit(1)):
            return True

    # Check DT level scheduled outages
    if dt_id:
        stmt = select(ScheduledOutage).where(
            ScheduledOutage.scope == "dt",
            ScheduledOutage.target_id == dt_id,
            ScheduledOutage.starts_at <= now,
            ScheduledOutage.ends_at >= now
        )
        if db.scalar(stmt.limit(1)):
            return True

    return False





def run_localization_for_dt(db: Session, dt_id: str, states_cache: dict[str, PoleState] | None = None) -> list[Incident]:
    """Analyze the states of all poles under a DT and create/update Incidents."""
    topo = get_topology()
    tree = topo.by_dt.get(dt_id)
    if not tree:
        return []

    # Get states of all poles under this DT
    if states_cache is not None:
        states = {p_id: states_cache[p_id] for p_id in tree.pole_ids if p_id in states_cache}
    else:
        stmt = select(PoleState).where(PoleState.pole_id.in_(tree.pole_ids))
        states = {ps.pole_id: ps for ps in db.scalars(stmt).all()}

    # Helper: get current status of a pole
    # Returns: "live", "dark", or "unknown" (no device or no state recorded)
    def get_status(p_id: str) -> str:
        state = states.get(p_id)
        if not state or state.energized is None:
            return "unknown"
        return "live" if state.energized else "dark"

    # Identify isolated offline/dead sensors (no heartbeat/silence for > 300 seconds)
    now = datetime.now(timezone.utc)
    reporting_poles = [p_id for p_id in tree.pole_ids if get_status(p_id) != "unknown"]
    
    # Calculate how many are silent
    silent_poles = set()
    for pole_id in reporting_poles:
        state = states.get(pole_id)
        if state and state.last_seen_at:
            last_seen = state.last_seen_at.replace(tzinfo=timezone.utc) if state.last_seen_at.tzinfo is None else state.last_seen_at
            # If silence duration is > 300 seconds, and it is isolated
            if (now - last_seen).total_seconds() > 300:
                silent_poles.add(pole_id)

    # If some are silent but NOT all, treat the silent ones as suspect_sensors (dead sensors)
    suspect_sensors = set()
    if 0 < len(silent_poles) < len(reporting_poles):
        for pole_id in silent_poles:
            suspect_sensors.add(pole_id)
            state = states.get(pole_id)
            if state and not state.suspect_sensor:
                state.suspect_sensor = True

    # 1. Identify sensor failures (dark parent, live child/descendant)
    # We walk the tree and check if any descendant of a dark pole is live.
    for pole_id in tree.pole_ids:
        if get_status(pole_id) == "dark":
            # Check if any descendant is live
            descendants = topo.descendants(dt_id, pole_id)
            # Exclude the pole itself
            descendants.remove(pole_id)
            if any(get_status(desc) == "live" for desc in descendants):
                suspect_sensors.add(pole_id)
                # Mark suspect sensor in DB
                state = states.get(pole_id)
                if state and not state.suspect_sensor:
                    state.suspect_sensor = True

    # Save any suspect sensor flags
    if suspect_sensors:
        db.commit()

    # Effective liveness: suspect sensors are treated as "live" for localization purposes
    def get_effective_status(p_id: str) -> str:
        if p_id in suspect_sensors:
            return "live"
        return get_status(p_id)

    # 2. Check if the entire DT is dark
    # Total device-equipped poles (excluding suspect sensors)
    active_reporting_poles = [
        p_id for p_id in tree.pole_ids
        if get_status(p_id) != "unknown" and p_id not in suspect_sensors
    ]
    
    if active_reporting_poles and all(get_effective_status(p_id) == "dark" for p_id in active_reporting_poles):
        # Entire DT is dark! We will create a DT-level fault.
        dt_record = db.get(DistributionTransformer, dt_id)
        pincode = get_nearest_pincode(db, dt_record.lat, dt_record.lon) if dt_record else None
        
        confidence, evidence = calculate_confidence_breakdown(
            db=db,
            kind=FaultKind.dt,
            dt_id=dt_id,
            feeder_id=tree.feeder_id,
            span_from=None,
            span_to=None,
            affected_poles_count=len(tree.pole_ids),
            wiring_known=tree.wiring_known
        )
        
        inc = Incident(
            id=str(uuid.uuid4()),
            kind=FaultKind.dt,
            status=TicketStatus.detected,
            feeder_id=tree.feeder_id,
            dt_id=dt_id,
            lat=dt_record.lat if dt_record else None,
            lon=dt_record.lon if dt_record else None,
            pincode=pincode,
            affected_poles=len(tree.pole_ids),
            confidence=confidence,
            evidence=evidence,
            reasons=[
                f"All {len(active_reporting_poles)} trusted reporting poles under DT {dt_id} are dark.",
                f"Wiring topology is {'recorded' if tree.wiring_known else 'geo-inferred'}."
            ],
            topology_mode="recorded" if tree.wiring_known else "inferred",
        )
        return [inc]

    # 3. Find frontiers: parent is live (or None/DT itself), child is dark (effectively)
    frontiers: list[tuple[str | None, str]] = []
    
    # We walk the children starting from the DT (parent None)
    queue: list[str | None] = [None]
    visited = set()
    
    while queue:
        parent = queue.pop(0)
        children = tree.children.get(parent, [])
        for child in children:
            if child in visited:
                continue
            visited.add(child)
            
            p_status = "live" if parent is None else get_effective_status(parent)
            c_status = get_effective_status(child)
            
            if p_status == "live" and c_status == "dark":
                # Found a frontier!
                frontiers.append((parent, child))
            else:
                # Continue walking down the tree
                queue.append(child)

    incidents = []
    for parent, child in frontiers:
        # All dark descendants under this frontier
        descendants = topo.descendants(dt_id, child)
        dark_affected = [d for d in descendants if get_effective_status(d) == "dark"]
        
        # Calculate location
        child_pole = db.get(Pole, child)
        lat, lon = child_pole.lat, child_pole.lon
        if parent:
            parent_pole = db.get(Pole, parent)
            if parent_pole:
                lat = (parent_pole.lat + child_pole.lat) / 2.0
                lon = (parent_pole.lon + child_pole.lon) / 2.0

        pincode = child_pole.pincode or get_nearest_pincode(db, lat, lon)
        
        # Determine confidence
        confidence, evidence = calculate_confidence_breakdown(
            db=db,
            kind=FaultKind.span,
            dt_id=dt_id,
            feeder_id=tree.feeder_id,
            span_from=parent,
            span_to=child,
            affected_poles_count=len(descendants),
            wiring_known=tree.wiring_known
        )
        reasons = [
            f"Frontier detected at span {parent or 'DT'} -> {child}.",
            f"{len(dark_affected)} trusted downstream reporting poles are dark.",
            f"Topology source: {'recorded' if tree.wiring_known else 'inferred'}."
        ]
        if not tree.wiring_known:
            reasons.append("Low confidence due to missing/inferred registry wiring.")

        inc = Incident(
            id=str(uuid.uuid4()),
            kind=FaultKind.span,
            status=TicketStatus.detected,
            feeder_id=tree.feeder_id,
            dt_id=dt_id,
            span_from=parent,
            span_to=child,
            lat=lat,
            lon=lon,
            pincode=pincode,
            affected_poles=len(descendants),
            confidence=confidence,
            evidence=evidence,
            reasons=reasons,
            topology_mode="recorded" if tree.wiring_known else "inferred",
        )
        incidents.append(inc)

    return incidents


def _incident_asset_key(inc: Incident) -> tuple:
    return (inc.kind, inc.feeder_id, inc.dt_id, inc.span_from, inc.span_to)


def _refresh_detected_fields(target: Incident, source: Incident) -> None:
    target.affected_poles = source.affected_poles
    target.confidence = source.confidence
    target.evidence = source.evidence
    target.reasons = source.reasons
    target.lat = source.lat
    target.lon = source.lon
    target.pincode = source.pincode
    target.topology_mode = source.topology_mode
    target.summary = source.summary
    target.feeder_id = source.feeder_id
    target.dt_id = source.dt_id
    target.span_from = source.span_from
    target.span_to = source.span_to


def _persist_detected_incidents(db: Session, final_incidents: list[Incident]) -> None:
    """Upsert detected tickets by asset key so polling does not churn incident IDs."""
    final_keys = {_incident_asset_key(inc) for inc in final_incidents}
    existing_detected = list(
        db.scalars(select(Incident).where(Incident.status == TicketStatus.detected)).all()
    )
    existing_by_key = {_incident_asset_key(row): row for row in existing_detected}

    for inc in final_incidents:
        key = _incident_asset_key(inc)
        existing = existing_by_key.get(key)
        if existing:
            _refresh_detected_fields(existing, inc)
        else:
            db.add(inc)

    for key, row in existing_by_key.items():
        if key not in final_keys:
            db.delete(row)


def run_global_localization(db: Session) -> list[Incident]:
    """
    Run fault localization across the entire grid.
    Returns the list of final detected incidents (uncommitted to DB yet, but objects are updated).
    """
    topo = get_topology()
    all_dt_incidents = {}
    feeder_to_dts = {}
    
    # Pre-fetch all PoleStates to avoid N+1 queries during DT-level localization
    all_states_cache = {s.pole_id: s for s in db.scalars(select(PoleState)).all()}

    # 1. Gather DT-level & Span-level incidents
    for dt_id in topo.by_dt.keys():
        incidents = run_localization_for_dt(db, dt_id, states_cache=all_states_cache)
        if incidents:
            all_dt_incidents[dt_id] = incidents

    # 2. Check for Feeder-level faults
    feeder_to_dts: dict[str, list[str]] = {}
    for dt_id, tree in topo.by_dt.items():
        feeder_to_dts.setdefault(tree.feeder_id, []).append(dt_id)

    final_incidents: list[Incident] = []
    covered_dts = set()

    # Load active feeder outages to cover downstream DTs
    active_feeders_stmt = select(Incident.feeder_id).where(
        Incident.kind == FaultKind.feeder,
        Incident.status.in_([TicketStatus.acknowledged, TicketStatus.crew_assigned, TicketStatus.resolved])
    )
    active_feeder_ids = db.scalars(active_feeders_stmt).all()
    for f_id in active_feeder_ids:
        for dt_id, tree in topo.by_dt.items():
            if tree.feeder_id == f_id:
                covered_dts.add(dt_id)

    for feeder_id, dt_ids in feeder_to_dts.items():
        reporting_dt_ids = []
        for dt_id in dt_ids:
            tree = topo.by_dt[dt_id]
            if db.scalar(select(PoleState.pole_id).where(PoleState.pole_id.in_(tree.pole_ids)).limit(1)):
                reporting_dt_ids.append(dt_id)

        if reporting_dt_ids and all(
            any(inc.kind == FaultKind.dt for inc in all_dt_incidents.get(d_id, []))
            for d_id in reporting_dt_ids
        ):
            # Feeder fault!
            if is_suppressed_by_schedule(db, feeder_id, None):
                for d_id in dt_ids:
                    covered_dts.add(d_id)
                continue

            lats = []
            lons = []
            for d_id in reporting_dt_ids:
                dt_rec = db.get(DistributionTransformer, d_id)
                if dt_rec:
                    lats.append(dt_rec.lat)
                    lons.append(dt_rec.lon)
            
            avg_lat = sum(lats) / len(lats) if lats else None
            avg_lon = sum(lons) / len(lons) if lons else None
            pincode = get_nearest_pincode(db, avg_lat, avg_lon) if avg_lat is not None else None

            total_poles = sum(len(topo.by_dt[d_id].pole_ids) for d_id in dt_ids)

            confidence, evidence = calculate_confidence_breakdown(
                db=db,
                kind=FaultKind.feeder,
                dt_id=None,
                feeder_id=feeder_id,
                span_from=None,
                span_to=None,
                affected_poles_count=total_poles,
                wiring_known=True
            )

            feeder_inc = Incident(
                id=str(uuid.uuid4()),
                kind=FaultKind.feeder,
                status=TicketStatus.detected,
                feeder_id=feeder_id,
                lat=avg_lat,
                lon=avg_lon,
                pincode=pincode,
                affected_poles=total_poles,
                confidence=confidence,
                evidence=evidence,
                reasons=[
                    f"All {len(reporting_dt_ids)} reporting DTs on feeder {feeder_id} are entirely dark.",
                    "High confidence feeder-level outage."
                ],
                topology_mode="recorded",
            )
            
            # Check if active feeder incident exists
            active_exists = db.scalar(
                select(Incident.id).where(
                    Incident.feeder_id == feeder_id,
                    Incident.kind == FaultKind.feeder,
                    Incident.status.in_([TicketStatus.acknowledged, TicketStatus.crew_assigned, TicketStatus.resolved])
                ).limit(1)
            )
            if not active_exists:
                final_incidents.append(feeder_inc)
                
            for d_id in dt_ids:
                covered_dts.add(d_id)

    # 3. Add all DT/span incidents not covered by feeder faults (checking for schedule suppression)
    for dt_id, incidents in all_dt_incidents.items():
        if dt_id not in covered_dts:
            for inc in incidents:
                if not is_suppressed_by_schedule(db, inc.feeder_id, inc.dt_id):
                    # Check if an active incident for the same asset exists
                    active_exists = db.scalar(
                        select(Incident.id).where(
                            Incident.kind == inc.kind,
                            Incident.dt_id == inc.dt_id,
                            Incident.span_from == inc.span_from,
                            Incident.span_to == inc.span_to,
                            Incident.status.in_([
                                TicketStatus.detected,
                                TicketStatus.acknowledged,
                                TicketStatus.crew_assigned,
                                TicketStatus.resolved,
                            ]),
                        ).limit(1)
                    )
                    if not active_exists:
                        final_incidents.append(inc)

    # 4. Save to Database (upsert detected; leave in-progress tickets untouched)
    _persist_detected_incidents(db, final_incidents)
    db.commit()

    return final_incidents


def is_incident_restored(db: Session, inc: Incident) -> bool:
    """Check if all reporting poles affected by the incident are now energized."""
    topo = get_topology()

    # Identify affected pole IDs
    if inc.kind == FaultKind.feeder:
        stmt = select(Pole.id).where(Pole.feeder_id == inc.feeder_id)
        affected_pids = db.scalars(stmt).all()
    elif inc.kind == FaultKind.dt:
        tree = topo.by_dt.get(inc.dt_id)
        affected_pids = tree.pole_ids if tree else []
    elif inc.kind == FaultKind.span:
        affected_pids = topo.descendants(inc.dt_id, inc.span_to) if inc.dt_id and inc.span_to else []
    else:
        return False

    if not affected_pids:
        return False

    # Get PoleState for all affected poles
    stmt = select(PoleState).where(PoleState.pole_id.in_(affected_pids))
    states = db.scalars(stmt).all()

    # We only care about poles that actually have reporting devices (state is recorded and energized is not None)
    reporting_states = [s for s in states if s.energized is not None]
    if not reporting_states:
        return False

    return all(
        s.energized
        and s.last_power_restored_seq is not None
        and s.last_boot_seq is not None
        for s in reporting_states
    )


def check_incident_restorations(db: Session) -> list[Incident]:
    """Close incidents only after repair completion and telemetry verification."""
    stmt = select(Incident).where(Incident.status == TicketStatus.resolved)
    awaiting_verification = db.scalars(stmt).all()

    restored_incidents = []
    for inc in awaiting_verification:
        if is_incident_restored(db, inc):
            inc.status = TicketStatus.verified
            inc.verified_at = datetime.now(timezone.utc)
            inc.verify_note = "Restoration automatically verified from power_restored and boot telemetry across affected reporting poles."
            # Auto-close immediately after verification
            inc.status = TicketStatus.closed
            inc.closed_at = datetime.now(timezone.utc)
            restored_incidents.append(inc)

    if restored_incidents:
        db.commit()

    return restored_incidents
