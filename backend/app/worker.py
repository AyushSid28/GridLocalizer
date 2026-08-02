"""Background consumer. Idle until P2 wires Redis → state updates."""

import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")


def main() -> None:
    log.info("worker started — waiting for telemetry stream (P2)")
    while True:
        time.sleep(30)
        log.info("worker idle")


if __name__ == "__main__":
    main()
