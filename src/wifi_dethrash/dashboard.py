import json
from wifi_dethrash.sources.vm import APInfo


def _parse_location(s: str) -> tuple[str, str]:
    """Split 'Ground floor / Living room' into ('Ground floor', 'Living room')."""
    if "/" in s:
        floor, room = s.split("/", 1)
        return floor.strip(), room.strip()
    return s.strip(), ""


def _build_topology_panel(
    ap_locations: dict[str, str],
    panel_id: int,
    y_offset: int,
) -> dict[str, object]:
    """Build a canvas panel showing AP topology grouped by floor."""
    floors: dict[str, list[tuple[str, str]]] = {}
    for ap, location in sorted(ap_locations.items()):
        floor, room = _parse_location(location)
        floors.setdefault(floor, []).append((ap, room))

    elements: list[dict[str, object]] = []
    y = 50
    for floor_name, floor_aps in sorted(floors.items()):
        # Floor label
        elements.append({
            "type": "rectangle",
            "name": f"floor-{floor_name}",
            "config": {
                "backgroundColor": {"fixed": "transparent"},
                "borderColor": {"fixed": "gray"},
                "text": {"fixed": floor_name},
            },
            "placement": {"left": 10, "top": y, "width": 780, "height": 30},
            "background": {"color": {"fixed": "transparent"}},
        })
        y += 40

        x = 30
        for ap, room in floor_aps:
            label = f"{ap}\n{room}" if room else ap
            elements.append({
                "type": "metric-value",
                "name": f"ap-{ap}",
                "config": {
                    "text": {"fixed": label},
                    "backgroundColor": {"fixed": "semi-dark-blue"},
                    "borderColor": {"fixed": "dark-blue"},
                    "color": {"fixed": "white"},
                },
                "placement": {"left": x, "top": y, "width": 140, "height": 60},
                "field": {
                    "source": "A",
                    "filter": [f'instance=~"{ap}:.*"'],
                },
            })
            x += 170
        y += 80

    return {
        "id": panel_id,
        "title": "AP Topology",
        "type": "canvas",
        "gridPos": {"h": 10, "w": 24, "x": 0, "y": y_offset},
        "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
        "targets": [
            {
                "refId": "A",
                "expr": "count(wifi_station_signal_dbm) by (instance)",
                "instant": True,
                "legendFormat": "{{instance}}",
            }
        ],
        "options": {
            "root": {
                "elements": elements,
            },
        },
    }


def _mac_transforms(mac_names: dict[str, str]) -> list[dict[str, object]]:
    """Build Grafana renameByRegex transformations for MAC→hostname."""
    return [
        {
            "id": "renameByRegex",
            "options": {"regex": mac, "renamePattern": name},
        }
        for mac, name in sorted(mac_names.items())
    ]


def _build_panels(
    aps: list[APInfo],
    ap_locations: dict[str, str] | None = None,
    mac_names: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build panel list with datasource placeholders."""
    instance_re = "|".join(a.instance for a in aps)
    mac_tx = _mac_transforms(mac_names) if mac_names else []

    panels: list[dict[str, object]] = [
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
            "transformations": mac_tx,
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
        {
            "id": 7,
            "title": "Thrashing Rate",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 34},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED'
                        ' | stats by (tags.hostname) count() connects'
                    ),
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "short",
                    "custom": {"drawStyle": "bars", "fillOpacity": 30},
                    "displayName": "${__field.labels.tags.hostname}",
                },
                "overrides": [],
            },
            "options": {"tooltip": {"mode": "multi"}},
        },
        {
            "id": 8,
            "title": "Roaming Timeline",
            "type": "state-timeline",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 42},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED'
                        ' | extract "AP-STA-CONNECTED <mac>" from _msg'
                        ' | stats by (mac, tags.hostname) count() connects'
                    ),
                }
            ],
            "fieldConfig": {
                "defaults": {},
                "overrides": [],
            },
            "options": {
                "mergeValues": True,
                "showValue": "auto",
                "alignValue": "left",
            },
        },
        {
            "id": 9,
            "title": "RSSI Heatmap",
            "type": "heatmap",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 50},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}',
                    "legendFormat": "{{instance}} / {{mac}}",
                }
            ],
            "fieldConfig": {
                "defaults": {"unit": "dBm"},
                "overrides": [],
            },
            "options": {
                "calculate": True,
                "calculation": {"xBuckets": {"mode": "size"}, "yBuckets": {"mode": "size", "value": "5"}},
                "color": {"mode": "scheme", "scheme": "RdYlGn", "reverse": True},
                "yAxis": {"unit": "dBm"},
            },
            "transformations": mac_tx,
        },
        {
            "id": 10,
            "title": "SNR Distribution",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 58},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}'
                        f' - on(instance, device) group_left()'
                        f' wifi_network_noise_dbm'
                    ),
                    "legendFormat": "{{instance}} / {{mac}}",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dB",
                    "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10},
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "red", "value": None},
                            {"color": "yellow", "value": 15},
                            {"color": "green", "value": 25},
                        ],
                    },
                },
                "overrides": [],
            },
            "options": {"tooltip": {"mode": "multi"}},
            "transformations": mac_tx,
        },
        {
            "id": 11,
            "title": "usteer Effectiveness",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 66},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND _msg:auth_alg=ft'
                        ' | stats count() ft_roams'
                    ),
                },
                {
                    "refId": "B",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND _msg:auth_alg=open'
                        ' | stats count() open_connects'
                    ),
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "short",
                    "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 20},
                },
                "overrides": [
                    {
                        "matcher": {"id": "byName", "options": "ft_roams"},
                        "properties": [{"id": "color", "value": {"fixedColor": "orange", "mode": "fixed"}}],
                    },
                    {
                        "matcher": {"id": "byName", "options": "open_connects"},
                        "properties": [{"id": "color", "value": {"fixedColor": "blue", "mode": "fixed"}}],
                    },
                ],
            },
            "options": {"tooltip": {"mode": "multi"}},
        },
    ]

    if ap_locations:
        last_y = max(p["gridPos"]["y"] + p["gridPos"]["h"]  # type: ignore[operator]
                     for p in panels)
        panels.append(_build_topology_panel(
            ap_locations, panel_id=len(panels) + 1, y_offset=last_y))

    return panels


def _dashboard_shell(panels: list[dict[str, object]]) -> dict[str, object]:
    """Common dashboard structure shared by both formats."""
    return {
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


def generate_dashboard(
    aps: list[APInfo],
    ap_locations: dict[str, str] | None = None,
) -> str:
    """Generate Grafana dashboard JSON in file-import format.

    Output includes __inputs so the UI prompts for datasource selection.
    """
    panels = _build_panels(aps, ap_locations=ap_locations, mac_names=None)
    dashboard: dict[str, object] = {
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
            {"type": "panel", "id": "state-timeline", "name": "State timeline", "version": ""},
            {"type": "panel", "id": "heatmap", "name": "Heatmap", "version": ""},
            {"type": "panel", "id": "canvas", "name": "Canvas", "version": ""},
        ],
        "id": None,
        "uid": None,
        **_dashboard_shell(panels),
    }
    return json.dumps(dashboard, indent=2)


def generate_dashboard_api(
    aps: list[APInfo],
    prometheus_uid: str,
    victorialogs_uid: str,
    ap_locations: dict[str, str] | None = None,
    mac_names: dict[str, str] | None = None,
) -> dict[str, object]:
    """Generate Grafana dashboard dict for API push.

    Substitutes real datasource UIDs (no __inputs/__requires).
    """
    panels = _build_panels(aps, ap_locations=ap_locations, mac_names=mac_names)
    dashboard = {
        "uid": "wifi-dethrash",
        **_dashboard_shell(panels),
    }

    # Replace datasource placeholders with real UIDs
    raw = json.dumps(dashboard)
    raw = raw.replace("${DS_PROMETHEUS}", prometheus_uid)
    raw = raw.replace("${DS_VICTORIALOGS}", victorialogs_uid)
    return json.loads(raw)
