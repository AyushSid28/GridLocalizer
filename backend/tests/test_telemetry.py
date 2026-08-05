from unittest.mock import MagicMock
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import PoleState, ProcessedEvent
from app.worker import process_event

# Setup in-memory sqlite for testing
engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(bind=engine)


@pytest.fixture
def db_session():
    tables = [PoleState.__table__, ProcessedEvent.__table__]
    Base.metadata.create_all(bind=engine, tables=tables)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=tables)


def test_process_event_deduplication_and_state(db_session):
    # Prepare dummy data
    data = {
        "device_id": "KSPDB-SD07-D-0001-000001",
        "pole_id": "P-000001",
        "event": "heartbeat",
        "energized": True,
        "ts": "2026-08-02T19:00:00+00:00",
        "seq": 10,
        "battery_mv": 3800,
        "rssi": -70,
        "fw": "1.4.2",
    }
    r_mock = MagicMock()

    dirty: set[str] = set()

    # First processing
    success = process_event(db_session, r_mock, data, dirty)
    assert success is True

    # Verify event recorded in ProcessedEvent
    pe = db_session.scalar(
        select(ProcessedEvent).where(
            ProcessedEvent.device_id == data["device_id"],
            ProcessedEvent.seq == data["seq"],
        )
    )
    assert pe is not None
    assert pe.pole_id == "P-000001"

    # Verify PoleState updated
    state = db_session.get(PoleState, "P-000001")
    assert state is not None
    assert state.device_id == data["device_id"]
    assert state.energized is True
    assert state.last_seq == 10
    assert state.battery_mv == 3800
    assert state.rssi == -70
    assert state.firmware == "1.4.2"

    # Duplicate processing should be skipped
    success_dup = process_event(db_session, r_mock, data, dirty)
    assert success_dup is True  # returns True (skipped cleanly without error)

    # Modify some values and send a new sequence number
    data_new = data.copy()
    data_new["seq"] = 11
    data_new["energized"] = False
    data_new["event"] = "power_lost"

    success_new = process_event(db_session, r_mock, data_new, dirty)
    assert success_new is True

    # Verify PoleState is updated to new values
    state_updated = db_session.get(PoleState, "P-000001")
    assert state_updated.energized is False
    assert state_updated.last_seq == 11
    assert state_updated.last_event == "power_lost"

    stale = data.copy()
    stale["seq"] = 10
    stale["energized"] = True
    stale["event"] = "heartbeat"
    success_stale = process_event(db_session, r_mock, stale, dirty)
    assert success_stale is True
    state_after_stale = db_session.get(PoleState, "P-000001")
    assert state_after_stale.energized is False
    assert state_after_stale.last_seq == 11

    restored = data.copy()
    restored["seq"] = 12
    restored["energized"] = True
    restored["event"] = "power_restored"
    assert process_event(db_session, r_mock, restored, dirty) is True

    boot = data.copy()
    boot["seq"] = 13
    boot["energized"] = True
    boot["event"] = "boot"
    assert process_event(db_session, r_mock, boot, dirty) is True

    state_restored = db_session.get(PoleState, "P-000001")
    assert state_restored.last_power_restored_seq == 12
    assert state_restored.last_boot_seq == 13
