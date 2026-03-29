import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

import httpx

log = logging.getLogger(__name__)

_MSG_RE = re.compile(
    r"([\w-]+): AP-STA-(CONNECTED|DISCONNECTED) "
    r"([0-9a-fA-F:]{17})"
    r"(?: auth_alg=(\w+))?"
)

# dnsmasq: DHCPACK(br-lan) 192.168.42.41 84:2f:57:07:9e:3d enterprise
_DNSMASQ_DHCP_RE = re.compile(
    r"DHCPACK\(\S+\)\s+\S+\s+([0-9a-fA-F:]{17})\s+(\S+)"
)

# Technitium: DHCP Server leased IP address [192.168.42.41] to enterprise [84-2F-57-07-9E-3D]
_TECHNITIUM_DHCP_RE = re.compile(
    r"DHCP Server leased IP address \[(\S+)\] to (\S+) \[([0-9a-fA-F-]{17})\]"
)


@dataclass(frozen=True)
class HostapdEvent:
    event: str       # "connected" or "disconnected"
    mac: str
    ap: str
    time: str        # ISO 8601
    auth_alg: str | None = None  # "ft", "open", or None (disconnects)
    ifname: str | None = None    # e.g. "phy1-ap0"


class VictoriaLogsClient:
    def __init__(self, base_url: str, hostname_field: str = "tags.hostname"):
        self._base_url = base_url.rstrip("/")
        self._hostname_field = hostname_field
        self._client = httpx.Client(timeout=30)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def fetch_events(
        self,
        start: datetime,
        end: datetime,
        macs: list[str] | None = None,
        limit: int = 50000,
    ) -> list[HostapdEvent]:
        """Fetch hostapd connect/disconnect events from VictoriaLogs."""
        query = 'tags.appname:hostapd AND _msg:AP-STA-'
        if macs:
            mac_filter = " OR ".join(f'_msg:"{m}"' for m in macs)
            query = f'{query} AND ({mac_filter})'

        resp = self._client.get(
            f"{self._base_url}/select/logsql/query",
            params={
                "query": query,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": str(limit),
            },
        )
        resp.raise_for_status()

        events = []
        for line in resp.text.strip().split("\n"):
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                log.warning("Skipping malformed JSONL line: %s", line[:200])
                continue
            msg = row.get("_msg", "")
            m = _MSG_RE.search(msg)
            if not m:
                continue
            events.append(HostapdEvent(
                event=m.group(2).lower(),
                mac=m.group(3).lower(),
                ap=row.get(self._hostname_field, ""),
                time=row["_time"],
                auth_alg=m.group(4),
                ifname=m.group(1),
            ))

        events.sort(key=lambda e: e.time)
        return events

    def fetch_mac_names(self, limit: int = 10000) -> dict[str, str]:
        """Resolve MAC addresses to hostnames from DHCP logs.

        Parses both Technitium and dnsmasq DHCP log formats.
        Prefers DNS reverse lookup (authoritative name) over DHCP
        client-provided hostname when IP is available.
        Returns dict mapping lowercase colon-separated MAC to hostname.
        """
        import socket

        resp = self._client.get(
            f"{self._base_url}/select/logsql/query",
            params={
                "query": (
                    "(tags.appname:docker AND _msg:\"DHCP Server leased\")"
                    " OR "
                    "(tags.appname:dnsmasq-dhcp AND _msg:DHCPACK)"
                ),
                "limit": str(limit),
            },
        )
        resp.raise_for_status()

        names: dict[str, str] = {}
        mac_ips: dict[str, str] = {}
        for line in resp.text.strip().split("\n"):
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = row.get("_msg", "")

            # Technitium: DHCP Server leased IP address [ip] to hostname [AA-BB-CC-DD-EE-FF]
            m = _TECHNITIUM_DHCP_RE.search(msg)
            if m:
                ip = m.group(1)
                hostname = m.group(2)
                mac = m.group(3).replace("-", ":").lower()
                names[mac] = hostname
                mac_ips[mac] = ip
                continue

            # dnsmasq: DHCPACK(br-lan) ip aa:bb:cc:dd:ee:ff hostname
            m = _DNSMASQ_DHCP_RE.search(msg)
            if m:
                mac = m.group(1).lower()
                hostname = m.group(2)
                names[mac] = hostname

        # Prefer DNS reverse lookup over DHCP client hostname
        for mac, ip in mac_ips.items():
            try:
                dns_name = socket.gethostbyaddr(ip)[0]
                # Strip domain suffix for display
                short = dns_name.split(".")[0]
                if short:
                    names[mac] = short
            except (socket.herror, OSError):
                pass

        return names
