#!/usr/bin/env python3
"""CLI utilities for the assignment backend.

Usage (inside the api container):
    python -m app.cli seed
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def seed_command() -> None:
    """Run the seeding logic and print a summary."""
    from app.db import SessionLocal
    from app.services.seed import seed_network

    with SessionLocal() as db:
        result = seed_network(db)
        print("Seed result:", result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Backend utility commands")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    subparsers.add_parser("seed", help="Seed synthetic network into Postgres")

    args = parser.parse_args(argv)

    if args.cmd == "seed":
        seed_command()

    return 0


if __name__ == "__main__":
    sys.exit(main())
