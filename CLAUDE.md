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
  test_*.py           # One test file per module (67 tests)
```

## Engineering Standards

- **Challenge the spec.** If domain knowledge contradicts the
  requirements, say so before building. A 30-second question costs
  nothing. Building the wrong thing costs hundreds of commits.
- **Ask before building.** Before implementing anything substantial:
  (1) Does the infrastructure already provide this? (2) Is there a
  10x simpler approach? (3) Will this still exist in two weeks?
- **Design discipline.** Before proposing recovery mechanisms,
  tracking structures, or new abstractions:
  (1) Don't duplicate state that already exists — derive it.
  (2) Think about the general problem, not the specific incident.
  (3) Lightweight over heavyweight. If the mechanism is heavier
  than the problem, the mechanism IS the problem.
  (4) Think it through before proposing — don't make the human
  iterate half-baked proposals into shape.
- **Debug with data first.** Read logs, inspect state, query the
  source before changing code. NEVER guess. Evidence first.
- **Never fabricate explanations.** If you don't know why something
  happened, say "I don't know, let me check" and investigate.
  A confident wrong explanation is worse than admitting ignorance.
- **Read before writing.** Before editing any file, read its helpers,
  utilities, and existing patterns. Grep for what you're about to
  build — it probably exists.
- **Implement once, reuse everywhere.** If two places need the same
  logic, refactor to share it. Never copy-paste with tweaks.
- **No leaky abstractions.** Each layer owns its domain. Return
  domain types, not strings/dicts callers parse.
- **Consistency.** Follow existing patterns. Same problem, same
  solution.
- **State the contract.** Signature + failure mode in one sentence
  before implementing. "Returns X or raises Y."
- **Fix root causes, not examples.** No band-aids, no
  `filterwarnings`, no `# type: ignore` without justification.
- **Type errors are design signals.** When a type constraint blocks
  your approach, the constraint is probably correct — your approach
  is probably wrong.
- **Never swallow exceptions.** Handle explicitly or let crash.
  Silent failures (like the libuci-lua debacle) are the worst bugs.
- **Type annotations on all signatures.**
- **"Done" means done.** Every method migrated, every caller updated,
  every test fixed, every doc current. Grep for stale references
  before committing renames.
- **Bite-sized commits.** One logical change. Messages explain WHY.

### Testing Standards

- Assert outcomes, not call sequences. Ask: "If the implementation
  were wrong, would this test catch it?"
- **Never assert buggy behavior.** If you don't understand why the
  code produces a value, don't write a test that asserts it.
- Mock at boundaries (HTTP via respx), real dependencies inside.
- **Use production code in tests** — never hardcode strings or
  re-implement logic. Build synthetic inputs, not synthetic outputs.
- **Never weaken production code to make tests pass.** Fix the test.
- Mock data must be realistic — empty or zeroed fixtures validate
  nothing.
- Test helpers mandatory. Names = scenario + outcome.

## Commands

```bash
.venv/bin/pytest -v              # run tests (67 tests, ~0.1s)
.venv/bin/pyright src/ tests/    # type check (zero errors)
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
