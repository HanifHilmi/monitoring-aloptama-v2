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
    symbol: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    station: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    component: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_state: Mapped[bool] = mapped_column(Boolean, default=False)
    chart_metrics: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))

    site: Mapped[Site] = relationship(back_populates="sensors")


class Telemetry(Base):
    __tablename__ = "telemetry"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"), primary_key=True)
    metric: Mapped[str] = mapped_column(String, primary_key=True, default="value")
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    text_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="ok")
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
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
    cdp_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)    # 0 = not applicable (OLA)
    sensor_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)  # 0 = not applicable (SLA)
    site_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_seconds: Mapped[int] = mapped_column(BigInteger)
    uptime_seconds: Mapped[int] = mapped_column(BigInteger)
    downtime_seconds: Mapped[int] = mapped_column(BigInteger)
    uptime_pct: Mapped[float] = mapped_column(Float)
    open_events: Mapped[int] = mapped_column(Integer, default=0)
    closed_events: Mapped[int] = mapped_column(Integer, default=0)


class AwosMetrics(Base):
    """Wide-columnar 1-minute observations (one row per (time, site_id)).

    Mirrors migration 009. PK (time, site_id) enables idempotent
    ON CONFLICT upserts and TimescaleDB columnar compression by site.
    """
    __tablename__ = "awos_metrics"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dewp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rh_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    qnh_hpa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    da_ft: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_speed_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_dir_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gust_speed_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gust_dir_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rvr_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vis_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    als_cd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    als_dn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rls: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lr1_100ft: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sky_condition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    precip_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    present_weather: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    solar_wm2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lightning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_line: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
