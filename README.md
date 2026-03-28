# wifi-dethrash

Offline WiFi mesh analyzer for OpenWrt. Detects AP thrashing and weak
associations from historical metrics and logs, recommends txpower and usteer
UCI settings, and optionally generates a Grafana dashboard.

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

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--vm-url` | required | VictoriaMetrics base URL |
| `--vl-url` | — | VictoriaLogs base URL (required unless `--generate-dashboard`) |
| `--window` | `24h` | Time window to analyze (e.g. `1h`, `24h`, `7d`) |
| `--host-label` | `instance` | Metric label containing AP hostname |
| `--mac` | all | Filter to specific MAC address(es), repeatable |
| `--overlap-threshold` | `6` | Max RSSI diff (dB) to count as overlap |
| `--snr-threshold` | `15` | Min SNR (dB) for a healthy association |
| `--generate-dashboard` | off | Write Grafana dashboard JSON to file and exit |

### Examples

```bash
# Analyze last 24 hours
wifi-dethrash --vm-url http://vm:8428 --vl-url http://vl:9428

# Analyze last hour for a specific device
wifi-dethrash --vm-url http://vm:8428 --vl-url http://vl:9428 --window 1h --mac aa:bb:cc:dd:ee:ff

# Generate Grafana dashboard (only needs VM, no VL required)
wifi-dethrash --vm-url http://vm:8428 --generate-dashboard dashboard.json
```

### Example output

```
============================================================
  wifi-dethrash report
============================================================

--- Thrashing summary ---
  aa:bb:cc:dd:ee:01  golem <-> pingu  345 connects in 30 episodes  (2026-02-09 to 2026-02-15)

--- RSSI overlap (significant) ---
  aa:bb:cc:dd:ee:01  golem <-> pingu  avg diff 3.2 dB  (89/100 samples = 89%)  [golem: -52 dBm, pingu: -55 dBm]

--- Weak associations ---
  aa:bb:cc:dd:ee:02 on mowgli  avg SNR 8 dB  (200 samples)

--- Recommendations ---
  1. golem <-> pingu (radio1): CRITICAL
     345 thrashing connects across 30 episodes
     RSSI overlap: 3.2 dB avg diff (89% of samples)
     golem: -52 dBm (txpower 23 dBm) | pingu: -55 dBm (txpower 20 dBm)
     -> Reduce golem radio1 txpower: 23 -> 18 dBm
        ssh root@golem uci set wireless.radio1.txpower=18

  usteer:
  ssh root@<ap> uci set usteer.@usteer[0].min_connect_snr=15
    # Reject new associations below 15 dB SNR
  ssh root@<ap> uci set usteer.@usteer[0].min_snr=12
    # Kick existing clients below 12 dB SNR
```

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

The collector also exports:
- `wifi_iface_ieee80211r_enabled`, `wifi_iface_ieee80211k_enabled`, `wifi_iface_ieee80211v_enabled`
- `wifi_usteer_min_connect_snr`, `wifi_usteer_min_snr`, `wifi_usteer_roam_scan_snr`, etc.

## Development

```bash
pip install -e ".[dev]"
pytest -v
```
