"""Debounce keys for localization — first change starts the timer; later events must not reset it."""

import time

import redis


def mark_dt_dirty(r: redis.Redis, dt_id: str) -> None:
    key = f"dt_dirty:{dt_id}"
    if not r.exists(key):
        r.set(key, time.time())
