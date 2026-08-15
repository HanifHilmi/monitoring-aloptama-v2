"""Pydantic response schemas for the REST API."""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------------
# Site / Sensor
# ----------------------------------------------------------------------
class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    unit: Optional[str] = None
    min_valid: Optional[float] = None
    max_valid: Optional[float] = None
    is_enabled: bool


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    slug: str
    file_prefixes: list[str] = Field(default_factory=list)
    sensors: list[SensorOut] = Field(default_factory=list)


class CdpNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ip_address: str
    mount_path: str
    is_active: bool
    role: str
    status: str


# ----------------------------------------------------------------------
# Telemetry
# ----------------------------------------------------------------------
class TelemetryPoint(BaseModel):
    time: datetime
    value: Optional[float] = None
    status: str


class TelemetrySeries(BaseModel):
    sensor_id: int
    site_code: str
    sensor_code: str
    sensor_name: str
    unit: Optional[str] = None
    status: str
    points: list[TelemetryPoint] = Field(default_factory=list)


class TelemetryCurrent(BaseModel):
    site_code: str
    site_name: str
    sensors: list[dict[str, Any]] = Field(default_factory=list)


# ----------------------------------------------------------------------
# Live status
# ----------------------------------------------------------------------
class SensorLiveStatus(BaseModel):
    sensor_id: int
    code: str
    name: str
    category: str
    unit: Optional[str] = None
    status: str
    last_value: Optional[float] = None
    last_time: Optional[datetime] = None
    age_seconds: Optional[int] = None


class SiteLiveStatus(BaseModel):
    site_id: int
    code: str
    name: str
    slug: str
    overall: str
    sensors: list[SensorLiveStatus] = Field(default_factory=list)


class CdpLiveStatus(BaseModel):
    cdp_id: int
    name: str
    ip: str
    role: str
    status: str
    last_check: Optional[datetime] = None
    last_rtt_ms: Optional[float] = None


class LiveStatusResponse(BaseModel):
    generated_at: datetime
    cdps: list[CdpLiveStatus] = Field(default_factory=list)
    sites: list[SiteLiveStatus] = Field(default_factory=list)


# ----------------------------------------------------------------------
# SLA / OLA
# ----------------------------------------------------------------------
class SlaOlaRollup(BaseModel):
    weo_time: date
    scope_type: str
    entity_type: str
    site_id: Optional[int] = None
    site_code: Optional[str] = None
    entity_name: Optional[str] = None
    cdp_id: Optional[int] = None
    sensor_id: Optional[int] = None
    total_seconds: int
    uptime_seconds: int
    downtime_seconds: int
    uptime_pct: float
    open_events: int
    closed_events: int


class SlaOlaSummary(BaseModel):
    period_start: date
    period_end: date
    scope_type: str
    rows: list[SlaOlaRollup] = Field(default_factory=list)


# ----------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    time: datetime