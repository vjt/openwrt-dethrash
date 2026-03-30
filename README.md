# wifi-dethrash

WiFi mesh analyzer for OpenWrt. Analyzes historical metrics and logs to detect
AP thrashing, RSSI overlap, and weak associations. Recommends txpower and
usteer UCI settings. Generates a fully dynamic Grafana dashboard with 13
panels and a station selector dropdown.

## Architecture

```
OpenWrt APs                           Monitoring stack
+-----------------------+             +-----------------------------------+
| prometheus-node-      |  scrape     | Telegraf                          |
| exporter-lua          |------------>|   inputs.prometheus (APs :9100)   |
| + wifi_dethrash.lua   |             |   inputs.prometheus (resolver     |
+-----------------------+             |     :9101/metrics)                |
                                      |   processors.execd               |
                                      |     (station-resolver)           |
                                      +--------+----------+-------------+
                                               |          |
                                               v          v
                                      VictoriaMetrics  VictoriaLogs
                                               |          |
                                               +----+-----+
                                                    |
                                                    v
                                                 Grafana
                                          (WiFi Mesh Health dashboard)
```

- **wifi_dethrash.lua** runs on each AP, exports radio metrics, 802.11r/k/v
  config, usteer runtime data (hearing map, roam events, load), and usteer
  config parameters.
- **station-resolver** is a Go binary running as a Telegraf `execd` processor.
  It enriches hostapd syslog events with `fields.station` (hostname from
  Technitium DHCP reservations) and serves a `/metrics` endpoint exporting
  `wifi_station_name{mac, station}` for dynamic MAC-to-hostname resolution.
- **Grafana dashboard** uses `group_left(station)` joins against
  `wifi_station_name_gauge` (the metric name after Telegraf's type suffix)
  so Prometheus panels show hostnames without any baked-in mapping. New devices
  appear automatically -- no need to re-push the dashboard.

## Setup

### 1. Install collector on APs

```bash
# Add custom feed (once per AP)
echo "src/gz wifi-dethrash http://<feed-server>/openwrt-feed" \
  >> /etc/opkg/customfeeds.conf

opkg update
opkg install wifi-dethrash-collector
```

This installs the Lua collector into
`/usr/lib/lua/prometheus-collectors/wifi_dethrash.lua` and pulls in
`prometheus-node-exporter-lua`, `libuci-lua`, and `luci-lib-nixio`
as dependencies.

### 2. Station resolver and Telegraf

The station-resolver runs alongside Telegraf in Docker. It has two roles:

1. **execd processor** -- enriches hostapd syslog lines with `station=<hostname>`
   fields before they reach VictoriaLogs.
2. **Prometheus /metrics endpoint** -- exports `wifi_station_name{mac, station}`
   gauge so Telegraf can scrape it and forward to VictoriaMetrics.

Docker Compose setup (in your monitoring stack):

```yaml
telegraf:
  build:
    context: .
    dockerfile: Dockerfile.telegraf
  environment:
    TECHNITIUM_TOKEN: "<your-technitium-api-token>"
    TECHNITIUM_URL: "https://ns1.example.com"
    METRICS_ADDR: ":9101"
```

The `Dockerfile.telegraf` is a multi-stage build that compiles
station-resolver from this repo's `cmd/station-resolver/` directory.

Telegraf config excerpts:

```toml
# Scrape APs
[[inputs.prometheus]]
  urls = ["http://golem:9100/metrics", "http://gordon:9100/metrics", ...]

# Scrape station-resolver MAC→hostname mapping
[[inputs.prometheus]]
  urls = ["http://localhost:9101/metrics"]

# Enrich hostapd syslog events with station hostname
[[processors.execd]]
  command = ["/usr/local/bin/station-resolver"]
  [processors.execd.tagpass]
    appname = ["hostapd"]
```

### 3. Configuration

Create `~/.config/wifi-dethrash/config.toml`:

```toml
vm_url = "https://metrics.example.com"
vl_url = "https://victoria.example.com"
grafana_url = "https://grafana.example.com"
grafana_api_key = "glsa_..."
mesh_ssids = ["Mercury", "Saturn"]

[aps]
golem = "Ground floor / Living room"
gordon = "Ground floor / Kitchen"
albert = "First floor / Bedroom"
pingu = "First floor / Office"
mowgli = "-1 / Garden"
parrot = "-1 / Laundry"
```

All fields are optional. CLI options override config values.

### 4. Push dashboard

```bash
wifi-dethrash --push-dashboard
```

This discovers APs from VictoriaMetrics, resolves Grafana datasource UIDs
automatically, and pushes the dashboard via the Grafana API. VictoriaLogs
URL is not needed for dashboard push -- only for analysis mode.

The dashboard is fully dynamic: the station dropdown is populated from
VictoriaLogs `fields.station`, and MAC-to-hostname resolution uses
`group_left(station)` joins against the station-resolver metric.

## Usage

```bash
# Analysis report (requires both VM and VL)
wifi-dethrash

# With explicit URLs
wifi-dethrash --vm-url http://vm:8428 --vl-url http://vl:9428

# Push dashboard to Grafana (requires VM + Grafana, not VL)
wifi-dethrash --push-dashboard

# Export dashboard as JSON file (for Grafana file import)
wifi-dethrash --generate-dashboard dashboard.json
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--config` | `~/.config/wifi-dethrash/config.toml` | Config file path |
| `--vm-url` | from config | VictoriaMetrics base URL |
| `--vl-url` | from config | VictoriaLogs base URL (required for analysis) |
| `--grafana-url` | from config | Grafana base URL |
| `--grafana-api-key` | from config | Grafana service account token |
| `--mesh-ssids` | from config | Mesh SSIDs to filter APs, repeatable |
| `--window` | `24h` | Time window (e.g. `1h`, `24h`, `7d`) |
| `--host-label` | `instance` | Metric label containing AP hostname |
| `--mac` | all | Filter to specific MAC(s), repeatable |
| `--overlap-threshold` | `6` | Max RSSI diff (dB) for overlap |
| `--snr-threshold` | `15` | Min SNR (dB) for healthy association |
| `--rssi-floor` | `-75` | Min RSSI (dBm) below which txpower reduction is skipped |
| `--generate-dashboard` | off | Write Grafana dashboard JSON to file |
| `--push-dashboard` | off | Push dashboard to Grafana via API |

### Grafana dashboard

13 panels with a dynamic station dropdown:

1. **Roaming Timeline** -- which AP each station is on over time (state-timeline)
2. **Signal Quality** -- RSSI (solid), SNR (dashed), noise (dotted red) merged panel
3. **Hearing Map** -- usteer signal per station as seen by all APs
4. **Channel Load** -- channel utilization per AP radio from usteer
5. **Roam Events (usteer)** -- source/target roam counts per AP
6. **Connect/Disconnect Events** -- hostapd event log with resolved station names
7. **Clients per AP** -- table with client count, avg RSSI, avg SNR
8. **Connects per Hour** -- connect events stacked by AP
9. **FT vs Open Connects** -- 802.11r fast transition vs plain auth ratio
10. **RSSI Heatmap** -- signal distribution over time in 5 dBm bands
11. **TX Power by Radio** -- current transmit power per radio
12. **802.11r/k/v Status** -- fast roaming protocol config per AP
13. **usteer Config** -- current usteer roaming parameters

## Data sources

**VictoriaMetrics** -- scraped by Telegraf from `prometheus-node-exporter-lua` on each AP:

- `wifi_station_signal_dbm` -- per-station RSSI (labels: `mac`, `ifname`, `instance`)
- `wifi_network_noise_dbm` -- noise floor per radio (labels: `device`, `channel`, `frequency`)
- `wifi_radio_txpower_dbm` -- effective txpower per radio (labels: `device`, `ifname`, `ssid`)
- `wifi_radio_configured_txpower` -- UCI-configured txpower per radio (label: `device`)
- `wifi_radio_channel` -- current channel per radio
- `wifi_radio_frequency_mhz` -- current frequency per radio
- `wifi_usteer_hearing_signal_dbm` -- signal per MAC per AP from usteer hearing map
- `wifi_usteer_hearing_connected` -- whether MAC is connected to AP (0/1)
- `wifi_usteer_roam_events_source` -- roams initiated away from AP
- `wifi_usteer_roam_events_target` -- roams steered to AP
- `wifi_usteer_load` -- channel utilization per AP radio
- `wifi_usteer_associated_clients` -- connected client count per AP
- `wifi_station_name_gauge` -- MAC-to-hostname mapping from station-resolver (labels: `mac`, `station`)

**VictoriaLogs** -- hostapd syslog events shipped via Telegraf:

- `AP-STA-CONNECTED <mac> auth_alg=ft|open` -- connect events
- `AP-STA-DISCONNECTED <mac>` -- disconnect events
- `fields.station` -- resolved hostname enriched by station-resolver

## Collector deployment

The `openwrt/` directory contains an OpenWrt package (`wifi-dethrash-collector`)
that installs a custom `prometheus-node-exporter-lua` collector on each AP.

It exports radio metrics (txpower, channel, frequency), 802.11r/k/v config,
usteer thresholds, and usteer runtime data (hearing map, roam events,
channel load, associated clients). Uses nixio for cached reverse DNS.

### Package build

Build a `.ipk` package using the OpenWrt SDK:

```bash
# From the SDK directory
echo "src-link wifi-dethrash /path/to/openwrt-dethrash/openwrt" >> feeds.conf
./scripts/feeds update wifi-dethrash
./scripts/feeds install wifi-dethrash-collector
make package/wifi-dethrash-collector/compile V=s
```

### Install on AP

```bash
# Add custom feed (once)
echo "src/gz wifi-dethrash http://<feed-server>/openwrt-feed" \
  >> /etc/opkg/customfeeds.conf

# Install (pulls in prometheus-node-exporter-lua, libuci-lua, luci-lib-nixio)
opkg update
opkg install wifi-dethrash-collector
```

## Development

```bash
pip install -e ".[dev]"
pytest -v              # 93 tests
pyright src/ tests/    # zero errors
```
