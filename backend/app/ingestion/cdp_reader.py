"""Active-Passive CDP node reader with live liveness probing.

CDP status = INSTANT network reachability, NOT the oneminute folder:

- ``_probe_host`` sends a short TCP connect to common AWOS CDP ports
  (80 HTTP, 443 HTTPS, 22 SSH, 2049 NFS); the first port that opens
  marks the node ONLINE. This is effectively a network-level ping that
  works from inside a container without root for ICMP.
- The mount path (``/mnt/cdpX_logs``) is NOT part of liveness — the
  oneminute folder is used only for the historical SLA/OLa backfill.
- The worker probes every ``cdps_check_interval_seconds`` and persists a
  ``cdp_connectivity`` row per probe for SLA history.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class NodeState:
    """Runtime state of a single CDP node."""

    cdp_id: int
    name: str
    ip: str
    mount_path: str
    role: str  # 'active' | 'passive'
    reachable: bool = False
    last_check: Optional[datetime] = None
    last_rtt_ms: Optional[float] = None
    consecutive_failures: int = 0
    error_message: Optional[str] = None


@dataclass
class CdpReaderState:
    """Shared mutable state across the active-passive pair."""

    nodes: dict[str, NodeState] = field(default_factory=dict)
    active_name: Optional[str] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def active_node(self) -> Optional[NodeState]:
        if self.active_name is None:
            return None
        return self.nodes.get(self.active_name)


# Ports probed for a live TCP connect. 80 (HTTP webserver) first since the
# user asked for port 80; SSH/NFS are common on the AWS unit.
PROBE_PORTS = [80, 443, 22, 2049]


async def _probe_host(ip: str, timeout: float) -> tuple[bool, Optional[float], Optional[str]]:
    """Live CDP reachability: ICMP ping first, TCP-connect fallback.

    The host operator can always `ping` the CDPs, so we mirror that with the
    system ping binary (works from inside the container even when TCP ports
    80/443/22/2049 are firewalled). If ping is unavailable, fall back to
    trying the probe ports.
    """
    import shutil

    # 1) ICMP ping (system binary) - matches the host's reachability.
    if shutil.which("ping"):
        try:
            start = asyncio.get_event_loop().time()
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "ping", "-c", "1", "-W", str(max(1, int(timeout))), ip,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                ),
                timeout=timeout + 1.0,
            )
            rc = await proc.wait()
            if rc == 0:
                rtt_ms = (asyncio.get_event_loop().time() - start) * 1000.0
                return True, round(rtt_ms, 2), None
        except (OSError, asyncio.TimeoutError):
            pass

    # 2) TCP connect fallback: first open port wins.
    last_error = "no probe ports configured"
    for port in PROBE_PORTS:
        try:
            start = asyncio.get_event_loop().time()
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=timeout
            )
            rtt_ms = (asyncio.get_event_loop().time() - start) * 1000.0
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True, round(rtt_ms, 2), None
        except (asyncio.TimeoutError, OSError) as exc:
            last_error = f"port {port}: {exc}"
    return False, None, last_error


async def _check_mount_path(mount_path: str, timeout: float) -> tuple[bool, Optional[str]]:
    """Verify the network mount path exists INSIDE the container.

    Informational only — the mount is for reading oneminute logs and is
    NOT part of live CDP reachability.
    """
    try:
        path = Path(mount_path)
        if not path.exists():
            return False, f"mount path not found: {mount_path}"
        _ = await asyncio.wait_for(
            asyncio.to_thread(lambda: list(path.iterdir())), timeout=timeout
        )
        return True, None
    except (OSError, asyncio.TimeoutError) as exc:
        return False, f"mount read error: {exc}"


class CdpReader:
    """Manages active-passive failover across both CDP nodes."""

    def __init__(self, nodes: list[dict]):
        self.state = CdpReaderState()
        for n in nodes:
            node = NodeState(
                cdp_id=n["id"],
                name=n["name"],
                ip=str(n["ip_address"]),
                mount_path=n["mount_path"],
                role=n.get("role", "passive"),
            )
            self.state.nodes[n["name"]] = node

        # Initial active = configured role == 'active'
        for node in self.state.nodes.values():
            if node.role == "active":
                self.state.active_name = node.name
                break
        if self.state.active_name is None and self.state.nodes:
            self.state.active_name = next(iter(self.state.nodes))
            self.state.nodes[self.state.active_name].role = "active"

    # ------------------------------------------------------------------
    async def check_all(self) -> list[NodeState]:
        """Probe all nodes concurrently and apply failover rules."""
        async with self.state.lock:
            results = await asyncio.gather(
                *[self._check_node(node) for node in self.state.nodes.values()]
            )
            # Failover if active node is down
            active = self.state.active_node()
            if active is not None and not active.reachable:
                self._promote_passive()
            return results

    async def _check_node(self, node: NodeState) -> NodeState:
        # INSTANT liveness = network probe only (ports 80/443/22/2049).
        ok_host, rtt_ms, err = await _probe_host(
            node.ip, settings.connectivity_timeout_seconds
        )

        # Mount check is informational only (for debugging log availability).
        ok_mount, mount_err = await _check_mount_path(
            node.mount_path, settings.connectivity_timeout_seconds
        )

        reachable = ok_host
        node.last_check = datetime.now(timezone.utc)
        node.last_rtt_ms = rtt_ms
        node.error_message = err or mount_err

        if reachable:
            node.reachable = True
            node.consecutive_failures = 0
        else:
            node.reachable = False
            node.consecutive_failures += 1
        return node

    def _promote_passive(self) -> None:
        """Promote the healthiest passive node to active."""
        candidates = [
            n for n in self.state.nodes.values() if n.name != self.state.active_name
        ]
        if not candidates:
            return
        # Prefer the node with fewer consecutive failures
        best = min(candidates, key=lambda n: (n.consecutive_failures, n.name))
        old_active = self.state.active_name
        best.role = "active"
        if old_active and old_active in self.state.nodes:
            self.state.nodes[old_active].role = "passive"
        self.state.active_name = best.name
        logger.warning(
            "CDP failover: %s (down) -> %s (active)", old_active, best.name
        )

    # ------------------------------------------------------------------
    def resolve_site_file(self, site_prefix: str, ts: datetime) -> Optional[Path]:
        """Resolve the 1-minute log file path for a site on the active node.

        Real layout observed on CDP1/CDP2:
            <mount_path>/oneminute/091OneMinute.<YYYYMMDD>.dat
        The file is *daily*; every data row carries its own minute.
        """
        active = self.state.active_node()
        if active is None:
            return None
        ts_str = ts.strftime("%Y%m%d")
        oneminute_dir = Path(active.mount_path) / "oneminute"
        candidates = [
            oneminute_dir / f"{site_prefix}OneMinute.{ts_str}.dat",
            oneminute_dir / f"{site_prefix}{ts_str}.OneMinute.dat",
        ]
        for path in candidates:
            if path.exists():
                return path
        if oneminute_dir.is_dir():
            matches = [p for p in oneminute_dir.glob(f"*OneMinute.{ts_str}.dat")]
            if matches:
                return matches[0]
        return candidates[0]

    def resolve_raw_sensor_file(self, site_prefix: str, ts: datetime) -> Optional[Path]:
        """Raw DCP files are not used as a data source."""
        return self.resolve_site_file(site_prefix, ts)

    def active_node_name(self) -> Optional[str]:
        return self.state.active_name