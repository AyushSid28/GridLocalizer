import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.db import Base
from app.models import (
    DistributionTransformer,
    FaultKind,
    Feeder,
    Incident,
    Pole,
    PoleState,
    TicketStatus,
    TopologySource,
)
from app.services.localization import check_incident_restorations
from app.services.topo_index import refresh_topology
from app.api.incidents import resolve_incident, acknowledge_incident, assign_crew, CrewAssignmentIn
from app.api.sim import repair_fault, FaultInjectionIn

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(bind=engine)


@pytest.fixture
def test_db():
    tables = [
        Feeder.__table__,
        DistributionTransformer.__table__,
        Pole.__table__,
        PoleState.__table__,
        Incident.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    db = TestingSessionLocal()

    # Seed
    f = Feeder(id="F-TEST", name="Test Feeder")
    db.add(f)
    dt = DistributionTransformer(
        id="DT-1",
        feeder_id="F-TEST",
        lat=12.9,
        lon=77.5,
        wiring_known=True,
    )
    db.add(dt)
    db.commit()

    p1 = Pole(
        id="P-01",
        lat=12.9001,
        lon=77.5001,
        feeder_id="F-TEST",
        dt_id="DT-1",
        parent_id=None,
        true_parent_id=None,
        device_id="D-P01",
        topology_source=TopologySource.recorded,
    )
    db.add(p1)
    db.commit()

    # Active dark state
    db.add(PoleState(pole_id="P-01", device_id="D-P01", energized=False, last_seen_at=datetime.now(timezone.utc)))
    db.commit()

    refresh_topology(db)

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=tables)


def test_ticket_fsm_transitions_and_pushback(test_db):
    # Create detected incident
    inc = Incident(
        id="INC-1",
        kind=FaultKind.dt,
        status=TicketStatus.detected,
        feeder_id="F-TEST",
        dt_id="DT-1",
        affected_poles=1,
    )
    test_db.add(inc)
    test_db.commit()

    # Acknowledge
    res = acknowledge_incident("INC-1", test_db)
    assert res["status"] == "acknowledged"

    # Assign crew
    res = assign_crew("INC-1", CrewAssignmentIn(crew_label="Crew A"), test_db)
    assert res["status"] == "crew_assigned"
    assert res["crew_label"] == "Crew A"

    with pytest.raises(HTTPException) as exc:
        resolve_incident("INC-1", test_db)
    assert exc.value.status_code == 409

    state = test_db.get(PoleState, "P-01")
    state.energized = True
    state.last_power_restored_seq = 2
    state.last_power_restored_at = datetime.now(timezone.utc)
    state.last_boot_seq = 3
    state.last_boot_at = datetime.now(timezone.utc)
    test_db.commit()

    res = resolve_incident("INC-1", test_db)
    assert res["status"] == "closed"
    assert test_db.get(Incident, "INC-1").status == TicketStatus.closed


def test_ticket_fsm_transitions_and_pushback_legacy_telemetry_steps(test_db):
    """Document verifier requirements step-by-step after resolve (historical path)."""
    inc = Incident(
        id="INC-1B",
        kind=FaultKind.dt,
        status=TicketStatus.detected,
        feeder_id="F-TEST",
        dt_id="DT-1",
        affected_poles=1,
    )
    test_db.add(inc)
    test_db.commit()

    acknowledge_incident("INC-1B", test_db)
    assign_crew("INC-1B", CrewAssignmentIn(crew_label="Crew A"), test_db)

    state = test_db.get(PoleState, "P-01")
    state.energized = True
    state.last_power_restored_seq = 2
    state.last_power_restored_at = datetime.now(timezone.utc)
    state.last_boot_seq = 3
    state.last_boot_at = datetime.now(timezone.utc)
    test_db.commit()

    res = resolve_incident("INC-1B", test_db)
    assert res["status"] == "closed"
    assert "Restoration automatically verified" in test_db.get(Incident, "INC-1B").verify_note


def test_repair_does_not_skip_crew_workflow(test_db):
    from unittest.mock import MagicMock

    inc = Incident(
        id="INC-CREW",
        kind=FaultKind.dt,
        status=TicketStatus.crew_assigned,
        feeder_id="F-TEST",
        dt_id="DT-1",
        affected_poles=1,
        crew_label="Crew B",
    )
    test_db.add(inc)
    test_db.commit()

    r_mock = MagicMock()
    pipe = MagicMock()
    r_mock.pipeline.return_value = pipe
    settings_mock = MagicMock()
    settings_mock.telemetry_stream = "test.telemetry"

    repair_fault(
        FaultInjectionIn(kind="dt", target_id="DT-1"),
        db=test_db,
        r=r_mock,
        settings=settings_mock,
    )

    test_db.refresh(inc)
    assert inc.status == TicketStatus.crew_assigned

    state = test_db.get(PoleState, "P-01")
    assert state.energized is True
    assert state.last_power_restored_seq is not None
    assert state.last_boot_seq is not None

    res = resolve_incident("INC-CREW", test_db)
    assert res["status"] == "closed"


def test_auto_verify_restoration(test_db):
    # Create incident in detected
    inc = Incident(
        id="INC-2",
        kind=FaultKind.dt,
        status=TicketStatus.detected,
        feeder_id="F-TEST",
        dt_id="DT-1",
        affected_poles=1,
    )
    test_db.add(inc)
    test_db.commit()

    # Verify no auto-restore yet (since P-01 is dark)
    restored = check_incident_restorations(test_db)
    assert len(restored) == 0

    # Restore power in telemetry, but do not mark repair complete yet.
    state = test_db.get(PoleState, "P-01")
    state.energized = True
    state.last_power_restored_seq = 2
    state.last_power_restored_at = datetime.now(timezone.utc)
    state.last_boot_seq = 3
    state.last_boot_at = datetime.now(timezone.utc)
    test_db.commit()

    restored = check_incident_restorations(test_db)
    assert len(restored) == 0
    assert test_db.get(Incident, "INC-2").status == TicketStatus.detected

    inc.status = TicketStatus.resolved
    test_db.commit()

    # Check auto-restoration after operator resolution.
    restored = check_incident_restorations(test_db)
    assert len(restored) == 1
    assert restored[0].id == "INC-2"
    assert restored[0].status == TicketStatus.closed
    assert "Restoration automatically verified" in restored[0].verify_note
