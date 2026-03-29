# wifi-dethrash

Offline WiFi mesh analyzer for OpenWrt. Detects AP thrashing and weak
associations from historical metrics and logs, recommends txpower and usteer
UCI settings, and generates Grafana dashboards (file export or direct API push).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

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

## Usage

```bash
# With config file (no URL flags needed)
wifi-dethrash

# With explicit URLs
wifi-dethrash --vm-url http://vm:8428 --vl-url http://vl:9428

# Push dashboard to Grafana
wifi-dethrash --push-dashboard

# Export dashboard as JSON file
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

The dashboard includes 12 panels:

1. **RSSI by Station** — per-MAC signal strength over time
2. **Noise Floor** — per-radio noise floor
3. **Connect/Disconnect Events** — hostapd event log
4. **TX Power by Radio** — current and configured txpower
5. **802.11r/k/v Status** — fast roaming config per AP
6. **Usteer Thresholds** — usteer SNR/signal_diff settings
7. **Thrashing Rate** — connects/hour per AP (bar chart)
8. **Roaming Timeline** — which AP each MAC is on over time
9. **RSSI Heatmap** — signal distribution over time
10. **SNR Distribution** — SNR with good/marginal/weak bands
11. **usteer Effectiveness** — ft vs open auth_alg ratio
12. **AP Topology** — floor-by-floor AP map with client counts (requires `[aps]` config)

## Data sources

**VictoriaMetrics** — scraped by Telegraf from `prometheus-node-exporter-lua` on each AP:

- `wifi_station_signal_dbm` — per-station RSSI (labels: `mac`, `ifname`, `instance`)
- `wifi_network_noise_dbm` — noise floor per radio (labels: `device`, `channel`, `frequency`)
- `wifi_radio_txpower_dbm` — effective txpower per radio (labels: `device`, `ifname`, `ssid`)
- `wifi_radio_configured_txpower` — UCI-configured txpower per radio (label: `device`)
- `wifi_radio_channel` — current channel per radio
- `wifi_radio_frequency_mhz` — current frequency per radio

**VictoriaLogs** — hostapd syslog events shipped via Telegraf:

- `AP-STA-CONNECTED <mac> auth_alg=ft|open` — connect events
- `AP-STA-DISCONNECTED <mac>` — disconnect events

## Collector deployment

The `openwrt/` directory contains an OpenWrt package (`wifi-dethrash-collector`)
that installs a custom `prometheus-node-exporter-lua` collector on each AP.

It exports radio metrics (txpower, channel, frequency), 802.11r/k/v config,
and usteer thresholds.

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

# Install (pulls in prometheus-node-exporter-lua and libuci-lua automatically)
opkg update
opkg install wifi-dethrash-collector
```

## Development

```bash
pip install -e ".[dev]"
pytest -v              # 93 tests
pyright src/ tests/    # zero errors
```
