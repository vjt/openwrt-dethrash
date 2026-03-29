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


def _label_map_args(mac_names: dict[str, str]) -> str:
    """Build label_map() arguments for MAC→hostname substitution.

    VictoriaMetrics MetricsQL: label_map(q, "label", "src1", "dst1", ...)
    MACs uppercased to match Prometheus label values.
    """
    pairs = ", ".join(
        f'"{mac.upper()}", "{name}"'
        for mac, name in sorted(mac_names.items())
    )
    return f'"mac", {pairs}'


def _wrap_label_map(expr: str, mac_names: dict[str, str] | None) -> str:
    """Wrap a PromQL expression with label_map() and station filter.

    With mac_names: label_match(label_map(expr, ...), "mac", "$station")
    Without: adds mac=~"$station" selector directly.
    """
    if mac_names:
        return f'label_match(label_map({expr}, {_label_map_args(mac_names)}), "mac", "$station")'
    return expr.replace("}", ', mac=~"$station"}', 1) if "}" in expr else expr


def _build_panels(
    aps: list[APInfo],
    ap_locations: dict[str, str] | None = None,
    mac_names: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build panel list with datasource placeholders."""
    instance_re = "|".join(a.instance for a in aps)

    rssi_expr = f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}'
    snr_expr = (
        f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}'
        f' - on(instance, device) group_left()'
        f' wifi_network_noise_dbm'
    )

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
                    "expr": _wrap_label_map(rssi_expr, mac_names),
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
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED'
                        ' | extract "AP-STA-CONNECTED <mac> auth_alg=<auth>" from _msg'
                        ' | format "🟢 <_time> <fields.station> (<mac>) ▸ <tags.hostname> (<auth>)" as _msg'
                    ),
                },
                {
                    "refId": "B",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-DISCONNECTED'
                        ' | extract "AP-STA-DISCONNECTED <mac>" from _msg'
                        ' | format "🔴 <_time> <fields.station> (<mac>) ◂ <tags.hostname>" as _msg'
                    ),
                },
            ],
            "options": {},
        },
        {
            "id": 4,
            "title": "TX Power by Radio",
            "type": "bargauge",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 24},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": f'wifi_radio_txpower_dbm{{instance=~"{instance_re}"}}',
                    "instant": True,
                    "legendFormat": "{{instance}} / {{device}} ({{ssid}})",
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dBm",
                    "min": 0,
                    "max": 30,
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "yellow", "value": None},
                            {"color": "green", "value": 10},
                            {"color": "orange", "value": 23},
                        ],
                    },
                },
                "overrides": [],
            },
            "options": {
                "orientation": "horizontal",
                "displayMode": "gradient",
                "showUnfilled": True,
                "valueMode": "color",
                "textSizeMode": "auto",
            },
        },
        {
            "id": 5,
            "title": "802.11r/k/v Status",
            "type": "stat",
            "gridPos": {"h": 4, "w": 12, "x": 12, "y": 24},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        f'wifi_iface_ieee80211r_enabled{{instance=~"{instance_re}"}}'
                        f' + on(instance, device, ifname, ssid) wifi_iface_ieee80211k_enabled'
                        f' + on(instance, device, ifname, ssid) wifi_iface_ieee80211v_enabled'
                    ),
                    "legendFormat": "{{instance}} / {{ssid}}",
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "mappings": [
                        {"type": "value", "options": {
                            "0": {"text": "❌ disabled", "color": "red"},
                            "1": {"text": "⚠️ 1/3", "color": "yellow"},
                            "2": {"text": "⚠️ 2/3", "color": "yellow"},
                            "3": {"text": "✅ r/k/v", "color": "green"},
                        }},
                    ],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "red", "value": None},
                            {"color": "yellow", "value": 1},
                            {"color": "green", "value": 3},
                        ],
                    },
                },
                "overrides": [],
            },
            "options": {
                "textMode": "value_and_name",
                "colorMode": "background",
                "reduceOptions": {"calcs": ["lastNotNull"]},
            },
        },
        {
            "id": 6,
            "title": "usteer Config",
            "type": "stat",
            "gridPos": {"h": 4, "w": 24, "x": 0, "y": 30},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": "avg(wifi_usteer_signal_diff_threshold)",
                    "legendFormat": "signal_diff",
                },
                {
                    "refId": "B",
                    "expr": "avg(wifi_usteer_roam_scan_snr)",
                    "legendFormat": "roam_scan_snr",
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dB",
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "blue", "value": None},
                        ],
                    },
                },
                "overrides": [],
            },
            "options": {
                "textMode": "value_and_name",
                "colorMode": "background",
                "graphMode": "none",
                "reduceOptions": {"calcs": ["lastNotNull"]},
            },
        },
        {
            "id": 7,
            "title": "Connects per Hour",
            "type": "barchart",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 34},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED'
                        ' | stats by (_time:1h, tags.hostname) count() connects'
                    ),
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "short",
                },
                "overrides": [],
            },
            "options": {
                "stacking": "normal",
                "tooltip": {"mode": "multi"},
            },
            "transformations": [
                {"id": "convertFieldType", "options": {
                    "conversions": [{"targetField": "connects", "destinationType": "number"}],
                }},
            ],
        },
        {
            "id": 8,
            "title": "Roaming Events",
            "type": "table",
            "gridPos": {"h": 10, "w": 24, "x": 0, "y": 42},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED'
                        ' | extract_regexp "CONNECTED (?P<mac>[0-9a-fA-F:]{17})" from _msg'
                        ' | extract "auth_alg=<auth>" from _msg'
                        ' | fields _time, fields.station, mac, tags.hostname, auth'
                    ),
                }
            ],
            "fieldConfig": {
                "defaults": {},
                "overrides": [
                    {"matcher": {"id": "byName", "options": "_time"}, "properties": [
                        {"id": "displayName", "value": "Time"},
                    ]},
                    {"matcher": {"id": "byName", "options": "fields.station"}, "properties": [
                        {"id": "displayName", "value": "Station"},
                    ]},
                    {"matcher": {"id": "byName", "options": "mac"}, "properties": [
                        {"id": "displayName", "value": "MAC"},
                    ]},
                    {"matcher": {"id": "byName", "options": "tags.hostname"}, "properties": [
                        {"id": "displayName", "value": "AP"},
                    ]},
                    {"matcher": {"id": "byName", "options": "auth"}, "properties": [
                        {"id": "displayName", "value": "Auth"},
                    ]},
                ],
            },
            "options": {
                "sortBy": [{"displayName": "Time", "desc": True}],
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
                    "expr": _wrap_label_map(rssi_expr, mac_names),
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
                    "expr": _wrap_label_map(snr_expr, mac_names),
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


def _station_variable() -> dict[str, object]:
    """Build a station selector variable from VictoriaLogs.

    Queries unique fields.station values from hostapd events.
    Dynamic — new devices appear as they connect.
    """
    return {
        "name": "station",
        "label": "Station",
        "type": "query",
        "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
        "query": "tags.appname:hostapd AND fields.station:* | field_values fields.station limit 200",
        "includeAll": True,
        "allValue": ".*",
        "multi": False,
        "sort": 1,
        "refresh": 2,
    }


def _dashboard_shell(panels: list[dict[str, object]]) -> dict[str, object]:
    """Common dashboard structure shared by both formats."""
    variables = [_station_variable()]

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
        "templating": {"list": variables},
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
