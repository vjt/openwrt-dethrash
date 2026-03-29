# Changelog

## Unreleased

### Planned
- Config file (`~/.config/wifi-dethrash/config.toml`) for URLs, credentials, floor plan
- Grafana API integration — push dashboards directly, no JSON copy-paste
- New Grafana panels: thrashing rate over time, per-client roaming timeline,
  RSSI heatmap, SNR distribution, usteer effectiveness
- Topology view panel with floor-by-floor AP placement and client counts
- SSID-based AP filtering (Mercury/Saturn mesh, exclude non-mesh like jeeves)

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
