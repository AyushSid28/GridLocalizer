import pytest
import json
from unittest.mock import MagicMock
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.db import Base
from app.models import (
    DistributionTransformer,
    Feeder,
    FaultKind,
    Incident,
    Pole,
    PoleState,
    ProcessedEvent,
    ScheduledOutage,
    TopologySource,
)
from app.services.topo_index import refresh_topology
from app.services.localization import run_global_localization
from app.api.sim import inject_fault, repair_fault, inject_noise, run_scenario, FaultInjectionIn, NoiseInjectionIn, ScenarioFault, ScenarioIn
from app.worker import process_event

engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(bind=engine)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture
def test_db():
    tables = [
        Feeder.__table__,
        DistributionTransformer.__table__,
        Pole.__table__,
        PoleState.__table__,
        ProcessedEvent.__table__,
        Incident.__table__,
        ScheduledOutage.__table__,
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

    db.add(PoleState(pole_id="P-01", device_id="D-P01", energized=True, last_seen_at=datetime.now(timezone.utc)))
    db.commit()

    refresh_topology(db)

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=tables)


def test_fault_injection_and_repair(test_db):
    r_mock = MagicMock()
    settings_mock = MagicMock()
    settings_mock.telemetry_stream = "test.telemetry"

    # Inject outage on DT-1
    res = inject_fault(
        FaultInjectionIn(kind="dt", target_id="DT-1"),
        db=test_db,
        r=r_mock,
        settings=settings_mock
    )
    assert res["injected"] is True
    assert res["affected_devices"] == 1

    # Simulator publishes telemetry only; worker owns DB state changes.
    state = test_db.get(PoleState, "P-01")
    assert state.energized is True
    assert state.last_event is None

    # Verify stream message was published
    assert r_mock.xadd.call_count == 1

    # Reset mock and repair
    r_mock.reset_mock()
    res = repair_fault(
        FaultInjectionIn(kind="dt", target_id="DT-1"),
        db=test_db,
        r=r_mock,
        settings=settings_mock
    )
    assert res["repaired"] is True
    assert res["affected_devices"] == 1

    # Repair emits boot + power_restored and still does not mutate DB directly.
    state = test_db.get(PoleState, "P-01")
    assert state.energized is True
    assert state.last_event is None
    assert r_mock.xadd.call_count == 2


def test_noise_injection(test_db):
    r_mock = MagicMock()
    settings_mock = MagicMock()
    settings_mock.telemetry_stream = "test.telemetry"

    # Inject dead_sensor noise on P-01
    res = inject_noise(
        NoiseInjectionIn(kind="dead_sensor", target_id="P-01"),
        db=test_db,
        r=r_mock,
        settings=settings_mock
    )
    assert res["noise_injected"] is True
    assert res["kind"] == "dead_sensor"

    # Noise is also published as telemetry only.
    state = test_db.get(PoleState, "P-01")
    assert state.energized is True
    assert r_mock.xadd.call_count == 1

    r_mock.reset_mock()
    res = inject_noise(
        NoiseInjectionIn(kind="reorder", target_id="P-01"),
        db=test_db,
        r=r_mock,
        settings=settings_mock
    )
    assert res["noise_injected"] is True
    assert res["kind"] == "reorder"
    assert r_mock.xadd.call_count == 2


def test_simulator_repair_events_are_processed_by_worker(test_db):
    r_mock = MagicMock()
    settings_mock = MagicMock()
    settings_mock.telemetry_stream = "test.telemetry"

    res = repair_fault(
        FaultInjectionIn(kind="dt", target_id="DT-1"),
        db=test_db,
        r=r_mock,
        settings=settings_mock
    )

    assert res["repaired"] is True
    payloads = [call.args[1]["payload"] for call in r_mock.xadd.call_args_list]
    assert [json.loads(p)["event"] for p in payloads] == ["boot", "power_restored"]

    for raw in payloads:
        assert process_event(test_db, r_mock, json.loads(raw)) is True

    state = test_db.get(PoleState, "P-01")
    assert state.energized is True
    assert state.last_boot_seq is not None
    assert state.last_power_restored_seq is not None


def test_multi_dt_scenario_publishes_without_500(test_db):
    live_dt = DistributionTransformer(
        id="D-0010",
        feeder_id="F-TEST",
        lat=12.9,
        lon=77.5,
        wiring_known=True,
    )
    test_db.add(live_dt)
    test_db.add(
        Pole(
            id="P-D-0010",
            lat=12.9001,
            lon=77.5001,
            feeder_id="F-TEST",
            dt_id="D-0010",
            parent_id=None,
            true_parent_id=None,
            device_id="DEV-D-0010",
            topology_source=TopologySource.recorded,
        )
    )
    test_db.add(
        PoleState(
            pole_id="P-D-0010",
            device_id="DEV-D-0010",
            energized=True,
            last_seq=0,
            last_seen_at=datetime.now(timezone.utc),
        )
    )

    for dt_id in ["D-0003", "D-0006", "D-0008"]:
        test_db.add(
            DistributionTransformer(
                id=dt_id,
                feeder_id="F-TEST",
                lat=12.9,
                lon=77.5,
                wiring_known=True,
            )
        )
        pole_id = f"P-{dt_id}"
        test_db.add(
            Pole(
                id=pole_id,
                lat=12.9001,
                lon=77.5001,
                feeder_id="F-TEST",
                dt_id=dt_id,
                parent_id=None,
                true_parent_id=None,
                device_id=f"DEV-{dt_id}",
                topology_source=TopologySource.recorded,
            )
        )
        test_db.add(
            PoleState(
                pole_id=pole_id,
                device_id=f"DEV-{dt_id}",
                energized=True,
                last_seq=0,
                last_seen_at=datetime.now(timezone.utc),
            )
        )
    test_db.commit()
    refresh_topology(test_db)

    r_mock = MagicMock()
    settings_mock = MagicMock()
    settings_mock.telemetry_stream = "test.telemetry"

    res = run_scenario(
        ScenarioIn(
            faults=[
                ScenarioFault(kind="dt", target_id="D-0003"),
                ScenarioFault(kind="dt", target_id="D-0006"),
                ScenarioFault(kind="dt", target_id="D-0008"),
            ]
        ),
        db=test_db,
        r=r_mock,
        settings=settings_mock,
    )

    assert res["status"] == "injected"
    assert res["affected_devices"] == 3
    assert set(res["dts"]) == {"D-0003", "D-0006", "D-0008"}
    assert r_mock.xadd.call_count == 3

    for call in r_mock.xadd.call_args_list:
        assert process_event(test_db, r_mock, json.loads(call.args[1]["payload"])) is True

    incidents = run_global_localization(test_db)
    assert len(incidents) == 3
    assert {inc.kind for inc in incidents} == {FaultKind.dt}
    assert {inc.dt_id for inc in incidents} == {"D-0003", "D-0006", "D-0008"}
