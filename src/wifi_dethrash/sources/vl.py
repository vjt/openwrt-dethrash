import json
import re
from dataclasses import dataclass
from datetime import datetime

import httpx

_MSG_RE = re.compile(
    r"(?:[\w-]+): AP-STA-(CONNECTED|DISCONNECTED) "
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


class VictoriaLogsClient:
    def __init__(self, base_url: str, hostname_field: str = "tags.hostname"):
        self._base_url = base_url.rstrip("/")
        self._hostname_field = hostname_field
        self._client = httpx.Client(timeout=30)

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
            row = json.loads(line)
            msg = row.get("_msg", "")
            m = _MSG_RE.search(msg)
            if not m:
                continue
            events.append(HostapdEvent(
                event=m.group(1).lower(),
                mac=m.group(2).lower(),
                ap=row.get(self._hostname_field, ""),
                time=row["_time"],
                auth_alg=m.group(3),
            ))

        events.sort(key=lambda e: e.time)
        return events
