import pytest
from datetime import datetime, timedelta, timezone
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

    # Seed Feeder and DTs
    f = Feeder(id="F-TEST", name="Test Feeder")
    db.add(f)

    dt1 = DistributionTransformer(
        id="DT-1",
        feeder_id="F-TEST",
        lat=12.9,
        lon=77.5,
        wiring_known=True,
    )
    dt2 = DistributionTransformer(
        id="DT-2",
        feeder_id="F-TEST",
        lat=12.95,
        lon=77.55,
        wiring_known=True,
    )
    db.add_all([dt1, dt2])
    db.commit()

    # Poles
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
        lat=12.9501,
        lon=77.5501,
        feeder_id="F-TEST",
        dt_id="DT-2",
        parent_id=None,
        true_parent_id=None,
        pincode="560002",
        topology_source=TopologySource.recorded,
        device_id="D-P03",
    )
    db.add_all([p1, p2, p3])
    db.commit()

    # Initialize state
    db.add(PoleState(pole_id="P-01", device_id="D-P01", energized=True, last_seen_at=datetime.now(timezone.utc)))
    db.add(PoleState(pole_id="P-02", device_id="D-P02", energized=True, last_seen_at=datetime.now(timezone.utc)))
    db.add(PoleState(pole_id="P-03", device_id="D-P03", energized=True, last_seen_at=datetime.now(timezone.utc)))
    db.commit()

    refresh_topology(db)


    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=tables)


def test_scheduled_outage_suppression(test_db):
    # Setup scheduled outage for DT-1 active now
    now = datetime.now(timezone.utc)
    if test_db.bind.dialect.name == "sqlite":
        now = now.replace(tzinfo=None)

    outage = ScheduledOutage(
        id="SO-1",
        scope="dt",
        target_id="DT-1",
        starts_at=now - timedelta(minutes=10),
        ends_at=now + timedelta(minutes=50),
        reason="Testing suppression",
    )

    test_db.add(outage)

    # Make DT-1 entirely dark
    test_db.get(PoleState, "P-01").energized = False
    test_db.get(PoleState, "P-02").energized = False
    test_db.commit()

    # Run localization

    incidents = run_global_localization(test_db)

    # We expect 0 incidents because it should be suppressed
    assert len(incidents) == 0


def test_dead_sensor_silence_suppression(test_db):
    # P-02 goes silent (>300 seconds ago)
    state = test_db.get(PoleState, "P-02")
    state.energized = False
    state.last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    test_db.commit()

    # P-01 remains active and energized
    state_p1 = test_db.get(PoleState, "P-01")
    state_p1.last_seen_at = datetime.now(timezone.utc)
    test_db.commit()

    incidents = run_global_localization(test_db)

    # We expect 0 incidents because P-02 is classified as an isolated silent dead sensor
    assert len(incidents) == 0

    # P-02 should be marked suspect
    assert test_db.get(PoleState, "P-02").suspect_sensor is True
