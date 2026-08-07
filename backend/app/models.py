"""SQLAlchemy ORM models mirroring the TimescaleDB schema."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class CdpNode(Base):
    __tablename__ = "cdp_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    ip_address: Mapped[str] = mapped_column(INET)
    mount_path: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String, default="passive")
    status: Mapped[str] = mapped_column(String, default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True)
    file_prefixes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    sensors: Mapped[list["Sensor"]] = relationship(back_populates="site", cascade="all, delete-orphan")


class Sensor(Base):
    __tablename__ = "sensors"
    __table_args__ = (UniqueConstraint("site_id", "code", name="uq_sensor_site_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    unit: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    min_valid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_valid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    fallback_slice: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    site: Mapped[Site] = relationship(back_populates="sensors")


class Telemetry(Base):
    __tablename__ = "telemetry"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"), primary_key=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="ok")
    raw_line: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CdpConnectivity(Base):
    __tablename__ = "cdp_connectivity"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    cdp_id: Mapped[int] = mapped_column(ForeignKey("cdp_nodes.id", ondelete="CASCADE"), primary_key=True)
    reachable: Mapped[bool] = mapped_column(Boolean)
    rtt_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DowntimeEvent(Base):
    __tablename__ = "downtime_events"
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'sla' AND cdp_id IS NOT NULL AND sensor_id IS NULL) OR "
            "(scope_type = 'ola' AND sensor_id IS NOT NULL AND cdp_id IS NULL)",
            name="ck_downtime_scope_entity",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    cdp_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cdp_nodes.id", ondelete="CASCADE"), nullable=True)
    sensor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"), nullable=True)
    site_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reason_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


class DailySlaOla(Base):
    __tablename__ = "daily_sla_ola"

    weo_time: Mapped[date] = mapped_column(Date, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, primary_key=True)
    cdp_id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, nullable=True)
    sensor_id: Mapped[Optional[int]] = mapped_column(Integer, primary_key=True, nullable=True)
    site_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_seconds: Mapped[int] = mapped_column(BigInteger)
    uptime_seconds: Mapped[int] = mapped_column(BigInteger)
    downtime_seconds: Mapped[int] = mapped_column(BigInteger)
    uptime_pct: Mapped[float] = mapped_column(Float)
    open_events: Mapped[int] = mapped_column(Integer, default=0)
    closed_events: Mapped[int] = mapped_column(Integer, default=0)