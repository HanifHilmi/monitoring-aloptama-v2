"""Application configuration - loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. All values overridable via env vars."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- App ----
    app_name: str = "Monitoring Aloptama V2"
    app_version: str = "2.0.0"
    # Coolify / Docker often inject ENVIRONMENT with arbitrary values
    # (e.g. "prod", "production", "staging", "Development", ""). Accept any
    # string so a strict enum never crashes startup (crash-loop protection).
    environment: str = "production"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # ---- Database ----
    database_url: str = (
        "postgresql+asyncpg://monitor:monitor@localhost:5432/monitoring_aloptama"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True

    # ---- CDP network nodes ----
    cdp1_ip: str = "172.22.39.162"
    cdp1_mount_path: str = "/mnt/cdp1_logs/"
    cdp2_ip: str = "172.22.39.163"
    cdp2_mount_path: str = "/mnt/cdp2_logs/"

    # ---- Ingestion ----
    ingestion_interval_seconds: int = 60
    active_check_interval_seconds: int = 10
    cdps_check_interval_seconds: int = 30
    connectivity_timeout_seconds: float = 5.0
    backfill_start: str = "2026-01-01T00:00:00Z"
    backfill_batch_days: int = 1
    # Backfill is triggered manually from the dashboard Settings -> Backfill
    # (CDP uptime and DCP data). We do NOT backfill automatically on boot.
    enable_backfill_on_boot: bool = False
    enable_migrations_on_boot: bool = True
    telemetry_stale_after_minutes: int = 5

    # ---- SLA/OLA rollup ----
    rollup_interval_minutes: int = 5

    # ---- CORS / frontend ----
    cors_origins: list[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # ---- LTTB downsample ----
    lttb_default_threshold: int = 1000


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()