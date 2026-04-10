# Changelog

## 0.3.1 — 2026-04-10

### Added
- **Station IP enrichment** — station-resolver now emits IP address alongside
  hostname. New `STATION_IP_FIELD` env var (default `station_ip`, set to
  `client_ip` in SIEM stack). Technitium DHCP `address` field parsed from
  reserved leases.
- **`/metrics` endpoint: `ip` label** — `wifi_station_name{mac,station,ip} 1`
  gauge now includes the station's reserved DHCP IP address.
- **Dashboard: `group_left(station, ip)`** — all panels using `_with_station()`
  now pull both hostname and IP labels from the join.
- **`build.sh`** — Docker-based build/test script for station-resolver. No
  local Go toolchain required (`golang:1.23-alpine` in Docker).

### Changed
- Station-resolver `lookup()` returns `(name, ip)` tuple instead of just name.
- `processLine()` injects both hostname and IP fields into influx line protocol.
  IP field omitted gracefully when not available for a MAC.

## 0.3.0 — 2026-03-30

### Added
- **Station-resolver `/metrics` endpoint** — serves `wifi_station_name` gauge
  with `{mac, station}` labels for dynamic MAC→hostname resolution. Telegraf
  scrapes this and forwards to VictoriaMetrics, enabling `group_left(station)`
  joins in dashboard queries. No more re-pushing dashboard when new devices
  connect.
- **Hearing Map panel** — signal strength of selected station as seen by all APs,
  showing usteer's roaming decision data.
- **Channel Load panel** — channel utilization per AP radio from usteer.
- **Roam Events panel** — source/target roam counts per AP from usteer.
- **Clients per AP table** — connected client count with avg RSSI and SNR,
  replacing the canvas topology panel.
- **Signal Quality merged panel** — RSSI (solid), SNR (dashed), and noise floor
  (dotted red) in a single panel (replaces separate RSSI and noise panels).
- **Station dropdown** — dynamic variable populated from VictoriaLogs
  `fields.station` via station-resolver enrichment. Works across both
  Prometheus and VictoriaLogs panels.
- **Collector: usteer runtime data** — hearing map signal, roam events, channel
  load, and associated clients exported via ubus. Each AP exports only its own
  `local_info` metrics; `remote_info` used only for node-map SSID resolution.
- **Collector: nixio reverse DNS** — cached hostname resolution for remote AP
  labels. Failures not cached, retried on next scrape.
- `fetch_wifi_stations()` replaces `fetch_mac_names()` — only WiFi clients
  included in MAC resolution.
- `luci-lib-nixio` added as package dependency.

### Fixed
- **Collector: ubus leak on early return** — `u:close()` now always runs even
  when `network.wireless status` fails. Replaced early returns with conditional
  blocks.
- **Collector: DNS cache cached failures permanently** — `resolve_ip()` no
  longer caches raw IP on DNS failure, allowing retry on next scrape.
- **Collector: remote_info metric duplication** — removed remote_info export of
  roam events, load, and associated clients. Each AP exports only its own data.
- **Dashboard: canvas panel in __requires** — removed stale canvas panel entry.
- **Dashboard: panel IDs non-sequential** — renumbered 1-13 in order of
  appearance.
- **Dashboard: fragile station filter in file-export** — `_wrap_label_map()`
  no longer injects `mac=~"$station"` in file-export format (no mac_names).

### Changed
- **Dashboard: `group_left(station)` replaces baked-in `label_map`** — Prometheus
  panels now join with `wifi_station_name_gauge` (from station-resolver /metrics)
  instead of hardcoded MAC→hostname mappings. Dashboard is fully dynamic.
- **`--push-dashboard` no longer needs VictoriaLogs** — only needs VM for AP
  discovery and Grafana for datasource UIDs. VL URL is only required for
  analysis mode.
- Dashboard reorganized: 13 panels (was 12), usteer visibility section added
  between signal quality and events/clients.
- Panel ID sequence: 1-13 in order of appearance.
- PKG_VERSION bumped to 0.3.0.

## 0.2.0 — 2026-03-29

### Added
- **Config file** (`~/.config/wifi-dethrash/config.toml`) — TOML config for
  URLs, Grafana credentials, mesh SSIDs, and AP floor plan. CLI options
  override config values. Config is optional — tool still works with CLI args.
- **Grafana API client** — `--push-dashboard` pushes dashboard directly via
  Grafana API using service account token. Discovers datasource UIDs
  automatically. `--generate-dashboard` kept for file export.
- **Grafana annotations** — `--annotate` marks config changes as vertical
  lines on dashboard panels for before/after comparison.
- **SSID-based AP filtering** — `mesh_ssids` config (or `--mesh-ssids` CLI)
  filters APs to only those broadcasting configured SSIDs. Non-mesh APs
  (e.g. jeeves with 5G backup) automatically excluded.
- **MAC address resolution** — resolves MACs to hostnames from DHCP logs
  (Technitium and dnsmasq formats). Names shown in all report tables.
- **5 new Grafana panels**: thrashing rate (connects/hour per AP), roaming
  timeline (state-timeline per MAC), RSSI heatmap, SNR distribution with
  threshold bands, usteer effectiveness (ft vs open auth_alg ratio).
- **Topology canvas panel** — floor-by-floor AP diagram with client counts,
  generated from `[aps]` config section. Only present when floor plan configured.
- `ssid` field on `TxPowerReading` — extracted from existing Prometheus label.

### Changed
- Dashboard module refactored: shared `_build_panels()` with two output
  formats (file-import with `__inputs`, API with real datasource UIDs).
- CLI options `--vm-url` and `--vl-url` now optional when set in config file.

## 0.1.1 — 2026-03-29

### Fixed
- **libuci-lua dependency** — collector package was missing the `libuci-lua`
  dependency, causing UCI-based metrics (configured_txpower, 802.11r/k/v,
  usteer thresholds) to silently not export. 12 of 16 metrics were missing.
- **Lua collector early return** — Phase 2 (UCI wireless) failure caused early
  return that prevented Phase 3 (usteer metrics) from executing. Wrapped in
  conditional instead of returning.
- **MAC normalization in weak analyzer** — `weak.py` didn't `.lower()` MACs
  while `overlap.py` did, causing silent data loss on case mismatch.
- **VictoriaLogs malformed JSON** — `json.loads()` crash on bad JSONL lines
  replaced with `try/except` + `log.warning()`.

### Changed
- **Consolidated txpower plan** — replaced per-pair recommendations with a
  holistic per-AP plan. Collects votes from all thrashing pairs, resolves
  conflicts by severity weight, and simulates compound RSSI impact across
  all pairs before/after.
- **Coverage-first philosophy** — when RSSI is below floor (-75 dBm), suggest
  txpower *increase* on quieter AP for coverage instead of "no change". When
  healthy, suggest conservative 2 dBm reduction with RSSI floor guard.
- **Prefer higher-txpower AP for reduction** — targets the AP with more
  headroom rather than always the louder signal.
- **usteer: signal_diff only, no kicking** — dropped min_snr, min_connect_snr,
  roam_trigger, load_kick recommendations. Data showed usteer kicking caused
  252 connects/day vs 213/day without (77% were usteer-pushed ft roams).
  Complete config now explicitly zeroes all dangerous settings.
- **Rich terminal output** — colored tables, Unicode box-drawing, arrow
  indicators for impact analysis. Commands rendered outside tables for
  copy-paste.

### Added
- **Network state table** — per-AP radio info (channel, txpower, noise floor)
  grouped by band at the top of the report.
- **Impact analysis table** — before/after RSSI diff simulation for all
  thrashing pairs under the proposed plan, with signal_diff coverage check.
- **Complete usteer config output** — signal_diff_threshold (data-driven),
  roam_scan_snr=25 (passive), plus explicit disables for all kicking.
- **pyright** at standard strictness — zero errors. Fixed tuple type in
  thrashing.py, added NoReturn to `_handle_error`.
- `--rssi-floor` CLI option (default -75 dBm).
- Engineering and testing standards in CLAUDE.md.

## 0.1.0 — 2026-02-16

Initial release.

- VictoriaMetrics client: AP discovery, RSSI, noise, txpower fetching
- VictoriaLogs client: hostapd connect/disconnect event parsing
- Thrashing detector: 3+ connects alternating between 2 APs within max_gap
- Overlap analyzer: RSSI diff between AP pairs per MAC per timestamp
- Weak association analyzer: SNR computation via noise-RSSI correlation
- Recommender: txpower and usteer UCI command generation
- Terminal report: aggregated thrashing, filtered overlap, weak associations
- Grafana 12 dashboard JSON generator (file-import format)
- Prometheus Lua collector for OpenWrt: txpower, channel, 802.11r/k/v, usteer
- OpenWrt SDK package (Makefile)
- truststore for OS-native CA trust
- 65 tests, Click CLI, synchronous httpx
