import json
from wifi_dethrash.sources.vm import APInfo


def generate_dashboard(aps: list[APInfo]) -> str:
    """Generate a Grafana dashboard JSON for WiFi mesh health monitoring.

    Output is in Grafana's file-import format with __inputs so the UI
    prompts the user to select their datasources.
    """
    instance_re = "|".join(a.instance for a in aps)

    panels = [
        {
            "id": 1,
            "title": "RSSI by Station",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}',
                    "legendFormat": "{{instance}} / {{mac}}",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dBm",
                    "custom": {"drawStyle": "line", "lineWidth": 1},
                },
                "overrides": [],
            },
            "options": {},
        },
        {
            "id": 2,
            "title": "Noise Floor",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": f'wifi_network_noise_dbm{{instance=~"{instance_re}"}}',
                    "legendFormat": "{{instance}} / {{device}} ({{frequency}} MHz)",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dBm",
                    "custom": {"drawStyle": "line", "lineWidth": 1},
                },
                "overrides": [],
            },
            "options": {},
        },
        {
            "id": 3,
            "title": "Connect/Disconnect Events",
            "type": "logs",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": "tags.appname:hostapd AND _msg:AP-STA-",
                }
            ],
            "options": {},
        },
        {
            "id": 4,
            "title": "TX Power by Radio",
            "type": "table",
            "gridPos": {"h": 6, "w": 12, "x": 0, "y": 24},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": f'wifi_radio_txpower_dbm{{instance=~"{instance_re}"}}',
                    "instant": True,
                    "format": "table",
                },
                {
                    "refId": "B",
                    "expr": f'wifi_radio_configured_txpower{{instance=~"{instance_re}"}}',
                    "instant": True,
                    "format": "table",
                },
            ],
            "fieldConfig": {
                "defaults": {"unit": "dBm"},
                "overrides": [],
            },
            "options": {},
            "transformations": [
                {
                    "id": "merge",
                    "options": {},
                },
            ],
        },
        {
            "id": 5,
            "title": "802.11r/k/v Status",
            "type": "table",
            "gridPos": {"h": 6, "w": 12, "x": 12, "y": 24},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": f'wifi_iface_ieee80211r_enabled{{instance=~"{instance_re}"}}',
                    "instant": True,
                    "format": "table",
                },
                {
                    "refId": "B",
                    "expr": f'wifi_iface_ieee80211k_enabled{{instance=~"{instance_re}"}}',
                    "instant": True,
                    "format": "table",
                },
                {
                    "refId": "C",
                    "expr": f'wifi_iface_ieee80211v_enabled{{instance=~"{instance_re}"}}',
                    "instant": True,
                    "format": "table",
                },
            ],
            "fieldConfig": {
                "defaults": {},
                "overrides": [
                    {
                        "matcher": {"id": "byRegexp", "options": "Value.*"},
                        "properties": [
                            {"id": "mappings", "value": [
                                {"type": "value", "options": {"0": {"text": "Off"}, "1": {"text": "On"}}},
                            ]},
                        ],
                    },
                ],
            },
            "options": {},
            "transformations": [
                {
                    "id": "merge",
                    "options": {},
                },
            ],
        },
        {
            "id": 6,
            "title": "Usteer Thresholds",
            "type": "stat",
            "gridPos": {"h": 4, "w": 24, "x": 0, "y": 30},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {"refId": "A", "expr": "wifi_usteer_min_connect_snr", "legendFormat": "min_connect_snr"},
                {"refId": "B", "expr": "wifi_usteer_min_snr", "legendFormat": "min_snr"},
                {"refId": "C", "expr": "wifi_usteer_roam_scan_snr", "legendFormat": "roam_scan_snr"},
                {"refId": "D", "expr": "wifi_usteer_roam_trigger_snr", "legendFormat": "roam_trigger_snr"},
                {"refId": "E", "expr": "wifi_usteer_signal_diff_threshold", "legendFormat": "signal_diff"},
            ],
            "fieldConfig": {
                "defaults": {"unit": "dB"},
                "overrides": [],
            },
            "options": {"textMode": "value_and_name", "colorMode": "background"},
        },
    ]

    dashboard = {
        "__inputs": [
            {
                "name": "DS_PROMETHEUS",
                "label": "Prometheus",
                "description": "VictoriaMetrics or Prometheus datasource with WiFi metrics",
                "type": "datasource",
                "pluginId": "prometheus",
                "pluginName": "Prometheus",
            },
            {
                "name": "DS_VICTORIALOGS",
                "label": "VictoriaLogs",
                "description": "VictoriaLogs datasource with hostapd syslog events",
                "type": "datasource",
                "pluginId": "victoriametrics-logs-datasource",
                "pluginName": "VictoriaLogs",
            },
        ],
        "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "12.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"},
            {"type": "panel", "id": "timeseries", "name": "Time series", "version": ""},
            {"type": "panel", "id": "logs", "name": "Logs", "version": ""},
            {"type": "panel", "id": "table", "name": "Table", "version": ""},
            {"type": "panel", "id": "stat", "name": "Stat", "version": ""},
        ],
        "id": None,
        "uid": None,
        "title": "WiFi Mesh Health",
        "tags": ["wifi", "openwrt", "mesh"],
        "timezone": "browser",
        "editable": True,
        "schemaVersion": 39,
        "version": 0,
        "panels": panels,
        "time": {"from": "now-24h", "to": "now"},
        "refresh": "30s",
        "templating": {"list": []},
        "annotations": {"list": []},
    }

    return json.dumps(dashboard, indent=2)
