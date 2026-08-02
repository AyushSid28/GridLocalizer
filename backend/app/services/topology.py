"""Infer parent links from geography when the registry has none."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.geo import haversine_m

# Typical LT span in dense Indian urban layouts.
MAX_SPAN_M = 70.0


@dataclass
class PolePin:
    pole_id: str
    lat: float
    lon: float


def infer_parents(
    dt_lat: float,
    dt_lon: float,
    poles: list[PolePin],
    max_span_m: float = MAX_SPAN_M,
) -> dict[str, str | None]:
    """
    Grow a tree from the DT: repeatedly attach the nearest free pole
    to the nearest already-connected point (DT or pole), if within max_span_m.

    Returns pole_id -> parent_pole_id (None means direct child of DT).
    """
    if not poles:
        return {}

    parent: dict[str, str | None] = {}
    # connected points: ("dt"|pole_id, lat, lon)
    frontier: list[tuple[str | None, float, float]] = [(None, dt_lat, dt_lon)]
    remaining = {p.pole_id: p for p in poles}

    while remaining:
        best_pole: str | None = None
        best_parent: str | None = None
        best_dist = float("inf")

        for pole_id, pin in remaining.items():
            for src_id, slat, slon in frontier:
                d = haversine_m(slat, slon, pin.lat, pin.lon)
                if d < best_dist:
                    best_dist = d
                    best_pole = pole_id
                    best_parent = src_id

        if best_pole is None:
            break

        # If nothing is within a sane span, still attach to nearest — degraded tree.
        # Localization confidence will reflect inferred topology.
        pin = remaining.pop(best_pole)
        parent[best_pole] = best_parent
        frontier.append((best_pole, pin.lat, pin.lon))

    return parent


def children_map(parent_of: dict[str, str | None]) -> dict[str | None, list[str]]:
    kids: dict[str | None, list[str]] = {}
    for child, parent in parent_of.items():
        kids.setdefault(parent, []).append(child)
    return kids
