"""Background consumer. Processes telemetry events from Redis Stream and updates DB state."""

import json
import logging
import time
from datetime import datetime, timezone
import redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import PoleState, ProcessedEvent
from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")


def process_event(db, data: dict) -> bool:
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

    # Record processing
    pe = ProcessedEvent(
        device_id=device_id,
        seq=seq,
        pole_id=pole_id,
        received_at=datetime.now(timezone.utc),
    )
    db.add(pe)

    # Update state
    state = db.get(PoleState, pole_id)
    if not state:
        state = PoleState(pole_id=pole_id)
        db.add(state)

    state.device_id = device_id
    state.firmware = fw
    state.energized = energized
    state.last_seq = seq
    state.last_event = event_type
    state.last_seen_at = ts
    if battery_mv is not None:
        state.battery_mv = battery_mv
    if rssi is not None:
        state.rssi = rssi

    try:
        db.commit()
        log.info("Processed event: %s seq %s (energized=%s)", pole_id, seq, energized)
        return True
    except IntegrityError:
        db.rollback()
        # Might be concurrent processing
        log.warning("Integrity error on event: %s seq %s", device_id, seq)
        return False


def main() -> None:
    settings = get_settings()
    log.info("Worker started — connecting to Redis and Database")

    r = redis.from_url(settings.redis_url, decode_responses=True)
    stream = settings.telemetry_stream

    # Recover last processed stream ID from Redis, or start from beginning ('0-0')
    last_id = r.get("telemetry:last_processed_id") or "0-0"
    log.info("Starting stream consumption from ID: %s", last_id)

    while True:
        try:
            # Read from the stream
            response = r.xread({stream: last_id}, count=100, block=2000)
            if not response:
                continue

            for stream_name, messages in response:
                for msg_id, payload in messages:
                    raw_data = payload.get("payload")
                    if not raw_data:
                        last_id = msg_id
                        continue

                    data = json.loads(raw_data)
                    with SessionLocal() as db:
                        success = process_event(db, data)

                    if success:
                        last_id = msg_id
                        r.set("telemetry:last_processed_id", last_id)

        except redis.RedisError as e:
            log.error("Redis connection error: %s. Retrying in 5s...", e)
            time.sleep(5)
        except Exception as e:
            log.error("Unexpected error in worker loop: %s. Retrying...", e, exc_info=True)
            time.sleep(1)


if __name__ == "__main__":
    main()

