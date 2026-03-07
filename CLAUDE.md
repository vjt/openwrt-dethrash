# CLAUDE.md

## Project

wifi-dethrash — WiFi mesh thrashing analyzer for OpenWrt.
Analyzes historical WiFi metrics and logs to detect AP thrashing, RSSI
overlap, and weak associations. Produces actionable UCI commands for
txpower and usteer tuning, and generates Grafana dashboards.

## Architecture

```
src/wifi_dethrash/
  cli.py              # Click CLI entry point (error handling, --generate-dashboard)
  sources/
    vm.py             # VictoriaMetrics client (RSSI, noise, AP discovery, txpower)
    vl.py             # VictoriaLogs client (hostapd events)
  analyzers/
    thrashing.py      # Detects AP-pair bouncing from hostapd events
    overlap.py        # Finds RSSI overlap between AP pairs
    weak.py           # Finds low-SNR associations
  recommender.py      # Generates txpower + usteer recommendations
  report.py           # Terminal report renderer (aggregated, filtered)
  dashboard.py        # Grafana 12 dashboard JSON generator (file-import format)
  utils.py            # ifname_to_radio helper
openwrt/
  Makefile             # OpenWrt SDK package Makefile
  files/usr/lib/lua/prometheus-collectors/
    wifi_dethrash.lua  # Prometheus collector deployed on OpenWrt APs
tests/
  conftest.py         # respx mock fixture
  test_*.py           # One test file per module (65 tests)
```

## Commands

```bash
.venv/bin/pytest -v              # run tests (65 tests, ~0.1s)
.venv/bin/wifi-dethrash --help   # CLI help
```

## Key design decisions

- Synchronous httpx (not async) — simpler for a CLI tool
- truststore for OS-native CA trust (no manual cert config)
- Noise-RSSI correlation keyed by (ap, radio) to avoid cross-band mismatch
- Thrashing = 3+ connects alternating between exactly 2 APs within max_gap seconds
- AP pairs normalized as sorted tuples so thrashing and overlap results can be joined
- ifname (e.g. phy1-ap0) mapped to radio (e.g. radio1) for correct UCI commands
- MAC addresses normalized to lowercase throughout
- Recommendations require BOTH thrashing AND overlap for a pair (no false positives)
- Txpower suggestions: reduce louder AP by (overlap_threshold - rssi_diff + 2), clamped to [5, current - 2]
- Grafana dashboard uses file-import format with __inputs for datasource selection (not API format)
- Report aggregates thrashing by (mac, ap_pair) and filters overlap to >= 5 samples

## Data sources

- VictoriaMetrics: `wifi_station_signal_dbm`, `wifi_network_noise_dbm`,
  `wifi_radio_txpower_dbm`, `wifi_radio_configured_txpower`,
  `wifi_radio_channel`, `wifi_radio_frequency_mhz`
- VictoriaLogs: hostapd `AP-STA-CONNECTED` / `AP-STA-DISCONNECTED` events
- Instance label format: `hostname:9100` (configurable via --host-label)

## Lua collector (openwrt/wifi_dethrash.lua)

Deployed on each AP as a prometheus-node-exporter-lua collector. Exports:
- Radio metrics via iwinfo+ubus: txpower, txpower_offset, channel, frequency
- UCI wireless config: configured_txpower, 802.11r/k/v enabled
- UCI usteer config: SNR thresholds, signal_diff, load_kick, band_steering

## OpenWrt environment

- Target: OpenWrt 24.10.x (snapshot)
- Interface naming: modern (phy1-ap0) and legacy (wlan0) both supported
- Firmware upgrades via owut; custom packages via opkg from custom feed (separate repo)

## Gotchas learned during development

- VictoriaLogs datasource plugin ID is `victoriametrics-logs-datasource` (not `victorialogs-datasource`)
- Grafana 12 rejects dashboard JSON wrapped in `{"dashboard": {...}}` — use bare JSON
- Grafana 12 requires schemaVersion >= 39, panel `id` fields, and `refId` on targets
- `--vl-url` is optional when using `--generate-dashboard` (only needs VM to discover APs)
- txpower fetch uses instant query (`/api/v1/query`), not range query
- configured_txpower, channel, frequency are optional — graceful degradation via try/except
