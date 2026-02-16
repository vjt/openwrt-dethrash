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
wifi-dethrash --vm-url http://victoriametrics:8428 --vl-url http://victorialogs:9428
```

See `wifi-dethrash --help` for all options.
