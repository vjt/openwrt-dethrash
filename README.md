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
| `--vl-url` | required | VictoriaLogs base URL |
| `--window` | `24h` | Time window to analyze (e.g. `1h`, `24h`, `7d`) |
| `--host-label` | `instance` | Metric label containing AP hostname |
| `--mac` | all | Filter to specific MAC address(es), repeatable |
| `--overlap-threshold` | `6` | Max RSSI diff (dB) to count as overlap |
| `--snr-threshold` | `15` | Min SNR (dB) for a healthy association |
| `--target-power` | `14` | Recommended TX power (dBm) |
| `--generate-dashboard` | off | Write Grafana dashboard JSON to file and exit |

### Examples

```bash
# Analyze last 24 hours
wifi-dethrash --vm-url http://vm:8428 --vl-url http://vl:9428

# Analyze last hour for a specific device
wifi-dethrash --vm-url http://vm:8428 --vl-url http://vl:9428 --window 1h --mac aa:bb:cc:dd:ee:ff

# Generate Grafana dashboard
wifi-dethrash --vm-url http://vm:8428 --vl-url http://vl:9428 --generate-dashboard dashboard.json
```

### Example output

```
============================================================
  wifi-dethrash report
============================================================

--- Thrashing sequences ---
  aa:bb:cc:dd:ee:01  golem <-> pingu  47 connects  (08:00:00Z to 08:12:00Z)

--- RSSI overlap ---
  aa:bb:cc:dd:ee:01  golem <-> pingu  avg diff 3.2 dB  (89/100 samples = 89%)

--- Weak associations ---
  aa:bb:cc:dd:ee:02 on mowgli  avg SNR 8 dB  (200 samples)

--- Recommended commands ---
  ssh root@golem uci set wireless.radio1.txpower=14
    # Reduce overlap with pingu on radio1 (avg 3.2 dB difference)
  ssh root@pingu uci set wireless.radio1.txpower=14
    # Reduce overlap with golem on radio1 (avg 3.2 dB difference)
  ssh root@<ap> uci set usteer.@usteer[0].min_connect_snr=15
    # Reject new associations below 15 dB SNR
  ssh root@<ap> uci set usteer.@usteer[0].min_snr=12
    # Kick existing clients below 12 dB SNR
```

## Data sources

**VictoriaMetrics** — scraped by Telegraf from `prometheus-node-exporter-lua` on each AP:

- `wifi_station_signal_dbm` — per-station RSSI (labels: `mac`, `ifname`, `instance`)
- `wifi_network_noise_dbm` — noise floor per radio (labels: `device`, `channel`, `frequency`)

**VictoriaLogs** — hostapd syslog events shipped via Telegraf:

- `AP-STA-CONNECTED <mac> auth_alg=ft|open` — connect events
- `AP-STA-DISCONNECTED <mac>` — disconnect events

## Development

```bash
pip install -e ".[dev]"
pytest -v
```
