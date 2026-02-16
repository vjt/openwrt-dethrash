# wifi-dethrash Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use 10x-engineer:executing-plans to implement this plan task-by-task.

**Goal:** Offline WiFi mesh analyzer that detects AP thrashing and weak associations from historical metrics/logs, recommends txpower and usteer UCI settings, and optionally generates a Grafana dashboard for before/after validation.

**Architecture:** Standalone Python CLI that queries VictoriaMetrics (RSSI, noise, station metrics) and VictoriaLogs (hostapd connect/disconnect events) over configurable time windows. Discovers APs automatically from metric labels. Produces a terminal report with copy-pasteable `ssh root@<hostname> uci set ...` commands. Separate `--generate-dashboard` flag writes a Grafana JSON file for one-time import.

**Tech Stack:** Python 3.11+, httpx (async HTTP), click (CLI), pytest

---

## Context

### The problem

In a multi-AP OpenWrt mesh, phones thrash between APs that have overlapping signal coverage — rapid connect/disconnect cycles between two APs with similar RSSI. This happens when TX power is too high (both APs hear the phone equally well) or when usteer thresholds are too permissive (the AP accepts weak associations). Diagnosing this requires correlating RSSI metrics with hostapd logs across multiple APs over time, which nobody does manually.

### Data sources

**VictoriaMetrics** — scraped every 5-10s by Telegraf from `prometheus-node-exporter-lua` on each AP:

| Metric | Labels | What it tells us |
|--------|--------|-----------------|
| `wifi_station_signal_dbm` | `mac`, `ifname` | Per-station RSSI — the core signal |
| `wifi_station_inactive_milliseconds` | `mac`, `ifname` | How long since station last transmitted |
| `wifi_network_noise_dbm` | `device`, `channel`, `frequency`, `ssid` | Noise floor per radio — needed for SNR |
| `node_ethtool_transmitted_retry_failed` | `device` (e.g. `phy0-ap0`) | TX retry failures — link quality indicator |

VictoriaMetrics adds an `instance` label (e.g. `mowgli:9100`) to all metrics scraped via Telegraf. The AP hostname is derived from this label by default (`--host-label` overrides).

**VictoriaLogs** — hostapd syslog events shipped via Telegraf:

| Field | Example | What it tells us |
|-------|---------|-----------------|
| `_msg` | `phy1-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=ft` | Connect event, with auth type |
| `_msg` | `phy1-ap0: AP-STA-DISCONNECTED de:ad:be:ef:00:01` | Disconnect event |
| `tags.hostname` | `pingu` | AP hostname |
| `_time` | `2026-02-16T07:49:56Z` | Event timestamp |

`auth_alg=ft` = 802.11r fast transition roam. `auth_alg=open` = fresh association (not a roam).

### API reference

**VictoriaMetrics query API:**
```
GET /api/v1/query_range?query=wifi_station_signal_dbm&start=<rfc3339>&end=<rfc3339>&step=30s
```
Returns `{"data":{"result":[{"metric":{"mac":"...","ifname":"...","instance":"mowgli:9100"},"values":[[timestamp,"value"],...]}]}}`.

**VictoriaLogs query API:**
```
GET /select/logsql/query?query=tags.appname:hostapd AND _msg:AP-STA-&start=<rfc3339>&end=<rfc3339>&limit=10000
```
Returns JSONL (one JSON object per line), each with `_time`, `_msg`, `tags.hostname`.

### What the analyzer does

1. **Discover APs** — query VictoriaMetrics for `wifi_station_signal_dbm` label values to find all AP instances
2. **Fetch RSSI data** — query `wifi_station_signal_dbm` and `wifi_network_noise_dbm` over the time window
3. **Fetch hostapd events** — query VictoriaLogs for `AP-STA-CONNECTED` and `AP-STA-DISCONNECTED`
4. **Detect thrashing** — find MACs with rapid connect sequences between AP pairs (from logs), cross-reference with RSSI overlap (from metrics)
5. **Detect weak associations** — find stations with sustained low SNR (signal - noise < threshold)
6. **Recommend txpower** — for thrashing AP pairs, suggest reducing power to increase RSSI differentiation
7. **Recommend usteer** — suggest `min_connect_snr` and `min_snr` thresholds based on observed weak associations
8. **Output** — terminal report + `ssh root@<hostname> uci set ...` commands

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/dethrash/__init__.py`
- Create: `src/dethrash/__main__.py`
- Create: `src/dethrash/cli.py`
- Create: `README.md`
- Create: `.gitignore`
- Create: `tests/__init__.py`

### Step 1: Create pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "wifi-dethrash"
version = "0.1.0"
description = "WiFi mesh thrashing analyzer for OpenWrt"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "click>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[project.scripts]
dethrash = "dethrash.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Step 2: Create .gitignore

```
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
build/
.pytest_cache/
```

### Step 3: Create src/dethrash/__init__.py

Empty file.

### Step 4: Create src/dethrash/__main__.py

```python
from dethrash.cli import main

main()
```

### Step 5: Create src/dethrash/cli.py

Minimal CLI skeleton that just parses args and prints a placeholder:

```python
import click


@click.command()
@click.option("--vm-url", required=True, help="VictoriaMetrics base URL")
@click.option("--vl-url", required=True, help="VictoriaLogs base URL")
@click.option("--window", default="24h", help="Time window to analyze (e.g. 1h, 24h, 7d)")
@click.option("--host-label", default="instance", help="Metric label containing AP hostname")
@click.option("--mac", multiple=True, help="Filter to specific MAC address(es)")
@click.option("--generate-dashboard", type=click.Path(), default=None,
              help="Write Grafana dashboard JSON to file and exit")
def main(vm_url, vl_url, window, host_label, mac, generate_dashboard):
    """WiFi mesh thrashing analyzer for OpenWrt."""
    click.echo(f"vm_url={vm_url} vl_url={vl_url} window={window}")
    click.echo("Not implemented yet.")
```

### Step 6: Create README.md

```markdown
# wifi-dethrash

WiFi mesh thrashing analyzer for OpenWrt. Queries VictoriaMetrics and VictoriaLogs
to detect AP thrashing, weak associations, and recommends txpower and usteer settings.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
dethrash --vm-url http://victoriametrics:8428 --vl-url http://victorialogs:9428
```

See `dethrash --help` for all options.
```

### Step 7: Create tests/__init__.py

Empty file.

### Step 8: Set up venv and verify

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
dethrash --help
```

Expected: help text with all options.

### Step 9: Commit

```bash
git add -A && git commit -m "chore: project scaffolding"
```

---

## Task 2: VictoriaMetrics client — AP discovery and RSSI fetching

**Files:**
- Create: `src/dethrash/sources/vm.py`
- Create: `src/dethrash/sources/__init__.py`
- Create: `tests/test_vm.py`

### Step 1: Write failing tests

Create `tests/test_vm.py`:

```python
import pytest
from datetime import datetime, timezone
from dethrash.sources.vm import VictoriaMetricsClient, APInfo, RSSIReading


# --- Fixtures ---

LABEL_VALUES_RESPONSE = {
    "data": ["mowgli:9100", "pingu:9100", "albert:9100"]
}

QUERY_RANGE_RESPONSE = {
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {
                    "mac": "de:ad:be:ef:00:01",
                    "ifname": "phy1-ap0",
                    "instance": "mowgli:9100",
                },
                "values": [
                    [1700000000, "-55"],
                    [1700000030, "-57"],
                ],
            },
            {
                "metric": {
                    "mac": "de:ad:be:ef:00:01",
                    "ifname": "phy1-ap0",
                    "instance": "pingu:9100",
                },
                "values": [
                    [1700000000, "-62"],
                    [1700000030, "-60"],
                ],
            },
        ],
    }
}

NOISE_RESPONSE = {
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {
                    "device": "radio1",
                    "frequency": "5745",
                    "instance": "mowgli:9100",
                },
                "values": [
                    [1700000000, "-92"],
                    [1700000030, "-91"],
                ],
            },
        ],
    }
}


class TestDiscoverAPs:
    def test_extracts_hostnames_from_instance_label(self, respx_mock):
        respx_mock.get(
            "http://vm:8428/api/v1/label/instance/values",
            params={"match[]": "wifi_station_signal_dbm"},
        ).respond(json=LABEL_VALUES_RESPONSE)

        client = VictoriaMetricsClient("http://vm:8428", host_label="instance")
        aps = client.discover_aps()

        assert len(aps) == 3
        assert aps[0].hostname == "mowgli"
        assert aps[0].instance == "mowgli:9100"

    def test_custom_host_label(self, respx_mock):
        respx_mock.get(
            "http://vm:8428/api/v1/label/hostname/values",
            params={"match[]": "wifi_station_signal_dbm"},
        ).respond(json={"data": ["mowgli", "pingu"]})

        client = VictoriaMetricsClient("http://vm:8428", host_label="hostname")
        aps = client.discover_aps()

        assert len(aps) == 2
        assert aps[0].hostname == "mowgli"
        assert aps[0].instance == "mowgli"  # no port stripping needed


class TestFetchRSSI:
    def test_returns_readings_with_ap_and_mac(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=QUERY_RANGE_RESPONSE
        )

        client = VictoriaMetricsClient("http://vm:8428")
        start = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        end = datetime(2023, 11, 14, 22, 14, 20, tzinfo=timezone.utc)
        readings = client.fetch_rssi(start, end)

        assert len(readings) == 4  # 2 series x 2 values each
        r = readings[0]
        assert r.mac == "de:ad:be:ef:00:01"
        assert r.ap == "mowgli"
        assert r.rssi == -55
        assert r.timestamp == 1700000000

    def test_mac_filter(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=QUERY_RANGE_RESPONSE
        )

        client = VictoriaMetricsClient("http://vm:8428")
        start = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        end = datetime(2023, 11, 14, 22, 14, 20, tzinfo=timezone.utc)
        readings = client.fetch_rssi(start, end, macs=["de:ad:be:ef:00:01"])

        # All readings match, so same count — but the query should have a label filter
        assert len(readings) == 4


class TestFetchNoise:
    def test_returns_noise_per_ap_and_radio(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=NOISE_RESPONSE
        )

        client = VictoriaMetricsClient("http://vm:8428")
        start = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        end = datetime(2023, 11, 14, 22, 14, 20, tzinfo=timezone.utc)
        noise = client.fetch_noise(start, end)

        assert len(noise) == 2
        assert noise[0].ap == "mowgli"
        assert noise[0].radio == "radio1"
        assert noise[0].frequency == 5745
        assert noise[0].noise_dbm == -92
```

### Step 2: Run tests — expect FAIL

```bash
.venv/bin/pytest tests/test_vm.py -v
```

Expected: `ModuleNotFoundError: No module named 'dethrash.sources'`

### Step 3: Create conftest.py with respx fixture

Create `tests/conftest.py`:

```python
import pytest
import respx


@pytest.fixture
def respx_mock():
    with respx.mock(assert_all_called=False) as mock:
        yield mock
```

### Step 4: Implement VictoriaMetrics client

Create `src/dethrash/sources/__init__.py` (empty).

Create `src/dethrash/sources/vm.py`:

```python
from dataclasses import dataclass
from datetime import datetime

import httpx


@dataclass(frozen=True)
class APInfo:
    hostname: str
    instance: str


@dataclass(frozen=True)
class RSSIReading:
    mac: str
    ap: str
    ifname: str
    rssi: int
    timestamp: int


@dataclass(frozen=True)
class NoiseReading:
    ap: str
    radio: str
    frequency: int
    noise_dbm: int
    timestamp: int


class VictoriaMetricsClient:
    def __init__(self, base_url: str, host_label: str = "instance"):
        self._base_url = base_url.rstrip("/")
        self._host_label = host_label
        self._client = httpx.Client(timeout=30)

    def _hostname_from_label(self, label_value: str) -> str:
        """Extract hostname from label value. 'mowgli:9100' -> 'mowgli'."""
        return label_value.split(":")[0] if ":" in label_value else label_value

    def discover_aps(self) -> list[APInfo]:
        """Discover APs from metric label values."""
        resp = self._client.get(
            f"{self._base_url}/api/v1/label/{self._host_label}/values",
            params={"match[]": "wifi_station_signal_dbm"},
        )
        resp.raise_for_status()
        values = resp.json()["data"]
        return [
            APInfo(
                hostname=self._hostname_from_label(v),
                instance=v,
            )
            for v in sorted(values)
        ]

    def fetch_rssi(
        self,
        start: datetime,
        end: datetime,
        macs: list[str] | None = None,
        step: str = "30s",
    ) -> list[RSSIReading]:
        """Fetch wifi_station_signal_dbm over time window."""
        query = "wifi_station_signal_dbm"
        if macs:
            mac_re = "|".join(macs)
            query = f'wifi_station_signal_dbm{{mac=~"{mac_re}"}}'

        resp = self._client.get(
            f"{self._base_url}/api/v1/query_range",
            params={
                "query": query,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "step": step,
            },
        )
        resp.raise_for_status()

        readings = []
        for series in resp.json()["data"]["result"]:
            metric = series["metric"]
            ap = self._hostname_from_label(metric.get(self._host_label, ""))
            mac = metric["mac"]
            ifname = metric["ifname"]
            for ts, val in series["values"]:
                readings.append(RSSIReading(
                    mac=mac, ap=ap, ifname=ifname,
                    rssi=int(float(val)), timestamp=int(ts),
                ))
        return readings

    def fetch_noise(
        self,
        start: datetime,
        end: datetime,
        step: str = "30s",
    ) -> list[NoiseReading]:
        """Fetch wifi_network_noise_dbm over time window."""
        resp = self._client.get(
            f"{self._base_url}/api/v1/query_range",
            params={
                "query": "wifi_network_noise_dbm",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "step": step,
            },
        )
        resp.raise_for_status()

        readings = []
        for series in resp.json()["data"]["result"]:
            metric = series["metric"]
            ap = self._hostname_from_label(metric.get(self._host_label, ""))
            radio = metric.get("device", "")
            freq = int(metric.get("frequency", "0"))
            for ts, val in series["values"]:
                readings.append(NoiseReading(
                    ap=ap, radio=radio, frequency=freq,
                    noise_dbm=int(float(val)), timestamp=int(ts),
                ))
        return readings
```

### Step 5: Run tests — expect PASS

```bash
.venv/bin/pytest tests/test_vm.py -v
```

### Step 6: Commit

```bash
git add -A && git commit -m "feat: VictoriaMetrics client — AP discovery, RSSI, noise"
```

---

## Task 3: VictoriaLogs client — hostapd event fetching

**Files:**
- Create: `src/dethrash/sources/vl.py`
- Create: `tests/test_vl.py`

### Step 1: Write failing tests

Create `tests/test_vl.py`:

```python
import pytest
from datetime import datetime, timezone
from dethrash.sources.vl import VictoriaLogsClient, HostapdEvent


JSONL_RESPONSE = (
    '{"_time":"2026-02-16T07:49:56Z","_msg":"phy1-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=ft","tags.hostname":"pingu"}\n'
    '{"_time":"2026-02-16T07:52:47Z","_msg":"phy1-ap0: AP-STA-DISCONNECTED de:ad:be:ef:00:01","tags.hostname":"pingu"}\n'
    '{"_time":"2026-02-16T07:52:48Z","_msg":"phy1-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=open","tags.hostname":"golem"}\n'
)


class TestFetchEvents:
    def test_parses_connect_and_disconnect(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=JSONL_RESPONSE,
        )

        client = VictoriaLogsClient("http://vl:9428")
        start = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 8, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end)

        assert len(events) == 3

        e = events[0]
        assert e.event == "connected"
        assert e.mac == "de:ad:be:ef:00:01"
        assert e.ap == "pingu"
        assert e.auth_alg == "ft"
        assert e.time == "2026-02-16T07:49:56Z"

        e = events[1]
        assert e.event == "disconnected"
        assert e.mac == "de:ad:be:ef:00:01"
        assert e.ap == "pingu"
        assert e.auth_alg is None

        e = events[2]
        assert e.event == "connected"
        assert e.auth_alg == "open"
        assert e.ap == "golem"

    def test_mac_filter(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=JSONL_RESPONSE,
        )

        client = VictoriaLogsClient("http://vl:9428")
        start = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 8, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end, macs=["de:ad:be:ef:00:01"])

        # The query should include a MAC filter — all 3 events match this MAC
        assert len(events) == 3

    def test_custom_hostname_field(self, respx_mock):
        resp_text = '{"_time":"2026-02-16T08:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:ff auth_alg=open","host":"router1"}\n'
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=resp_text,
        )

        client = VictoriaLogsClient("http://vl:9428", hostname_field="host")
        start = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 9, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end)

        assert events[0].ap == "router1"

    def test_sorts_by_time(self, respx_mock):
        # Out of order
        resp_text = (
            '{"_time":"2026-02-16T08:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:ff auth_alg=open","tags.hostname":"b"}\n'
            '{"_time":"2026-02-16T07:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:ff auth_alg=ft","tags.hostname":"a"}\n'
        )
        respx_mock.get("http://vl:9428/select/logsql/query").respond(text=resp_text)

        client = VictoriaLogsClient("http://vl:9428")
        start = datetime(2026, 2, 16, 6, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 9, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end)

        assert events[0].time == "2026-02-16T07:00:00Z"
        assert events[1].time == "2026-02-16T08:00:00Z"
```

### Step 2: Run tests — expect FAIL

```bash
.venv/bin/pytest tests/test_vl.py -v
```

Expected: `ModuleNotFoundError: No module named 'dethrash.sources.vl'`

### Step 3: Implement VictoriaLogs client

Create `src/dethrash/sources/vl.py`:

```python
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
```

### Step 4: Run tests — expect PASS

```bash
.venv/bin/pytest tests/test_vl.py -v
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: VictoriaLogs client — hostapd event fetching"
```

---

## Task 4: Thrashing detector

**Files:**
- Create: `src/dethrash/analyzers/thrashing.py`
- Create: `src/dethrash/analyzers/__init__.py`
- Create: `tests/test_thrashing.py`

### Step 1: Write failing tests

Create `tests/test_thrashing.py`. The thrashing detector takes sorted hostapd events and identifies MACs that bounce between two APs rapidly.

A "thrash sequence" is: 3+ connects for the same MAC alternating between two APs, where consecutive connects are less than `max_gap` seconds apart (default 60s).

```python
import pytest
from dethrash.analyzers.thrashing import ThrashingDetector, ThrashSequence
from dethrash.sources.vl import HostapdEvent


def _connect(mac, ap, time, auth_alg="ft"):
    return HostapdEvent(event="connected", mac=mac, ap=ap, time=time, auth_alg=auth_alg)


def _disconnect(mac, ap, time):
    return HostapdEvent(event="disconnected", mac=mac, ap=ap, time=time)


class TestThrashingDetection:
    def test_detects_simple_thrash(self):
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:06Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:09Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        assert len(sequences) == 1
        s = sequences[0]
        assert s.mac == "aa:bb:cc:dd:ee:01"
        assert set(s.ap_pair) == {"pingu", "golem"}
        assert s.count == 4

    def test_ignores_normal_roaming(self):
        """Roaming once is not thrashing."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:05:00Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)
        assert sequences == []

    def test_gap_breaks_sequence(self):
        """Long gap between connects breaks the thrash sequence."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:06Z"),
            # 5 minute gap — breaks the sequence
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:05:06Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        assert len(sequences) == 1
        assert sequences[0].count == 3  # only first 3

    def test_multiple_macs(self):
        """Detects thrashing per-MAC independently."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:02", "albert", "2026-02-16T08:00:01Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:02Z"),
            _connect("aa:bb:cc:dd:ee:02", "gordon", "2026-02-16T08:00:03Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:04Z"),
            _connect("aa:bb:cc:dd:ee:02", "albert", "2026-02-16T08:00:05Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        assert len(sequences) == 2

    def test_disconnects_are_ignored(self):
        """Only connect events contribute to thrashing detection."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _disconnect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:01Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
            _disconnect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:04Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:06Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        assert len(sequences) == 1
        assert sequences[0].count == 3

    def test_three_ap_cycle_not_a_pair(self):
        """A→B→C→A is not a pair thrash — it's normal roaming through rooms."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
            _connect("aa:bb:cc:dd:ee:01", "albert", "2026-02-16T08:00:06Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:09Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        # Should NOT detect as thrash — it visited 3 different APs
        assert sequences == []
```

### Step 2: Run tests — expect FAIL

```bash
.venv/bin/pytest tests/test_thrashing.py -v
```

### Step 3: Implement thrashing detector

Create `src/dethrash/analyzers/__init__.py` (empty).

Create `src/dethrash/analyzers/thrashing.py`:

```python
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from dethrash.sources.vl import HostapdEvent


@dataclass(frozen=True)
class ThrashSequence:
    mac: str
    ap_pair: tuple[str, str]
    count: int
    first_time: str
    last_time: str


class ThrashingDetector:
    def __init__(self, max_gap: int = 60, min_count: int = 3):
        self._max_gap = max_gap
        self._min_count = min_count

    def detect(self, events: list[HostapdEvent]) -> list[ThrashSequence]:
        """Detect thrashing sequences from sorted hostapd events."""
        # Group connect events by MAC
        connects_by_mac: dict[str, list[HostapdEvent]] = defaultdict(list)
        for e in events:
            if e.event == "connected":
                connects_by_mac[e.mac].append(e)

        sequences = []
        for mac, connects in connects_by_mac.items():
            sequences.extend(self._detect_for_mac(mac, connects))

        sequences.sort(key=lambda s: s.count, reverse=True)
        return sequences

    def _detect_for_mac(
        self, mac: str, connects: list[HostapdEvent]
    ) -> list[ThrashSequence]:
        """Find thrash sequences for a single MAC."""
        if len(connects) < self._min_count:
            return []

        sequences = []
        run_start = 0

        for i in range(1, len(connects)):
            prev_t = self._parse_time(connects[i - 1].time)
            curr_t = self._parse_time(connects[i].time)
            gap = (curr_t - prev_t).total_seconds()

            if gap > self._max_gap:
                # Gap too large — flush current run
                seq = self._check_run(mac, connects[run_start:i])
                if seq:
                    sequences.append(seq)
                run_start = i

        # Flush final run
        seq = self._check_run(mac, connects[run_start:])
        if seq:
            sequences.append(seq)

        return sequences

    def _check_run(
        self, mac: str, connects: list[HostapdEvent]
    ) -> ThrashSequence | None:
        """Check if a run of connects is a pair thrash."""
        if len(connects) < self._min_count:
            return None

        aps = {c.ap for c in connects}
        if len(aps) != 2:
            return None

        ap_pair = tuple(sorted(aps))
        return ThrashSequence(
            mac=mac,
            ap_pair=ap_pair,
            count=len(connects),
            first_time=connects[0].time,
            last_time=connects[-1].time,
        )

    @staticmethod
    def _parse_time(iso: str) -> datetime:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
```

### Step 4: Run tests — expect PASS

```bash
.venv/bin/pytest tests/test_thrashing.py -v
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: thrashing detector — finds AP-pair bouncing"
```

---

## Task 5: RSSI overlap and weak association analyzers

**Files:**
- Create: `src/dethrash/analyzers/overlap.py`
- Create: `src/dethrash/analyzers/weak.py`
- Create: `tests/test_overlap.py`
- Create: `tests/test_weak.py`

### Step 1: Write failing tests for overlap

Create `tests/test_overlap.py`. The overlap analyzer takes RSSI readings and finds AP pairs where a station sees both APs within a small dB margin — confirming the thrashing cause.

```python
import pytest
from dethrash.analyzers.overlap import OverlapAnalyzer, OverlapResult
from dethrash.sources.vm import RSSIReading


def _r(mac, ap, rssi, ts):
    return RSSIReading(mac=mac, ap=ap, ifname="phy1-ap0", rssi=rssi, timestamp=ts)


class TestOverlapAnalysis:
    def test_detects_overlap(self):
        """Two APs seeing the same MAC within 6 dB = overlap."""
        readings = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000),
            _r("aa:bb:cc:dd:ee:01", "golem", -58, 1000),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)

        assert len(results) == 1
        r = results[0]
        assert r.mac == "aa:bb:cc:dd:ee:01"
        assert set(r.ap_pair) == {"pingu", "golem"}
        assert r.rssi_diff == 3  # |(-55) - (-58)|

    def test_no_overlap_when_difference_large(self):
        """20 dB difference = no overlap."""
        readings = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000),
            _r("aa:bb:cc:dd:ee:01", "golem", -75, 1000),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)
        assert results == []

    def test_overlap_across_time(self):
        """Overlap is computed per-timestamp, then aggregated."""
        readings = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000),
            _r("aa:bb:cc:dd:ee:01", "golem", -58, 1000),
            _r("aa:bb:cc:dd:ee:01", "pingu", -56, 1030),
            _r("aa:bb:cc:dd:ee:01", "golem", -59, 1030),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)

        assert len(results) == 1
        assert results[0].overlap_count == 2  # overlap at both timestamps

    def test_multiple_macs(self):
        readings = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000),
            _r("aa:bb:cc:dd:ee:01", "golem", -57, 1000),
            _r("aa:bb:cc:dd:ee:02", "albert", -50, 1000),
            _r("aa:bb:cc:dd:ee:02", "gordon", -52, 1000),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)
        assert len(results) == 2
```

### Step 2: Write failing tests for weak associations

Create `tests/test_weak.py`:

```python
import pytest
from dethrash.analyzers.weak import WeakAssociationAnalyzer, WeakAssociation
from dethrash.sources.vm import RSSIReading, NoiseReading


def _r(mac, ap, rssi, ts):
    return RSSIReading(mac=mac, ap=ap, ifname="phy1-ap0", rssi=rssi, timestamp=ts)


def _n(ap, noise, ts, radio="radio1", freq=5745):
    return NoiseReading(ap=ap, radio=radio, frequency=freq, noise_dbm=noise, timestamp=ts)


class TestWeakAssociation:
    def test_detects_low_snr(self):
        """Station with SNR < threshold = weak."""
        rssi = [_r("aa:bb:cc:dd:ee:01", "pingu", -80, 1000)]
        noise = [_n("pingu", -90, 1000)]

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)

        assert len(results) == 1
        r = results[0]
        assert r.mac == "aa:bb:cc:dd:ee:01"
        assert r.ap == "pingu"
        assert r.avg_snr == 10  # -80 - (-90) = 10

    def test_good_snr_not_flagged(self):
        """Station with SNR > threshold = fine."""
        rssi = [_r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000)]
        noise = [_n("pingu", -92, 1000)]

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)
        assert results == []

    def test_averages_over_time(self):
        """SNR is averaged over multiple samples."""
        rssi = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -78, 1000),
            _r("aa:bb:cc:dd:ee:01", "pingu", -82, 1030),
        ]
        noise = [
            _n("pingu", -90, 1000),
            _n("pingu", -90, 1030),
        ]

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)

        assert len(results) == 1
        assert results[0].avg_snr == 10  # avg(-78, -82) - (-90) = -80 - (-90) = 10
```

### Step 3: Run tests — expect FAIL

```bash
.venv/bin/pytest tests/test_overlap.py tests/test_weak.py -v
```

### Step 4: Implement overlap analyzer

Create `src/dethrash/analyzers/overlap.py`:

```python
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from dethrash.sources.vm import RSSIReading


@dataclass(frozen=True)
class OverlapResult:
    mac: str
    ap_pair: tuple[str, str]
    rssi_diff: float          # mean abs RSSI difference when overlapping
    overlap_count: int        # number of timestamps with overlap
    total_samples: int        # total timestamps where both APs saw the MAC


class OverlapAnalyzer:
    def __init__(self, overlap_threshold: int = 6):
        self._threshold = overlap_threshold

    def analyze(self, readings: list[RSSIReading]) -> list[OverlapResult]:
        # Group: (mac, timestamp) -> {ap: rssi}
        by_mac_ts: dict[str, dict[int, dict[str, int]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for r in readings:
            by_mac_ts[r.mac][r.timestamp][r.ap] = r.rssi

        results = []
        for mac, ts_map in by_mac_ts.items():
            # For each AP pair this MAC was seen on, check overlap
            pair_stats: dict[tuple[str, str], list[int]] = defaultdict(list)
            for ts, ap_rssi in ts_map.items():
                for a, b in combinations(sorted(ap_rssi.keys()), 2):
                    diff = abs(ap_rssi[a] - ap_rssi[b])
                    pair_stats[(a, b)].append(diff)

            for pair, diffs in pair_stats.items():
                overlaps = [d for d in diffs if d <= self._threshold]
                if overlaps:
                    results.append(OverlapResult(
                        mac=mac,
                        ap_pair=pair,
                        rssi_diff=round(sum(overlaps) / len(overlaps), 1),
                        overlap_count=len(overlaps),
                        total_samples=len(diffs),
                    ))

        results.sort(key=lambda r: r.overlap_count, reverse=True)
        return results
```

### Step 5: Implement weak association analyzer

Create `src/dethrash/analyzers/weak.py`:

```python
from collections import defaultdict
from dataclasses import dataclass

from dethrash.sources.vm import RSSIReading, NoiseReading


@dataclass(frozen=True)
class WeakAssociation:
    mac: str
    ap: str
    avg_snr: float
    sample_count: int


class WeakAssociationAnalyzer:
    def __init__(self, snr_threshold: int = 15):
        self._threshold = snr_threshold

    def analyze(
        self,
        rssi: list[RSSIReading],
        noise: list[NoiseReading],
    ) -> list[WeakAssociation]:
        # Build noise lookup: (ap, timestamp) -> noise_dbm
        # Use nearest available noise reading per AP
        noise_by_ap: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for n in noise:
            noise_by_ap[n.ap].append((n.timestamp, n.noise_dbm))

        # Sort noise by timestamp for bisect
        for ap in noise_by_ap:
            noise_by_ap[ap].sort()

        # Compute SNR for each RSSI reading
        snr_by_mac_ap: dict[tuple[str, str], list[float]] = defaultdict(list)
        for r in rssi:
            noise_val = self._nearest_noise(noise_by_ap.get(r.ap, []), r.timestamp)
            if noise_val is not None:
                snr = r.rssi - noise_val
                snr_by_mac_ap[(r.mac, r.ap)].append(snr)

        results = []
        for (mac, ap), snrs in snr_by_mac_ap.items():
            avg = sum(snrs) / len(snrs)
            if avg < self._threshold:
                results.append(WeakAssociation(
                    mac=mac,
                    ap=ap,
                    avg_snr=round(avg),
                    sample_count=len(snrs),
                ))

        results.sort(key=lambda w: w.avg_snr)
        return results

    @staticmethod
    def _nearest_noise(
        noise_series: list[tuple[int, int]], ts: int
    ) -> int | None:
        """Find the noise reading closest to the given timestamp."""
        if not noise_series:
            return None
        import bisect
        idx = bisect.bisect_left(noise_series, (ts,))
        candidates = []
        if idx < len(noise_series):
            candidates.append(noise_series[idx])
        if idx > 0:
            candidates.append(noise_series[idx - 1])
        return min(candidates, key=lambda x: abs(x[0] - ts))[1]
```

### Step 6: Run tests — expect PASS

```bash
.venv/bin/pytest tests/test_overlap.py tests/test_weak.py -v
```

### Step 7: Commit

```bash
git add -A && git commit -m "feat: overlap and weak association analyzers"
```

---

## Task 6: Recommendation engine — txpower and usteer

**Files:**
- Create: `src/dethrash/recommender.py`
- Create: `tests/test_recommender.py`

### Step 1: Write failing tests

Create `tests/test_recommender.py`. The recommender takes analyzer results and produces UCI commands.

```python
import pytest
from dethrash.recommender import Recommender, UCICommand
from dethrash.analyzers.thrashing import ThrashSequence
from dethrash.analyzers.overlap import OverlapResult
from dethrash.analyzers.weak import WeakAssociation


class TestTxPowerRecommendation:
    def test_recommends_power_reduction_for_thrashing_pair(self):
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=50,
            first_time="2026-02-16T08:00:00Z",
            last_time="2026-02-16T08:10:00Z",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            rssi_diff=3.0,
            overlap_count=100,
            total_samples=120,
        )]

        rec = Recommender()
        commands = rec.txpower_commands(thrash, overlap)

        # Should recommend reducing power on both APs in the pair
        assert len(commands) >= 2
        assert all(c.command.startswith("uci set") for c in commands)
        assert any("golem" in c.ssh_prefix for c in commands)
        assert any("pingu" in c.ssh_prefix for c in commands)

    def test_no_thrashing_no_recommendations(self):
        rec = Recommender()
        commands = rec.txpower_commands([], [])
        assert commands == []


class TestUsteerRecommendation:
    def test_recommends_min_snr_for_weak_associations(self):
        weak = [WeakAssociation(
            mac="aa:bb:cc:dd:ee:01",
            ap="pingu",
            avg_snr=8,
            sample_count=100,
        )]

        rec = Recommender()
        commands = rec.usteer_commands(weak)

        assert len(commands) >= 1
        assert any("min_snr" in c.command or "min_connect_snr" in c.command
                    for c in commands)


class TestUCICommand:
    def test_ssh_format(self):
        cmd = UCICommand(
            ap="pingu",
            ssh_prefix="ssh root@pingu",
            command="uci set wireless.radio1.txpower=14",
            reason="Reduce overlap with golem (avg 3 dB difference)",
        )
        assert str(cmd) == "ssh root@pingu uci set wireless.radio1.txpower=14"
```

### Step 2: Run tests — expect FAIL

```bash
.venv/bin/pytest tests/test_recommender.py -v
```

### Step 3: Implement recommender

Create `src/dethrash/recommender.py`:

```python
from dataclasses import dataclass

from dethrash.analyzers.thrashing import ThrashSequence
from dethrash.analyzers.overlap import OverlapResult
from dethrash.analyzers.weak import WeakAssociation


@dataclass
class UCICommand:
    ap: str
    ssh_prefix: str
    command: str
    reason: str

    def __str__(self) -> str:
        return f"{self.ssh_prefix} {self.command}"


class Recommender:
    def __init__(self, target_power: int = 14, min_snr_value: int = 15):
        self._target_power = target_power
        self._min_snr_value = min_snr_value

    def txpower_commands(
        self,
        thrash: list[ThrashSequence],
        overlap: list[OverlapResult],
    ) -> list[UCICommand]:
        """Generate txpower reduction commands for thrashing AP pairs."""
        if not thrash:
            return []

        # Find AP pairs that both thrash AND have RSSI overlap
        overlap_pairs = {r.ap_pair for r in overlap}
        thrash_pairs = {s.ap_pair for s in thrash}
        confirmed = overlap_pairs & thrash_pairs

        commands = []
        affected_aps = set()
        for pair in confirmed:
            for ap in pair:
                if ap not in affected_aps:
                    affected_aps.add(ap)
                    other = pair[1] if pair[0] == ap else pair[0]
                    overlap_r = next(
                        (r for r in overlap if r.ap_pair == pair), None
                    )
                    diff = overlap_r.rssi_diff if overlap_r else "?"
                    commands.append(UCICommand(
                        ap=ap,
                        ssh_prefix=f"ssh root@{ap}",
                        command=f"uci set wireless.radio1.txpower={self._target_power}",
                        reason=f"Reduce overlap with {other} (avg {diff} dB difference)",
                    ))

        return commands

    def usteer_commands(
        self,
        weak: list[WeakAssociation],
    ) -> list[UCICommand]:
        """Generate usteer threshold commands for weak associations."""
        if not weak:
            return []

        # Recommend global usteer thresholds based on worst-case weak associations
        commands = [
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command=f"uci set usteer.@usteer[0].min_connect_snr={self._min_snr_value}",
                reason=f"Reject new associations below {self._min_snr_value} dB SNR",
            ),
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command=f"uci set usteer.@usteer[0].min_snr={self._min_snr_value - 3}",
                reason=f"Kick existing clients below {self._min_snr_value - 3} dB SNR",
            ),
        ]
        return commands
```

### Step 4: Run tests — expect PASS

```bash
.venv/bin/pytest tests/test_recommender.py -v
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: recommender — txpower and usteer UCI commands"
```

---

## Task 7: Terminal report renderer

**Files:**
- Create: `src/dethrash/report.py`
- Create: `tests/test_report.py`

### Step 1: Write failing tests

Create `tests/test_report.py`. The report renderer takes all analyzer results and produces a human-readable terminal output.

```python
import pytest
from dethrash.report import render_report
from dethrash.analyzers.thrashing import ThrashSequence
from dethrash.analyzers.overlap import OverlapResult
from dethrash.analyzers.weak import WeakAssociation
from dethrash.recommender import UCICommand


class TestReport:
    def test_includes_thrash_sequences(self):
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=50,
            first_time="2026-02-16T08:00:00Z",
            last_time="2026-02-16T08:10:00Z",
        )]
        output = render_report(
            thrash=thrash, overlap=[], weak=[], commands=[],
        )
        assert "aa:bb:cc:dd:ee:01" in output
        assert "golem" in output
        assert "pingu" in output
        assert "50" in output

    def test_includes_commands_section(self):
        commands = [UCICommand(
            ap="pingu",
            ssh_prefix="ssh root@pingu",
            command="uci set wireless.radio1.txpower=14",
            reason="test reason",
        )]
        output = render_report(
            thrash=[], overlap=[], weak=[], commands=commands,
        )
        assert "ssh root@pingu uci set wireless.radio1.txpower=14" in output

    def test_empty_report(self):
        output = render_report(thrash=[], overlap=[], weak=[], commands=[])
        assert "No thrashing" in output or "clean" in output.lower()
```

### Step 2: Run tests — expect FAIL

```bash
.venv/bin/pytest tests/test_report.py -v
```

### Step 3: Implement report renderer

Create `src/dethrash/report.py`:

```python
from dethrash.analyzers.thrashing import ThrashSequence
from dethrash.analyzers.overlap import OverlapResult
from dethrash.analyzers.weak import WeakAssociation
from dethrash.recommender import UCICommand


def render_report(
    *,
    thrash: list[ThrashSequence],
    overlap: list[OverlapResult],
    weak: list[WeakAssociation],
    commands: list[UCICommand],
) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  wifi-dethrash report")
    lines.append("=" * 60)
    lines.append("")

    # Thrashing
    lines.append("--- Thrashing sequences ---")
    if thrash:
        for s in thrash:
            lines.append(
                f"  {s.mac}  {s.ap_pair[0]} <-> {s.ap_pair[1]}  "
                f"{s.count} connects  ({s.first_time} to {s.last_time})"
            )
    else:
        lines.append("  No thrashing detected.")
    lines.append("")

    # Overlap
    lines.append("--- RSSI overlap ---")
    if overlap:
        for o in overlap:
            pct = round(o.overlap_count / o.total_samples * 100) if o.total_samples else 0
            lines.append(
                f"  {o.mac}  {o.ap_pair[0]} <-> {o.ap_pair[1]}  "
                f"avg diff {o.rssi_diff} dB  "
                f"({o.overlap_count}/{o.total_samples} samples = {pct}%)"
            )
    else:
        lines.append("  No significant overlap.")
    lines.append("")

    # Weak associations
    lines.append("--- Weak associations ---")
    if weak:
        for w in weak:
            lines.append(
                f"  {w.mac} on {w.ap}  avg SNR {w.avg_snr} dB  "
                f"({w.sample_count} samples)"
            )
    else:
        lines.append("  No weak associations.")
    lines.append("")

    # Commands
    lines.append("--- Recommended commands ---")
    if commands:
        for c in commands:
            lines.append(f"  {c}")
            lines.append(f"    # {c.reason}")
    else:
        lines.append("  No changes recommended. Looking clean.")
    lines.append("")

    return "\n".join(lines)
```

### Step 4: Run tests — expect PASS

```bash
.venv/bin/pytest tests/test_report.py -v
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: terminal report renderer"
```

---

## Task 8: Wire CLI to analyzers

**Files:**
- Modify: `src/dethrash/cli.py`

### Step 1: Write an end-to-end CLI test

Create `tests/test_cli.py`:

```python
import json
import pytest
from click.testing import CliRunner
from dethrash.cli import main


VM_LABEL_RESP = {"data": ["mowgli:9100", "pingu:9100"]}

VM_RSSI_RESP = {
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {"mac": "aa:bb:cc:dd:ee:01", "ifname": "phy1-ap0",
                           "instance": "pingu:9100"},
                "values": [[1700000000, "-55"]],
            },
        ],
    }
}

VM_NOISE_RESP = {
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {"device": "radio1", "frequency": "5745",
                           "instance": "pingu:9100"},
                "values": [[1700000000, "-92"]],
            },
        ],
    }
}

VL_EVENTS = '{"_time":"2026-02-16T08:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:01 auth_alg=open","tags.hostname":"pingu"}\n'


class TestCLI:
    def test_runs_and_produces_report(self, respx_mock):
        # VM: label values
        respx_mock.get("http://vm:8428/api/v1/label/instance/values").respond(
            json=VM_LABEL_RESP
        )
        # VM: RSSI query_range
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=VM_RSSI_RESP
        )
        # VL: events
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=VL_EVENTS
        )

        runner = CliRunner()
        result = runner.invoke(main, [
            "--vm-url", "http://vm:8428",
            "--vl-url", "http://vl:9428",
            "--window", "1h",
        ])

        assert result.exit_code == 0
        assert "wifi-dethrash report" in result.output
```

### Step 2: Run test — expect FAIL

```bash
.venv/bin/pytest tests/test_cli.py -v
```

### Step 3: Implement full CLI

Rewrite `src/dethrash/cli.py`:

```python
import re
from datetime import datetime, timedelta, timezone

import click

from dethrash.sources.vm import VictoriaMetricsClient
from dethrash.sources.vl import VictoriaLogsClient
from dethrash.analyzers.thrashing import ThrashingDetector
from dethrash.analyzers.overlap import OverlapAnalyzer
from dethrash.analyzers.weak import WeakAssociationAnalyzer
from dethrash.recommender import Recommender
from dethrash.report import render_report


def _parse_window(window: str) -> timedelta:
    """Parse '1h', '24h', '7d' into timedelta."""
    m = re.match(r"^(\d+)([hd])$", window)
    if not m:
        raise click.BadParameter(f"Invalid window format: {window}. Use e.g. 1h, 24h, 7d")
    val, unit = int(m.group(1)), m.group(2)
    if unit == "h":
        return timedelta(hours=val)
    return timedelta(days=val)


@click.command()
@click.option("--vm-url", required=True, help="VictoriaMetrics base URL")
@click.option("--vl-url", required=True, help="VictoriaLogs base URL")
@click.option("--window", default="24h", help="Time window to analyze (e.g. 1h, 24h, 7d)")
@click.option("--host-label", default="instance", help="Metric label containing AP hostname")
@click.option("--mac", multiple=True, help="Filter to specific MAC address(es)")
@click.option("--generate-dashboard", type=click.Path(), default=None,
              help="Write Grafana dashboard JSON to file and exit")
@click.option("--overlap-threshold", default=6, help="Max RSSI diff (dB) to count as overlap")
@click.option("--snr-threshold", default=15, help="Min SNR (dB) for a healthy association")
@click.option("--target-power", default=14, help="Recommended TX power (dBm)")
def main(vm_url, vl_url, window, host_label, mac, generate_dashboard,
         overlap_threshold, snr_threshold, target_power):
    """WiFi mesh thrashing analyzer for OpenWrt."""
    if generate_dashboard:
        click.echo("Dashboard generation not yet implemented.")
        return

    delta = _parse_window(window)
    end = datetime.now(timezone.utc)
    start = end - delta

    macs = list(mac) if mac else None

    vm = VictoriaMetricsClient(vm_url, host_label=host_label)
    vl = VictoriaLogsClient(vl_url)

    click.echo(f"Discovering APs from {vm_url} ...")
    aps = vm.discover_aps()
    click.echo(f"Found {len(aps)} APs: {', '.join(a.hostname for a in aps)}")

    click.echo(f"Fetching RSSI data ({window} window) ...")
    rssi = vm.fetch_rssi(start, end, macs=macs)

    click.echo("Fetching noise floor data ...")
    noise = vm.fetch_noise(start, end)

    click.echo("Fetching hostapd events ...")
    events = vl.fetch_events(start, end, macs=macs)
    click.echo(f"Got {len(rssi)} RSSI readings, {len(events)} hostapd events.")

    click.echo("Analyzing ...")
    thrash = ThrashingDetector().detect(events)
    overlap = OverlapAnalyzer(overlap_threshold).analyze(rssi)
    weak = WeakAssociationAnalyzer(snr_threshold).analyze(rssi, noise)

    rec = Recommender(target_power=target_power, min_snr_value=snr_threshold)
    commands = rec.txpower_commands(thrash, overlap) + rec.usteer_commands(weak)

    click.echo("")
    click.echo(render_report(
        thrash=thrash, overlap=overlap, weak=weak, commands=commands,
    ))
```

### Step 4: Run tests — expect PASS

```bash
.venv/bin/pytest tests/test_cli.py -v
```

The `query_range` mock will be called twice (RSSI + noise) with the same mock — that's fine because `respx_mock` allows multiple calls by default.

### Step 5: Run full test suite

```bash
.venv/bin/pytest -v
```

### Step 6: Commit

```bash
git add -A && git commit -m "feat: wire CLI to analyzers and report"
```

---

## Task 9: Grafana dashboard generator

**Files:**
- Create: `src/dethrash/dashboard.py`
- Create: `tests/test_dashboard.py`

### Step 1: Write failing tests

Create `tests/test_dashboard.py`:

```python
import json
import pytest
from dethrash.dashboard import generate_dashboard
from dethrash.sources.vm import APInfo


class TestDashboard:
    def test_valid_json(self):
        aps = [
            APInfo(hostname="mowgli", instance="mowgli:9100"),
            APInfo(hostname="pingu", instance="pingu:9100"),
        ]
        dashboard = generate_dashboard(aps, datasource="Prometheus")
        parsed = json.loads(dashboard)

        assert "dashboard" in parsed
        assert parsed["dashboard"]["title"] == "WiFi Mesh Health"

    def test_has_rssi_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        panels = parsed["dashboard"]["panels"]
        titles = [p["title"] for p in panels]
        assert "RSSI by Station" in titles

    def test_has_noise_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        panels = parsed["dashboard"]["panels"]
        titles = [p["title"] for p in panels]
        assert "Noise Floor" in titles

    def test_has_events_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        panels = parsed["dashboard"]["panels"]
        titles = [p["title"] for p in panels]
        assert "Hostapd Events" in titles or "Connect/Disconnect Events" in titles
```

### Step 2: Run tests — expect FAIL

```bash
.venv/bin/pytest tests/test_dashboard.py -v
```

### Step 3: Implement dashboard generator

Create `src/dethrash/dashboard.py`:

```python
import json
from dethrash.sources.vm import APInfo


def generate_dashboard(
    aps: list[APInfo],
    datasource: str = "Prometheus",
    logs_datasource: str = "VictoriaLogs",
) -> str:
    """Generate a Grafana dashboard JSON for WiFi mesh health monitoring."""
    instance_re = "|".join(a.instance for a in aps)

    panels = [
        {
            "title": "RSSI by Station",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0},
            "datasource": {"type": "prometheus", "uid": datasource},
            "targets": [
                {
                    "expr": f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}',
                    "legendFormat": "{{instance}} / {{mac}}",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dBm",
                    "custom": {"drawStyle": "line", "lineWidth": 1},
                }
            },
        },
        {
            "title": "Noise Floor",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8},
            "datasource": {"type": "prometheus", "uid": datasource},
            "targets": [
                {
                    "expr": f'wifi_network_noise_dbm{{instance=~"{instance_re}"}}',
                    "legendFormat": "{{instance}} / {{device}} ({{frequency}} MHz)",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dBm",
                    "custom": {"drawStyle": "line", "lineWidth": 1},
                }
            },
        },
        {
            "title": "Connect/Disconnect Events",
            "type": "logs",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16},
            "datasource": {"type": "victorialogs-datasource", "uid": logs_datasource},
            "targets": [
                {
                    "expr": "tags.appname:hostapd AND _msg:AP-STA-",
                }
            ],
        },
    ]

    dashboard = {
        "dashboard": {
            "title": "WiFi Mesh Health",
            "tags": ["wifi", "openwrt", "mesh"],
            "timezone": "browser",
            "panels": panels,
            "time": {"from": "now-24h", "to": "now"},
            "refresh": "30s",
        },
        "overwrite": True,
    }

    return json.dumps(dashboard, indent=2)
```

### Step 4: Run tests — expect PASS

```bash
.venv/bin/pytest tests/test_dashboard.py -v
```

### Step 5: Wire dashboard generation into CLI

In `src/dethrash/cli.py`, replace the placeholder:

```python
    if generate_dashboard:
        click.echo("Dashboard generation not yet implemented.")
        return
```

With:

```python
    if generate_dashboard:
        from dethrash.dashboard import generate_dashboard as gen_dash
        vm = VictoriaMetricsClient(vm_url, host_label=host_label)
        aps = vm.discover_aps()
        dashboard_json = gen_dash(aps)
        with open(generate_dashboard, "w") as f:
            f.write(dashboard_json)
        click.echo(f"Dashboard written to {generate_dashboard}")
        return
```

### Step 6: Run full test suite

```bash
.venv/bin/pytest -v
```

### Step 7: Commit

```bash
git add -A && git commit -m "feat: Grafana dashboard JSON generator"
```

---

## Task 10: Final polish — README, CLAUDE.md

**Files:**
- Modify: `README.md`

### Step 1: Update README with full usage

Update `README.md` with:
- All CLI options documented
- Example output showing what the report looks like
- Dashboard generation instructions
- Data source requirements (VictoriaMetrics with Telegraf, VictoriaLogs with hostapd syslog)

### Step 2: Create CLAUDE.md

Create `CLAUDE.md` with project context for Claude:
- Architecture overview
- Key files
- Test command: `.venv/bin/pytest -v`
- Data source details (metric names, log format)
- Design decisions

### Step 3: Run full test suite one final time

```bash
.venv/bin/pytest -v
```

### Step 4: Commit

```bash
git add -A && git commit -m "docs: README and CLAUDE.md"
```

---

## Files summary

| Action | File |
|--------|------|
| Create | `pyproject.toml` |
| Create | `.gitignore` |
| Create | `README.md` |
| Create | `CLAUDE.md` |
| Create | `src/dethrash/__init__.py` |
| Create | `src/dethrash/__main__.py` |
| Create | `src/dethrash/cli.py` |
| Create | `src/dethrash/sources/__init__.py` |
| Create | `src/dethrash/sources/vm.py` |
| Create | `src/dethrash/sources/vl.py` |
| Create | `src/dethrash/analyzers/__init__.py` |
| Create | `src/dethrash/analyzers/thrashing.py` |
| Create | `src/dethrash/analyzers/overlap.py` |
| Create | `src/dethrash/analyzers/weak.py` |
| Create | `src/dethrash/recommender.py` |
| Create | `src/dethrash/report.py` |
| Create | `src/dethrash/dashboard.py` |
| Create | `tests/__init__.py` |
| Create | `tests/conftest.py` |
| Create | `tests/test_vm.py` |
| Create | `tests/test_vl.py` |
| Create | `tests/test_thrashing.py` |
| Create | `tests/test_overlap.py` |
| Create | `tests/test_weak.py` |
| Create | `tests/test_recommender.py` |
| Create | `tests/test_report.py` |
| Create | `tests/test_dashboard.py` |
| Create | `tests/test_cli.py` |

## Verification

```bash
.venv/bin/pytest -v   # all tests pass
dethrash --help       # shows all options
```
