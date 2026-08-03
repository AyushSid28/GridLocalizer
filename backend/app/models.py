import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TopologySource(str, enum.Enum):
    recorded = "recorded"
    inferred = "inferred"
    none = "none"


class FaultKind(str, enum.Enum):
    span = "span"
    dt = "dt"
    feeder = "feeder"
    sensor = "sensor"


class TicketStatus(str, enum.Enum):
    detected = "detected"
    acknowledged = "acknowledged"
    crew_assigned = "crew_assigned"
    resolved = "resolved"
    verified = "verified"
    closed = "closed"


class Feeder(Base):
    __tablename__ = "feeders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))


class DistributionTransformer(Base):
    __tablename__ = "distribution_transformers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    feeder_id: Mapped[str] = mapped_column(ForeignKey("feeders.id"), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    capacity_kva: Mapped[int] = mapped_column(Integer, default=250)
    households: Mapped[int] = mapped_column(Integer, default=0)
    # True when parent_pole_id came from the registry, not geography.
    wiring_known: Mapped[bool] = mapped_column(Boolean, default=False)

    poles: Mapped[list["Pole"]] = relationship(back_populates="dt")


class Pole(Base):
    __tablename__ = "poles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    feeder_id: Mapped[str] = mapped_column(ForeignKey("feeders.id"), index=True)
    dt_id: Mapped[str] = mapped_column(ForeignKey("distribution_transformers.id"), index=True)
    # What localization walks. Recorded or geo-inferred.
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # Ground-truth parent for the simulator (may differ when wiring was inferred).
    true_parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    seq_on_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ward: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    topology_source: Mapped[TopologySource] = mapped_column(
        Enum(TopologySource, native_enum=False), default=TopologySource.none
    )

    dt: Mapped[DistributionTransformer] = relationship(back_populates="poles")
    state: Mapped["PoleState | None"] = relationship(back_populates="pole", uselist=False)


class PoleState(Base):
    """What we currently believe about a pole's energization."""

    __tablename__ = "pole_states"

    pole_id: Mapped[str] = mapped_column(ForeignKey("poles.id"), primary_key=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(16), nullable=True)
    energized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_seq: Mapped[int] = mapped_column(Integer, default=-1)
    last_event: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_power_restored_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_power_restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_boot_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_boot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    battery_mv: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # offline = modem/device problems, not necessarily dark line
    suspect_sensor: Mapped[bool] = mapped_column(Boolean, default=False)

    pole: Mapped[Pole] = relationship(back_populates="state")


class ScheduledOutage(Base):
    __tablename__ = "scheduled_outages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))  # feeder | dt
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(256))


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[FaultKind] = mapped_column(Enum(FaultKind, native_enum=False))
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, native_enum=False),
        default=TicketStatus.detected,
        index=True,
    )

    feeder_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dt_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Span endpoints when kind == span
    span_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    span_to: Mapped[str | None] = mapped_column(String(32), nullable=True)

    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)

    affected_poles: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[list] = mapped_column(JSONB, default=list)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    topology_mode: Mapped[str] = mapped_column(String(32), default="recorded")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    crew_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verify_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProcessedEvent(Base):
    """Dedup ledger for (device_id, seq)."""

    __tablename__ = "processed_events"
    __table_args__ = (UniqueConstraint("device_id", "seq", name="uq_device_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    pole_id: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
