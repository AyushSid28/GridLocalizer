import pytest
from sqlalchemy import create_engine, select
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
    ScheduledOutage,
    TopologySource,
)
from app.services.localization import run_global_localization
from app.services.topo_index import refresh_topology

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
        ScheduledOutage.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)

    db = TestingSessionLocal()

    # Seed a simple testing topology
    # Feeder 1
    f = Feeder(id="F-TEST", name="Test Feeder")
    db.add(f)

    # DT 1 (Known wiring: DT -> P-01 -> P-02 -> P-03 -> P-04)
    dt1 = DistributionTransformer(
        id="DT-1",
        feeder_id="F-TEST",
        lat=12.9,
        lon=77.5,
        wiring_known=True,
    )
    db.add(dt1)

    # DT 2 (Inferred wiring: DT -> P-05 -> P-06)
    dt2 = DistributionTransformer(
        id="DT-2",
        feeder_id="F-TEST",
        lat=12.95,
        lon=77.55,
        wiring_known=False,
    )
    db.add(dt2)
    db.commit()

    # Poles for DT 1
    p1 = Pole(
        id="P-01",
        lat=12.9001,
        lon=77.5001,
        feeder_id="F-TEST",
        dt_id="DT-1",
        parent_id=None,
        true_parent_id=None,
        pincode="560001",
        topology_source=TopologySource.recorded,
        device_id="D-P01",
    )
    p2 = Pole(
        id="P-02",
        lat=12.9002,
        lon=77.5002,
        feeder_id="F-TEST",
        dt_id="DT-1",
        parent_id="P-01",
        true_parent_id="P-01",
        pincode="560001",
        topology_source=TopologySource.recorded,
        device_id="D-P02",
    )
    p3 = Pole(
        id="P-03",
        lat=12.9003,
        lon=77.5003,
        feeder_id="F-TEST",
        dt_id="DT-1",
        parent_id="P-02",
        true_parent_id="P-02",
        pincode="560001",
        topology_source=TopologySource.recorded,
        device_id="D-P03",
    )
    p4 = Pole(
        id="P-04",
        lat=12.9004,
        lon=77.5004,
        feeder_id="F-TEST",
        dt_id="DT-1",
        parent_id="P-03",
        true_parent_id="P-03",
        pincode="560001",
        topology_source=TopologySource.recorded,
        device_id="D-P04",
    )

    # Poles for DT 2
    p5 = Pole(
        id="P-05",
        lat=12.9501,
        lon=77.5501,
        feeder_id="F-TEST",
        dt_id="DT-2",
        parent_id=None,
        true_parent_id=None,
        pincode="560002",
        topology_source=TopologySource.inferred,
        device_id="D-P05",
    )
    p6 = Pole(
        id="P-06",
        lat=12.9502,
        lon=77.5502,
        feeder_id="F-TEST",
        dt_id="DT-2",
        parent_id="P-05",
        true_parent_id="P-05",
        pincode="560002",
        topology_source=TopologySource.inferred,
        device_id="D-P06",
    )

    db.add_all([p1, p2, p3, p4, p5, p6])
    db.commit()

    # Initialize all poles as energized
    for pid, dev_id in [
        ("P-01", "D-P01"),
        ("P-02", "D-P02"),
        ("P-03", "D-P03"),
        ("P-04", "D-P04"),
        ("P-05", "D-P05"),
        ("P-06", "D-P06"),
    ]:
        db.add(
            PoleState(
                pole_id=pid,
                device_id=dev_id,
                energized=True,
                last_seq=1,
            )
        )
    db.commit()

    # Initialize the in-memory topology index
    refresh_topology(db)

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=tables)


def test_known_topology_span_cut(test_db):
    # Cut span P-01 -> P-02 (so P-02, P-03, P-04 go dark)
    for pid in ["P-02", "P-03", "P-04"]:
        state = test_db.get(PoleState, pid)
        state.energized = False
    test_db.commit()

    incidents = run_global_localization(test_db)

    # We expect exactly 1 incident at the span P-01 -> P-02
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.kind == FaultKind.span
    assert inc.span_from == "P-01"
    assert inc.span_to == "P-02"
    assert inc.affected_poles == 3
    assert inc.confidence == 0.90
    assert inc.topology_mode == "recorded"


def test_dt_total_dark(test_db):
    # Make all poles under DT-1 dark
    for pid in ["P-01", "P-02", "P-03", "P-04"]:
        state = test_db.get(PoleState, pid)
        state.energized = False
    test_db.commit()

    incidents = run_global_localization(test_db)

    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.kind == FaultKind.dt
    assert inc.dt_id == "DT-1"
    assert inc.affected_poles == 4
    assert inc.confidence == 0.95


def test_feeder_total_dark(test_db):
    # Make all poles under both DT-1 and DT-2 dark
    for pid in ["P-01", "P-02", "P-03", "P-04", "P-05", "P-06"]:
        state = test_db.get(PoleState, pid)
        state.energized = False
    test_db.commit()

    incidents = run_global_localization(test_db)

    feeder = [i for i in incidents if i.kind == FaultKind.feeder]
    dt_incidents = [i for i in incidents if i.kind == FaultKind.dt]
    assert len(feeder) == 1
    assert feeder[0].feeder_id == "F-TEST"
    assert feeder[0].affected_poles == 6
    assert len(dt_incidents) == 2


def test_sensor_failure_dark_parent_live_child(test_db):
    # P-02 is dark, but P-03 (child) is live. Physically impossible.
    state_p2 = test_db.get(PoleState, "P-02")
    state_p2.energized = False
    test_db.commit()

    incidents = run_global_localization(test_db)

    # We expect 0 outage tickets because P-02 is classified as a sensor failure
    assert len(incidents) == 0

    # Verify P-02 is flagged as suspect sensor
    state_p2_updated = test_db.get(PoleState, "P-02")
    assert state_p2_updated.suspect_sensor is True


def test_two_spans_same_dt(test_db):
    # Two independent spurs going dark.
    # In our radial line DT -> P-01 -> P-02 -> P-03 -> P-04,
    # if P-02 is dark and P-03 is live, that's suspect.
    # But wait, to test two independent spans going dark, let's create a branched topology
    # or test two dark frontiers.
    # For example: P-02 goes dark, but P-03 is live (which triggers sensor failure on P-02).
    # Then P-04 goes dark (with P-03 live).
    # Let's customize the topology dynamically for this test.
    # Let's say DT-1 has direct children P-01 and P-02.
    # Let's build a branched structure on DT-1 for this test:
    # DT-1 -> P-01 (dark)
    # DT-1 -> P-02 (live) -> P-03 (dark) -> P-04 (dark)
    # That should trigger two incidents: one on span DT -> P-01, and one on span P-02 -> P-03.
    # Let's update parents:
    p1 = test_db.get(Pole, "P-01")
    p1.parent_id = None
    p2 = test_db.get(Pole, "P-02")
    p2.parent_id = None
    p3 = test_db.get(Pole, "P-03")
    p3.parent_id = "P-02"
    p4 = test_db.get(Pole, "P-04")
    p4.parent_id = "P-03"
    test_db.commit()

    refresh_topology(test_db)

    # Now make P-01 and P-03 (and P-04) dark.
    # P-02 remains live.
    test_db.get(PoleState, "P-01").energized = False
    test_db.get(PoleState, "P-03").energized = False
    test_db.get(PoleState, "P-04").energized = False
    test_db.commit()

    incidents = run_global_localization(test_db)

    # We expect 2 incidents
    assert len(incidents) == 2
    kinds = [inc.kind for inc in incidents]
    assert all(k == FaultKind.span for k in kinds)

    targets = {(inc.span_from, inc.span_to) for inc in incidents}
    assert (None, "P-01") in targets
    assert ("P-02", "P-03") in targets


def test_inferred_topology_span(test_db):
    # DT-2 has inferred topology.
    # Make P-06 dark, while P-05 is live.
    state = test_db.get(PoleState, "P-06")
    state.energized = False
    test_db.commit()

    incidents = run_global_localization(test_db)

    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.kind == FaultKind.span
    assert inc.span_from == "P-05"
    assert inc.span_to == "P-06"
    assert inc.topology_mode == "inferred"
    assert inc.confidence == 0.60
