"""In-memory adjacency for localization. Built from parent_id (not true_parent_id)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DistributionTransformer, Pole


@dataclass
class DtTree:
    dt_id: str
    feeder_id: str
    wiring_known: bool
    # parent_id -> children (None key = direct under DT)
    children: dict[str | None, list[str]] = field(default_factory=dict)
    parent_of: dict[str, str | None] = field(default_factory=dict)
    pole_ids: list[str] = field(default_factory=list)


class TopologyIndex:
    def __init__(self) -> None:
        self.by_dt: dict[str, DtTree] = {}
        self.pole_to_dt: dict[str, str] = {}

    def clear(self) -> None:
        self.by_dt.clear()
        self.pole_to_dt.clear()

    def load(self, db: Session) -> None:
        self.clear()
        dts = db.scalars(select(DistributionTransformer)).all()
        poles = db.scalars(select(Pole)).all()

        for dt in dts:
            self.by_dt[dt.id] = DtTree(
                dt_id=dt.id,
                feeder_id=dt.feeder_id,
                wiring_known=dt.wiring_known,
            )

        for pole in poles:
            tree = self.by_dt.get(pole.dt_id)
            if tree is None:
                continue
            tree.pole_ids.append(pole.id)
            tree.parent_of[pole.id] = pole.parent_id
            tree.children.setdefault(pole.parent_id, []).append(pole.id)
            self.pole_to_dt[pole.id] = pole.dt_id

    def descendants(self, dt_id: str, root_pole: str) -> list[str]:
        tree = self.by_dt[dt_id]
        out: list[str] = []
        stack = [root_pole]
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(tree.children.get(cur, []))
        return out


_index = TopologyIndex()


def get_topology() -> TopologyIndex:
    return _index


def refresh_topology(db: Session) -> TopologyIndex:
    _index.load(db)
    return _index
