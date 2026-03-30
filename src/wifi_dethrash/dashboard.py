import json
from wifi_dethrash.sources.vm import APInfo


def _build_clients_panel(
    instance_re: str,
    snr_expr: str,
    panel_id: int,
    y_offset: int,
) -> dict[str, object]:
    """Build a table showing connected clients, avg RSSI, and avg SNR per AP."""
    return {
        "id": panel_id,
        "title": "Clients per AP",
        "description": "Live client count and average signal quality per AP. RSSI and SNR cells colored by quality thresholds.",
        "type": "table",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": y_offset},
        "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
        "targets": [
            {
                "refId": "A",
                "expr": f'count by (instance)(wifi_station_signal_dbm{{instance=~"{instance_re}"}})',
                "instant": True,
                "format": "table",
            },
            {
                "refId": "B",
                "expr": f'round(avg by (instance)(wifi_station_signal_dbm{{instance=~"{instance_re}"}}), 0.1)',
                "instant": True,
                "format": "table",
            },
            {
                "refId": "C",
                "expr": f'round(avg by (instance)({snr_expr}), 0.1)',
                "instant": True,
                "format": "table",
            },
        ],
        "transformations": [
            {"id": "merge"},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True},
                "renameByName": {
                    "instance": "AP",
                    "Value #A": "Clients",
                    "Value #B": "Avg RSSI",
                    "Value #C": "Avg SNR",
                },
                "indexByName": {
                    "instance": 0,
                    "Value #A": 1,
                    "Value #B": 2,
                    "Value #C": 3,
                },
            }},
        ],
        "fieldConfig": {
            "defaults": {},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Avg RSSI"}, "properties": [
                    {"id": "unit", "value": "dBm"},
                    {"id": "custom.cellOptions", "value": {
                        "type": "color-background", "mode": "basic",
                    }},
                    {"id": "thresholds", "value": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "red", "value": None},
                            {"color": "yellow", "value": -75},
                            {"color": "green", "value": -65},
                        ],
                    }},
                ]},
                {"matcher": {"id": "byName", "options": "Avg SNR"}, "properties": [
                    {"id": "unit", "value": "dB"},
                    {"id": "custom.cellOptions", "value": {
                        "type": "color-background", "mode": "basic",
                    }},
                    {"id": "thresholds", "value": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "red", "value": None},
                            {"color": "yellow", "value": 15},
                            {"color": "green", "value": 25},
                        ],
                    }},
                ]},
            ],
        },
        "options": {
            "sortBy": [{"displayName": "Clients", "desc": True}],
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

    Uses $station variable (allValue=".*") for regex matching in both
    Prometheus (label_match) and VL (fields.station:~"$station") panels.
    """
    if mac_names:
        return f'label_match(label_map({expr}, {_label_map_args(mac_names)}), "mac", "$station")'
    return expr.replace("}", ', mac=~"$station"}', 1) if "}" in expr else expr


_AP_COLORS = [
    "semi-dark-green", "semi-dark-blue", "semi-dark-orange",
    "semi-dark-purple", "semi-dark-yellow", "semi-dark-red",
    "dark-green", "dark-blue",
]


def _build_panels(
    aps: list[APInfo],
    mac_names: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build panel list with datasource placeholders."""
    instance_re = "|".join(a.instance for a in aps)

    rssi_expr = f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}'
    snr_expr = (
        f'wifi_station_signal_dbm{{instance=~"{instance_re}"}}'
        f' - on(instance, ifname) group_left()'
        f' wifi_network_noise_dbm'
    )

    # Roaming timeline: each AP gets a numeric ID, state-timeline uses
    # value mappings to display AP names as colored blocks.
    roaming_parts = [
        f'(group by (mac)(wifi_station_signal_dbm{{instance="{ap.instance}"}}) * 0 + {i})'
        for i, ap in enumerate(aps, 1)
    ]
    roaming_expr = " or ".join(roaming_parts)
    roaming_expr = _wrap_label_map(roaming_expr, mac_names)
    roaming_mappings: list[dict[str, object]] = [
        {"type": "value", "options": {
            str(i): {"text": ap.hostname, "color": _AP_COLORS[(i - 1) % len(_AP_COLORS)]}
            for i, ap in enumerate(aps, 1)
        }},
    ]

    panels: list[dict[str, object]] = [
        {
            "id": 1,
            "title": "Signal Quality",
            "description": "RSSI (solid), SNR (dashed), and noise floor (dotted red) per station. Noise only shows for APs the selected station is connected to.",
            "type": "timeseries",
            "gridPos": {"h": 10, "w": 24, "x": 0, "y": 0},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": _wrap_label_map(rssi_expr, mac_names),
                    "legendFormat": "RSSI {{instance}} / {{mac}}",
                },
                {
                    "refId": "B",
                    "expr": _wrap_label_map(snr_expr, mac_names),
                    "legendFormat": "SNR {{instance}} / {{mac}}",
                },
                {
                    "refId": "C",
                    "expr": (
                        f'wifi_network_noise_dbm{{instance=~"{instance_re}"}}'
                        f' and on(instance, ifname)'
                        f' (group by (instance, ifname)({_wrap_label_map(rssi_expr, mac_names)}))'
                    ),
                    "legendFormat": "Noise {{instance}} / {{ifname}}",
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "dBm",
                    "custom": {"drawStyle": "line", "lineWidth": 1},
                },
                "overrides": [
                    {"matcher": {"id": "byFrameRefID", "options": "B"}, "properties": [
                        {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}},
                    ]},
                    {"matcher": {"id": "byFrameRefID", "options": "C"}, "properties": [
                        {"id": "custom.lineWidth", "value": 2},
                        {"id": "custom.lineStyle", "value": {"fill": "dot"}},
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "dark-red"}},
                    ]},
                ],
            },
            "options": {"tooltip": {"mode": "multi"}},
        },
        {
            "id": 3,
            "title": "Connect/Disconnect Events",
            "description": "Hostapd AP-STA-CONNECTED/DISCONNECTED events with resolved station names. Green = connect, red = disconnect.",
            "type": "logs",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 10},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND _msg:auth_alg'
                        ' AND fields.station:~"$station"'
                        ' | extract "AP-STA-CONNECTED <mac> auth_alg=<auth>" from _msg'
                        ' | format "🟢 <_time> <fields.station> ▸ <tags.hostname> (<auth>) · <mac>" as _msg'
                    ),
                },
                {
                    "refId": "B",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND NOT _msg:auth_alg'
                        ' AND fields.station:~"$station"'
                        ' | extract "AP-STA-CONNECTED <mac>" from _msg'
                        ' | format "🟢 <_time> <fields.station> ▸ <tags.hostname> (open) · <mac>" as _msg'
                    ),
                },
                {
                    "refId": "C",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-DISCONNECTED AND fields.station:~"$station"'
                        ' | extract "AP-STA-DISCONNECTED <mac>" from _msg'
                        ' | format "🔴 <_time> <fields.station> ◂ <tags.hostname> · <mac>" as _msg'
                    ),
                },
            ],
            "options": {},
        },
        {
            "id": 4,
            "title": "TX Power by Radio",
            "description": "Current transmit power per radio. Higher = more coverage but more overlap between APs.",
            "type": "bargauge",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 18},
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
            "description": "Fast roaming support per AP. 3/3 = all protocols enabled (r=fast transition, k=neighbor reports, v=BSS transition).",
            "type": "table",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 18},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": (
                        f'wifi_iface_ieee80211r_enabled{{instance=~"{instance_re}"}}'
                        f' + on(instance, device, ifname, ssid) wifi_iface_ieee80211k_enabled'
                        f' + on(instance, device, ifname, ssid) wifi_iface_ieee80211v_enabled'
                    ),
                    "instant": True,
                    "format": "table",
                },
            ],
            "transformations": [
                {"id": "organize", "options": {
                    "excludeByName": {
                        "Time": True, "__name__": True, "device": True,
                        "ifname": True, "metric_format": True, "metric_source": True,
                    },
                    "renameByName": {
                        "instance": "AP",
                        "ssid": "SSID",
                        "Value": "Score",
                    },
                    "indexByName": {"instance": 0, "ssid": 1, "Value": 2},
                }},
            ],
            "fieldConfig": {
                "defaults": {},
                "overrides": [
                    {"matcher": {"id": "byName", "options": "Score"}, "properties": [
                        {"id": "mappings", "value": [
                            {"type": "value", "options": {
                                "0": {"text": "❌ 0/3", "color": "red"},
                                "1": {"text": "⚠️ 1/3", "color": "yellow"},
                                "2": {"text": "⚠️ 2/3", "color": "yellow"},
                                "3": {"text": "✅ 3/3", "color": "green"},
                            }},
                        ]},
                        {"id": "custom.cellOptions", "value": {
                            "type": "color-background", "mode": "basic",
                        }},
                        {"id": "thresholds", "value": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "red", "value": None},
                                {"color": "yellow", "value": 1},
                                {"color": "green", "value": 3},
                            ],
                        }},
                    ]},
                ],
            },
            "options": {
                "sortBy": [{"displayName": "AP"}],
            },
        },
        {
            "id": 6,
            "title": "usteer Config",
            "description": "Key usteer roaming parameters. signal_diff = min dB improvement to trigger roam, roam_scan_snr = min SNR to start scanning.",
            "type": "stat",
            "gridPos": {"h": 4, "w": 24, "x": 0, "y": 24},
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
            "description": "AP-STA-CONNECTED events per hour, stacked by AP. Spikes indicate thrashing or mass reconnections.",
            "type": "timeseries",
            "interval": "1m",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 28},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "queryType": "statsRange",
                    "legendFormat": "{{tags.hostname}}",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED'
                        ' AND fields.station:~"$station"'
                        ' | stats by (tags.hostname) count() connects'
                    ),
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "short",
                    "custom": {
                        "drawStyle": "line",
                        "lineWidth": 2,
                        "fillOpacity": 20,
                        "stacking": {"mode": "normal"},
                        "showPoints": "never",
                    },
                    "noValue": "0",
                },
                "overrides": [],
            },
            "options": {
                "tooltip": {"mode": "multi", "sort": "desc"},
                "legend": {"displayMode": "list", "placement": "bottom"},
            },
        },
        {
            "id": 8,
            "title": "Roaming Timeline",
            "description": "Which AP each station is connected to over time. Color changes = roaming events. Derived from RSSI metric presence.",
            "type": "state-timeline",
            "gridPos": {"h": 10, "w": 24, "x": 0, "y": 36},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {
                    "refId": "A",
                    "expr": roaming_expr,
                    "legendFormat": "{{mac}}",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "mappings": roaming_mappings,
                    "custom": {"fillOpacity": 80},
                },
                "overrides": [],
            },
            "options": {
                "showValue": "auto",
                "mergeValues": True,
                "alignValue": "left",
                "legend": {"displayMode": "list", "placement": "bottom"},
                "tooltip": {"mode": "single"},
            },
        },
        {
            "id": 9,
            "title": "RSSI Heatmap",
            "description": "Signal strength distribution over time in 5 dBm bands. Darker = more readings in that band. Tight cluster = stable, spread = varying signal.",
            "type": "heatmap",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 46},
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
                "color": {"mode": "scheme", "scheme": "Blues"},
                "yAxis": {"unit": "dBm"},
            },
        },
        {
            "id": 11,
            "title": "FT vs Open Connects",
            "description": "Fast transition (802.11r) roams vs plain open connections. High FT ratio = clients are roaming seamlessly between APs.",
            "type": "timeseries",
            "interval": "1m",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 54},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {
                    "refId": "A",
                    "queryType": "statsRange",
                    "legendFormat": "ft roams",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND _msg:"auth_alg=ft"'
                        ' | stats count() ft_roams'
                    ),
                },
                {
                    "refId": "B",
                    "queryType": "statsRange",
                    "legendFormat": "open connects",
                    "expr": (
                        'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND _msg:"auth_alg=open"'
                        ' | stats count() open_connects'
                    ),
                },
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "short",
                    "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 20, "showPoints": "never"},
                    "noValue": "0",
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

    last_y = max(p["gridPos"]["y"] + p["gridPos"]["h"]  # type: ignore[operator]
                 for p in panels)
    panels.append(_build_clients_panel(
        instance_re, snr_expr, panel_id=len(panels) + 1, y_offset=last_y))

    return panels


def _station_variables() -> list[dict[str, object]]:
    """Build station selector variable.

    Dynamic query variable using VL field_values endpoint.
    Single variable with allValue=".*" works for both datasources:
    - Prometheus: label_match(..., "mac", "$station") — regex match
    - VictoriaLogs: fields.station:~"$station" — LogsQL regex filter
    """
    return [
        {
            "name": "station",
            "label": "Station",
            "type": "query",
            "datasource": {
                "type": "victoriametrics-logs-datasource",
                "uid": "${DS_VICTORIALOGS}",
            },
            "query": {
                "type": "fieldValue",
                "field": "fields.station",
                "query": "tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND fields.station:*",
                "limit": 500,
            },
            "includeAll": True,
            "allValue": ".*",
            "multi": False,
            "refresh": 1,
            "sort": 1,
        },
    ]


def _dashboard_shell(panels: list[dict[str, object]]) -> dict[str, object]:
    """Common dashboard structure shared by both formats."""
    variables = _station_variables()

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
) -> str:
    """Generate Grafana dashboard JSON in file-import format.

    Output includes __inputs so the UI prompts for datasource selection.
    """
    panels = _build_panels(aps, mac_names=None)
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
    mac_names: dict[str, str] | None = None,
) -> dict[str, object]:
    """Generate Grafana dashboard dict for API push.

    Substitutes real datasource UIDs (no __inputs/__requires).
    """
    panels = _build_panels(aps, mac_names=mac_names)
    dashboard = {
        "uid": "wifi-dethrash",
        **_dashboard_shell(panels),
    }

    # Replace datasource placeholders with real UIDs
    raw = json.dumps(dashboard)
    raw = raw.replace("${DS_PROMETHEUS}", prometheus_uid)
    raw = raw.replace("${DS_VICTORIALOGS}", victorialogs_uid)
    return json.loads(raw)
