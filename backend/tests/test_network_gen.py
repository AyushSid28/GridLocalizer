"""Generator invariants — no DB required."""

from collections import Counter

from app.services.network_gen import generate_network
from app.services.topology import PolePin, infer_parents


def test_network_shape():
    bp = generate_network(seed=7, feeder_count=4, dt_count=48, target_poles=3200)

    assert len(bp.feeders) == 4
    assert len(bp.dts) == 48
    assert 2500 <= len(bp.poles) <= 4500

    # Radial: each pole has at most one true parent; no cycles.
    by_id = {p.pole_id: p for p in bp.poles}
    for p in bp.poles:
        seen = set()
        cur = p.pole_id
        while True:
            assert cur not in seen
            seen.add(cur)
            parent = by_id[cur].true_parent_id
            if parent is None:
                break
            assert parent in by_id
            assert by_id[parent].dt_id == p.dt_id
            cur = parent


def test_coverage_and_gaps():
    bp = generate_network(seed=7)
    n = len(bp.poles)
    with_device = sum(1 for p in bp.poles if p.device_id)
    assert 0.85 <= with_device / n <= 0.96

    known = sum(1 for d in bp.dts if d.wiring_known)
    assert 0.25 <= known / len(bp.dts) <= 0.55

    fw12 = sum(1 for p in bp.poles if p.firmware and p.firmware.startswith("1.2"))
    devices = sum(1 for p in bp.poles if p.device_id)
    assert 0.03 <= fw12 / devices <= 0.15

    missing_pin = sum(1 for p in bp.poles if p.pincode is None)
    assert missing_pin / n < 0.08


def test_inferred_vs_recorded():
    bp = generate_network(seed=7)
    for p in bp.poles:
        if p.topology_source == "recorded":
            assert p.parent_id == p.true_parent_id
            assert p.seq_on_line is not None
        elif p.topology_source == "inferred":
            assert p.seq_on_line is None
            # parent_id None means the pole hangs directly off the DT.

    # Every inferred DT still got a full parent map covering its poles.
    for dt in bp.dts:
        if dt.wiring_known:
            continue
        dt_poles = [p for p in bp.poles if p.dt_id == dt.dt_id]
        assert len(dt_poles) == len({p.pole_id for p in dt_poles})
        # At least one pole attaches to the DT (parent None)
        assert any(p.parent_id is None for p in dt_poles)


def test_infer_parents_connects_all():
    pins = [
        PolePin("a", 12.0, 77.0),
        PolePin("b", 12.0003, 77.0),
        PolePin("c", 12.0006, 77.0),
    ]
    parents = infer_parents(11.9997, 77.0, pins)
    assert set(parents) == {"a", "b", "c"}
    # Closest to DT should hang directly off DT (parent None)
    assert parents["a"] is None


def test_unique_ids():
    bp = generate_network(seed=3)
    assert len({p.pole_id for p in bp.poles}) == len(bp.poles)
    assert len({d.dt_id for d in bp.dts}) == len(bp.dts)
    device_ids = [p.device_id for p in bp.poles if p.device_id]
    assert len(device_ids) == len(set(device_ids))
    # Each DT has poles
    counts = Counter(p.dt_id for p in bp.poles)
    assert all(c >= 12 for c in counts.values())
