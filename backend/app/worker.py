"""Background consumer. Processes telemetry events from Redis Stream and updates DB state."""

import json
import logging
import time
from datetime import datetime, timezone
import redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Pole, PoleState, ProcessedEvent
from app.services.dt_dirty import mark_dt_dirty
from app.services.localization import run_global_localization, check_incident_restorations
from app.services.topo_index import get_topology, refresh_topology
from app.settings import get_settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")


def process_event(db, r: redis.Redis, data: dict, dirty_dts: set) -> bool:
    """Process a single telemetry event with deduplication."""
    device_id = data["device_id"]
    seq = data["seq"]
    pole_id = data["pole_id"]
    event_type = data["event"]
    energized = data["energized"]
    ts = datetime.fromisoformat(data["ts"])
    battery_mv = data.get("battery_mv")
    rssi = data.get("rssi")
    fw = data.get("fw", "1.4.2")

    # Check for duplicate event
    dup = db.scalar(
        select(ProcessedEvent).where(
            ProcessedEvent.device_id == device_id, ProcessedEvent.seq == seq
        )
    )
    if dup:
        log.debug("Duplicate event skipped: %s seq %s", device_id, seq)
        return True

    state = db.get(PoleState, pole_id)
    if state and seq <= state.last_seq:
        db.add(
            ProcessedEvent(
                device_id=device_id,
                seq=seq,
                pole_id=pole_id,
                received_at=datetime.now(timezone.utc),
            )
        )
        log.info("Stale event recorded without state change: %s seq %s", pole_id, seq)
        return True

    # Record processing
    pe = ProcessedEvent(
        device_id=device_id,
        seq=seq,
        pole_id=pole_id,
        received_at=datetime.now(timezone.utc),
    )
    db.add(pe)

    # Update state
    state_changed = False
    if not state:
        state = PoleState(pole_id=pole_id)
        db.add(state)
        state_changed = True
    else:
        if state.energized != energized:
            state_changed = True

    state.device_id = device_id
    state.firmware = fw
    state.energized = energized
    state.last_seq = seq
    state.last_event = event_type
    state.last_seen_at = ts
    if event_type == "power_restored":
        state.last_power_restored_seq = seq
        state.last_power_restored_at = ts
    elif event_type == "boot":
        state.last_boot_seq = seq
        state.last_boot_at = ts
    if energized is False:
        state.last_boot_seq = None
        state.last_power_restored_seq = None
        state.last_boot_at = None
        state.last_power_restored_at = None
    if battery_mv is not None:
        state.battery_mv = battery_mv
    if rssi is not None:
        state.rssi = rssi

    # Mark suspect_sensor as False when a new event arrives (re-evaluate during localization)
    state.suspect_sensor = False

    log.info("Processed event: %s seq %s (energized=%s)", pole_id, seq, energized)

    if state_changed:
        topo = get_topology()
        dt_id = topo.pole_to_dt.get(pole_id)
        if dt_id:
            mark_dt_dirty(r, dt_id)
            dirty_dts.add(dt_id)
            log.info("Marked DT %s as dirty due to state change on pole %s", dt_id, pole_id)

    return True


def main() -> None:
    settings = get_settings()
    log.info("Worker started — connecting to Redis and Database")

    r = redis.from_url(settings.redis_url, decode_responses=True)
    stream = settings.telemetry_stream

    # Load / refresh topology on startup so get_topology() works in-memory
    with SessionLocal() as db:
        refresh_topology(db)
    log.info("Loaded topology index")

    # Recover last processed stream ID from Redis, or start from beginning ('0-0')
    last_id = r.get("telemetry:last_processed_id") or "0-0"
    log.info("Starting stream consumption from ID: %s", last_id)

    last_debounce_check = time.time()

    from app.services.localization import run_global_localization

    while True:
        try:
            # 1. Read from the stream
            response = r.xread({stream: last_id}, count=100, block=1000)
            if response:
                with SessionLocal() as db:
                    dirty_dts = set()
                    processed_any = False
                    for stream_name, messages in response:
                        for msg_id, payload in messages:
                            raw_data = payload.get("payload")
                            if not raw_data:
                                last_id = msg_id
                                continue
    
                            data = json.loads(raw_data)
                            try:
                                success = process_event(db, r, data, dirty_dts)
                                if success:
                                    last_id = msg_id
                                processed_any = True
                            except IntegrityError:
                                db.rollback()
                                log.warning("Integrity error on event: %s seq %s", data["device_id"], data["seq"])
                    
                    if processed_any:
                        db.commit()
                        r.set("telemetry:last_processed_id", last_id)

            # 2. Check for mature debounced DT state changes
            now = time.time()
            if now - last_debounce_check >= 2.0:
                last_debounce_check = now
                ready_dt_ids = set()
                for key in r.scan_iter("dt_dirty:*", count=50):
                    dirty_time = float(r.get(key) or 0)
                    if now - dirty_time >= settings.detect_wait_sec:
                        dt_id = key.split(":")[-1]
                        r.delete(key)
                        ready_dt_ids.add(dt_id)
                        log.info("DT %s dirty timer matured. Queued for targeted localization.", dt_id)

                if ready_dt_ids:
                    with SessionLocal() as db:
                        run_global_localization(db)
                    log.info("Completed global localization run for %d dirty DTs.", len(ready_dt_ids))

                # Always check for restorations when debouncing loop runs
                with SessionLocal() as db:
                    check_incident_restorations(db)

        except redis.RedisError as e:
            log.error("Redis connection error: %s. Retrying in 5s...", e)
            time.sleep(5)
        except Exception as e:
            log.error("Unexpected error in worker loop: %s. Retrying...", e, exc_info=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
