"""Active-Passive CDP node reader with automatic failover.

The system monitors two CDP nodes over network mounts:

* CDP1 (172.70.55.162, /mnt/cdp1_logs/) - active
* CDP2 (172.70.55.163, /mnt/cdp2_logs/) - passive

Failover rules:
- Normal operation reads exclusively from the active node.
- If the active node becomes unreachable (probe timeout / I/O error), the
  passive node is promoted to active and becomes the reader source.
- When the original active node recovers, it stays passive until the
  current active fails (no flapping).
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


async def _probe_host(ip: str, timeout: float) -> tuple[bool, Optional[float], Optional[str]]:
    """Probe a CDP host using TCP connects to known service ports."""
    attempts = [(2049, "NFS mount port"), (22, "SSH port")]
    for port, label in attempts:
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
            last_error = f"{label}: {exc}"
    return False, None, last_error


async def _check_mount_path(mount_path: str, timeout: float) -> tuple[bool, Optional[str]]:
    """Verify the network mount path is present and listable."""
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
        ok_host, rtt_ms, err = await _probe_host(node.ip, settings.connectivity_timeout_seconds)
        ok_mount, mount_err = await _check_mount_path(
            node.mount_path, settings.connectivity_timeout_seconds
        )
        reachable = ok_host and ok_mount
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

        Expected layout:
            <mount_path>/oneminute/<site_prefix><YYYYMMDDHHMM>.OneMinute.dat
        """
        active = self.state.active_node()
        if active is None:
            return None
        ts_str = ts.strftime("%Y%m%d%H%M")
        return Path(active.mount_path) / "oneminute" / f"{site_prefix}{ts_str}.OneMinute.dat"

    def resolve_raw_sensor_file(self, site_prefix: str, ts: datetime) -> Optional[Path]:
        """Resolve the raw DCP file path for a site on the active node.

        Expected layout:
            <mount_path>/sensor/<site_prefix><YYYYMMDD>.dat
        """
        active = self.state.active_node()
        if active is None:
            return None
        ts_str = ts.strftime("%Y%m%d")
        return Path(active.mount_path) / "sensor" / f"{site_prefix}{ts_str}.dat"

    def active_node_name(self) -> Optional[str]:
        return self.state.active_name