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


@dataclass(frozen=True)
class HostapdEvent:
    event: str       # "connected" or "disconnected"
    mac: str
    ap: str
    time: str        # ISO 8601
    auth_alg: str | None = None  # "ft", "open", or None (disconnects)
    ifname: str | None = None    # e.g. "phy1-ap0"


class VictoriaLogsClient:
    def __init__(self, base_url: str, hostname_field: str = "tags.hostname",
                 station_field: str = "station"):
        self._base_url = base_url.rstrip("/")
        self._hostname_field = hostname_field
        self._station_field = station_field
        self._vl_station_field = f"fields.{station_field}"
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

    def fetch_wifi_stations(self, limit: int = 10000) -> tuple[dict[str, str], list[str]]:
        """Extract MAC→hostname mapping and station list from hostapd events.

        Parses AP-STA-CONNECTED events that have the station field (set by
        station-resolver, field name configurable). Returns (mac_names,
        station_list) where:
        - mac_names: lowercase MAC → hostname for Prometheus label_map
        - station_list: sorted unique hostnames for the dropdown
        Only includes actual WiFi clients, not all DHCP leases.
        """
        resp = self._client.get(
            f"{self._base_url}/select/logsql/query",
            params={
                "query": (
                    f"tags.appname:hostapd AND _msg:AP-STA-CONNECTED"
                    f" AND {self._vl_station_field}:*"
                ),
                "limit": str(limit),
            },
        )
        resp.raise_for_status()

        # MAC regex: 17-char colon-separated hex
        mac_re = re.compile(r"AP-STA-CONNECTED ([0-9a-fA-F:]{17})")

        names: dict[str, str] = {}
        for line in resp.text.strip().split("\n"):
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            station = row.get(self._vl_station_field) or row.get(self._station_field, "")
            if not station:
                continue

            m = mac_re.search(row.get("_msg", ""))
            if m:
                names[m.group(1).lower()] = station

        stations = sorted(set(names.values()), key=str.lower)
        return names, stations
