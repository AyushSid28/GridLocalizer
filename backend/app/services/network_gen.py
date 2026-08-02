"""Build a synthetic radial LT network shaped like the brief."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from app.services.geo import offset_lat_lon
from app.services.topology import PolePin, infer_parents

# Bangalore-ish box for the fake subdivision.
ORIGIN_LAT = 12.935
ORIGIN_LON = 77.580

PINCODES = [
    "560001",
    "560002",
    "560011",
    "560025",
    "560034",
    "560038",
    "560041",
    "560066",
    "560068",
    "560076",
    "560078",
    "560095",
    "560102",
]


@dataclass
class GenPole:
    pole_id: str
    lat: float
    lon: float
    feeder_id: str
    dt_id: str
    true_parent_id: str | None
    seq_on_line: int
    ward: str
    pincode: str | None
    device_id: str | None
    firmware: str | None
    # What the asset DB exposes
    parent_id: str | None = None
    topology_source: str = "none"


@dataclass
class GenDT:
    dt_id: str
    feeder_id: str
    lat: float
    lon: float
    capacity_kva: int
    households: int
    wiring_known: bool


@dataclass
class GenFeeder:
    feeder_id: str
    name: str


@dataclass
class NetworkBlueprint:
    feeders: list[GenFeeder] = field(default_factory=list)
    dts: list[GenDT] = field(default_factory=list)
    poles: list[GenPole] = field(default_factory=list)


def _walk_branch(
    rng: random.Random,
    start_lat: float,
    start_lon: float,
    bearing_deg: float,
    count: int,
    step_m: float,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    lat, lon = start_lat, start_lon
    bearing = math.radians(bearing_deg)
    for _ in range(count):
        bearing += math.radians(rng.uniform(-18, 18))
        north = step_m * math.cos(bearing)
        east = step_m * math.sin(bearing)
        lat, lon = offset_lat_lon(lat, lon, north, east)
        points.append((lat, lon))
    return points


def _build_dt_tree(
    rng: random.Random,
    feeder_id: str,
    dt_id: str,
    dt_lat: float,
    dt_lon: float,
    pole_count: int,
    pole_start: int,
    ward: str,
    pincode: str,
) -> list[GenPole]:
    """Lay a main run + a few spurs. Returns poles with true parents set."""
    step = rng.uniform(28, 45)
    main_n = max(6, int(pole_count * rng.uniform(0.55, 0.75)))
    spur_budget = pole_count - main_n

    bearing = rng.uniform(0, 360)
    main_pts = _walk_branch(rng, dt_lat, dt_lon, bearing, main_n, step)

    poles: list[GenPole] = []
    seq = 1
    prev: str | None = None

    for lat, lon in main_pts:
        pid = f"P-{pole_start + len(poles):06d}"
        poles.append(
            GenPole(
                pole_id=pid,
                lat=lat,
                lon=lon,
                feeder_id=feeder_id,
                dt_id=dt_id,
                true_parent_id=prev,
                seq_on_line=seq,
                ward=ward,
                pincode=pincode,
                device_id=None,
                firmware=None,
            )
        )
        prev = pid
        seq += 1

    # Spurs off random main poles
    while spur_budget > 0 and poles:
        attach = poles[rng.randrange(0, max(1, len(poles) // 2 + 1))]
        spur_len = min(spur_budget, rng.randint(2, 8))
        spur_bearing = rng.uniform(0, 360)
        spur_pts = _walk_branch(rng, attach.lat, attach.lon, spur_bearing, spur_len, step * 0.9)
        prev = attach.pole_id
        for lat, lon in spur_pts:
            pid = f"P-{pole_start + len(poles):06d}"
            poles.append(
                GenPole(
                    pole_id=pid,
                    lat=lat,
                    lon=lon,
                    feeder_id=feeder_id,
                    dt_id=dt_id,
                    true_parent_id=prev,
                    seq_on_line=seq,
                    ward=ward,
                    pincode=pincode,
                    device_id=None,
                    firmware=None,
                )
            )
            prev = pid
            seq += 1
        spur_budget -= spur_len

    return poles


def assign_devices(rng: random.Random, poles: list[GenPole], coverage: float = 0.91) -> None:
    for pole in poles:
        if rng.random() > coverage:
            continue
        n = pole.pole_id.split("-")[-1]
        pole.device_id = f"KSPDB-SD07-{pole.dt_id}-{n}"
        # ~8% of fleet on fw 1.2.x (no power_lost)
        pole.firmware = "1.2.4" if rng.random() < 0.08 else rng.choice(["1.3.1", "1.4.0", "1.4.2"])


def apply_registry_gaps(rng: random.Random, blueprint: NetworkBlueprint, known_frac: float = 0.40) -> None:
    """
    ~60% of DTs lose recorded parents (digitization gap).
    We geo-infer parents for those; true_parent_id stays as ground truth.
    """
    for dt in blueprint.dts:
        dt_poles = [p for p in blueprint.poles if p.dt_id == dt.dt_id]
        if rng.random() < known_frac:
            dt.wiring_known = True
            for p in dt_poles:
                p.parent_id = p.true_parent_id
                p.topology_source = "recorded"
            continue

        dt.wiring_known = False
        pins = [PolePin(p.pole_id, p.lat, p.lon) for p in dt_poles]
        inferred = infer_parents(dt.lat, dt.lon, pins)
        for p in dt_poles:
            p.parent_id = inferred.get(p.pole_id)
            p.seq_on_line = None  # registry blank
            p.topology_source = "inferred"

    # ~3% missing PIN
    for p in blueprint.poles:
        if rng.random() < 0.03:
            p.pincode = None


def generate_network(
    seed: int = 7,
    feeder_count: int = 4,
    dt_count: int = 48,
    target_poles: int = 3200,
) -> NetworkBlueprint:
    rng = random.Random(seed)
    bp = NetworkBlueprint()

    for i in range(feeder_count):
        fid = f"F-07-{i + 1:02d}"
        bp.feeders.append(GenFeeder(feeder_id=fid, name=f"Feeder {i + 1}"))

    # Spread DTs across feeders
    poles_left = target_poles
    dts_left = dt_count
    pole_counter = 1

    for d_i in range(dt_count):
        feeder = bp.feeders[d_i % feeder_count]
        # Vary line size; last DT takes remainder
        if dts_left == 1:
            n_poles = max(12, poles_left)
        else:
            share = poles_left / dts_left
            n_poles = int(rng.uniform(share * 0.55, share * 1.45))
            n_poles = max(12, min(120, n_poles))
        poles_left -= n_poles
        dts_left -= 1

        # Place DT in a loose grid with jitter
        row, col = divmod(d_i, 8)
        base_lat, base_lon = offset_lat_lon(
            ORIGIN_LAT,
            ORIGIN_LON,
            north_m=row * 450 + rng.uniform(-80, 80),
            east_m=col * 450 + rng.uniform(-80, 80),
        )
        dt_id = f"D-{d_i + 1:04d}"
        ward = f"W-{(d_i % 40) + 1:03d}"
        pin = PINCODES[d_i % len(PINCODES)]

        dt = GenDT(
            dt_id=dt_id,
            feeder_id=feeder.feeder_id,
            lat=base_lat,
            lon=base_lon,
            capacity_kva=rng.choice([100, 160, 250, 315]),
            households=int(n_poles * rng.uniform(4.5, 7.0)),
            wiring_known=False,
        )
        bp.dts.append(dt)

        tree = _build_dt_tree(
            rng,
            feeder.feeder_id,
            dt_id,
            base_lat,
            base_lon,
            n_poles,
            pole_counter,
            ward,
            pin,
        )
        pole_counter += len(tree)
        bp.poles.extend(tree)

    assign_devices(rng, bp.poles)
    apply_registry_gaps(rng, bp)
    return bp
