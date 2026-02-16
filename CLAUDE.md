# CLAUDE.md

## Project

wifi-dethrash — WiFi mesh thrashing analyzer for OpenWrt.

## Architecture

```
src/wifi_dethrash/
  cli.py              # Click CLI entry point
  sources/
    vm.py             # VictoriaMetrics client (RSSI, noise, AP discovery)
    vl.py             # VictoriaLogs client (hostapd events)
  analyzers/
    thrashing.py      # Detects AP-pair bouncing from hostapd events
    overlap.py        # Finds RSSI overlap between AP pairs
    weak.py           # Finds low-SNR associations
  recommender.py      # Generates UCI commands (txpower, usteer)
  report.py           # Terminal report renderer
  dashboard.py        # Grafana dashboard JSON generator
  utils.py            # ifname_to_radio helper
tests/
  conftest.py         # respx mock fixture
  test_*.py           # One test file per module
```

## Commands

```bash
.venv/bin/pytest -v              # run tests
.venv/bin/wifi-dethrash --help   # CLI help
```

## Key design decisions

- Synchronous httpx (not async) — simpler for a CLI tool
- Noise-RSSI correlation keyed by (ap, radio) to avoid cross-band mismatch
- Thrashing = 3+ connects alternating between exactly 2 APs within max_gap seconds
- AP pairs normalized as sorted tuples so thrashing and overlap results can be joined
- ifname (e.g. phy1-ap0) mapped to radio (e.g. radio1) for correct UCI commands

## Data sources

- VictoriaMetrics: `wifi_station_signal_dbm`, `wifi_network_noise_dbm`
- VictoriaLogs: hostapd `AP-STA-CONNECTED` / `AP-STA-DISCONNECTED` events
- Instance label format: `hostname:9100` (configurable via --host-label)
