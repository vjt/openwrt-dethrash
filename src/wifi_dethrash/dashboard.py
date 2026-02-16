import json
from wifi_dethrash.sources.vm import APInfo


def generate_dashboard(
    aps: list[APInfo],
    datasource: str = "Prometheus",
    logs_datasource: str = "VictoriaLogs",
) -> str:
    """Generate a Grafana dashboard JSON for WiFi mesh health monitoring."""
    instance_re = "|".join(a.instance for a in aps)

    panels = [
        {
            "title": "RSSI by Station",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0},
            "datasource": {"type": "prometheus", "uid": datasource},
            "targets": [
                {
                    "expr": f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}',
                    "legendFormat": "{{instance}} / {{mac}}",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dBm",
                    "custom": {"drawStyle": "line", "lineWidth": 1},
                }
            },
        },
        {
            "title": "Noise Floor",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8},
            "datasource": {"type": "prometheus", "uid": datasource},
            "targets": [
                {
                    "expr": f'wifi_network_noise_dbm{{instance=~"{instance_re}"}}',
                    "legendFormat": "{{instance}} / {{device}} ({{frequency}} MHz)",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dBm",
                    "custom": {"drawStyle": "line", "lineWidth": 1},
                }
            },
        },
        {
            "title": "Connect/Disconnect Events",
            "type": "logs",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16},
            "datasource": {"type": "victorialogs-datasource", "uid": logs_datasource},
            "targets": [
                {
                    "expr": "tags.appname:hostapd AND _msg:AP-STA-",
                }
            ],
        },
    ]

    dashboard = {
        "dashboard": {
            "title": "WiFi Mesh Health",
            "tags": ["wifi", "openwrt", "mesh"],
            "timezone": "browser",
            "panels": panels,
            "time": {"from": "now-24h", "to": "now"},
            "refresh": "30s",
        },
        "overwrite": True,
    }

    return json.dumps(dashboard, indent=2)
