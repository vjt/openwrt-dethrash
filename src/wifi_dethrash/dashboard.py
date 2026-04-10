import json
from wifi_dethrash.sources.vm import APInfo


def _build_clients_panel(
    instance_re: str,
    snr_expr: str,
    panel_id: int,
    y_offset: int,
    width: int = 12,
    x_offset: int = 0,
    height: int = 8,
) -> dict[str, object]:
    """Build a table showing connected clients, avg RSSI, and avg SNR per AP."""
    return {
        "id": panel_id,
        "title": "Clients per AP",
        "description": "Live client count and average signal quality per AP. RSSI and SNR cells colored by quality thresholds.",
        "type": "table",
        "gridPos": {"h": height, "w": width, "x": x_offset, "y": y_offset},
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


def _with_station(expr: str) -> str:
    """Add station name via group_left join, filter by $station variable.

    Joins with wifi_station_name_gauge (from station-resolver) to add
    the 'station' label, then filters by the dashboard's $station
    variable. Fully dynamic — no baked-in mapping needed.

    The gauge is aggregated by (mac, station) to collapse series that
    differ only in labels added later (e.g. 'ip'), which would otherwise
    cause duplicate matches and duplicated timeline bars.
    """
    return (
        f'label_match('
        f'({expr}) * on(mac) group_left(station) max by (mac, station)(wifi_station_name_gauge)'
        f', "station", "$station")'
    )


_AP_COLORS = [
    "semi-dark-green", "semi-dark-blue", "semi-dark-orange",
    "semi-dark-purple", "semi-dark-yellow", "semi-dark-red",
    "dark-green", "dark-blue",
]


def _build_panels(
    aps: list[APInfo],
    station_field: str = "station",
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
    roaming_expr = _with_station(roaming_expr)
    roaming_mappings: list[dict[str, object]] = [
        {"type": "value", "options": {
            str(i): {"text": ap.hostname, "color": _AP_COLORS[(i - 1) % len(_AP_COLORS)]}
            for i, ap in enumerate(aps, 1)
        }},
    ]

    y = 0
    panels: list[dict[str, object]] = [
        # === TOP: at-a-glance ===
        {
            "id": 1, "title": "Roaming Timeline",
            "description": "Which AP each station is connected to over time. Color changes = roaming events.",
            "type": "state-timeline",
            "gridPos": {"h": 10, "w": 24, "x": 0, "y": (y := 0)},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [{"refId": "A", "expr": roaming_expr, "legendFormat": "{{station}}"}],
            "fieldConfig": {"defaults": {"mappings": roaming_mappings, "custom": {"fillOpacity": 80}}, "overrides": []},
            "options": {"showValue": "auto", "mergeValues": True, "alignValue": "left",
                        "legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "single"}},
        },
        {
            "id": 2, "title": "Signal Quality",
            "description": "RSSI (solid), SNR (dashed), and noise floor (dotted red) per station. Noise only shows for APs the selected station is connected to.",
            "type": "timeseries",
            "gridPos": {"h": 14, "w": 24, "x": 0, "y": (y := y + 10)},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {"refId": "A", "expr": _with_station(rssi_expr), "legendFormat": "RSSI {{instance}} / {{station}}"},
                {"refId": "B", "expr": _with_station(snr_expr), "legendFormat": "SNR {{instance}} / {{station}}"},
                {"refId": "C", "legendFormat": "Noise {{instance}} / {{ifname}}", "expr": (
                    f'wifi_network_noise_dbm{{instance=~"{instance_re}"}}'
                    f' and on(instance, ifname) (group by (instance, ifname)({_with_station(rssi_expr)}))'
                )},
            ],
            "fieldConfig": {"defaults": {"unit": "dBm", "custom": {"drawStyle": "line", "lineWidth": 1}}, "overrides": [
                {"matcher": {"id": "byFrameRefID", "options": "B"}, "properties": [
                    {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}}]},
                {"matcher": {"id": "byFrameRefID", "options": "C"}, "properties": [
                    {"id": "custom.lineWidth", "value": 2},
                    {"id": "custom.lineStyle", "value": {"fill": "dot"}},
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": "dark-red"}}]},
            ]},
            "options": {"tooltip": {"mode": "multi"},
                        "legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull"]}},
        },
        # === usteer visibility ===
        {
            "id": 3, "title": "Hearing Map",
            "description": "Signal strength of the selected station as seen by all APs. Shows usteer's roaming decision data — when signals cross, a roam happens. Select a single station for best results.",
            "type": "timeseries",
            "gridPos": {"h": 10, "w": 24, "x": 0, "y": (y := y + 14)},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [{"refId": "A", "legendFormat": "{{station}} · {{ap}}", "expr":
                         _with_station(
                             f'max by (mac, ap)(wifi_usteer_hearing_signal_dbm{{instance=~"{instance_re}"}})'
                             f' and on(mac) group by (mac)(wifi_station_signal_dbm{{instance=~"{instance_re}"}})')}],
            "fieldConfig": {"defaults": {"unit": "dBm", "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 5}},
                "overrides": []},
            "options": {"tooltip": {"mode": "multi"},
                        "legend": {"displayMode": "list", "placement": "bottom"}},
        },
        {
            "id": 4, "title": "Channel Load",
            "description": "Channel utilization per AP radio as reported by usteer. High load may trigger client steering.",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": (y := y + 10)},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [{"refId": "A", "legendFormat": "{{ap}}",
                         "expr": f'max by (ap)(wifi_usteer_load{{instance=~"{instance_re}"}})'  }],
            "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "custom": {
                "drawStyle": "line", "lineWidth": 2, "fillOpacity": 20}}, "overrides": []},
            "options": {"tooltip": {"mode": "multi"},
                        "legend": {"displayMode": "list", "placement": "bottom"}},
        },
        {
            "id": 5, "title": "Roam Events (usteer)",
            "description": "Roams initiated by usteer per AP. Source = steered away, Target = steered to. Counters reset on service restart.",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": y},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {"refId": "A", "legendFormat": "{{ap}} source",
                 "expr": f'increase(max by (ap)(wifi_usteer_roam_events_source{{instance=~"{instance_re}"}})[5m:])'  },
                {"refId": "B", "legendFormat": "{{ap}} target",
                 "expr": f'increase(max by (ap)(wifi_usteer_roam_events_target{{instance=~"{instance_re}"}})[5m:])'  },
            ],
            "fieldConfig": {"defaults": {"unit": "short", "custom": {
                "drawStyle": "line", "lineWidth": 2, "fillOpacity": 10}}, "overrides": []},
            "options": {"tooltip": {"mode": "multi"},
                        "legend": {"displayMode": "list", "placement": "bottom"}},
        },
        # === MIDDLE: events + clients side by side ===
        {
            "id": 6, "title": "Connect/Disconnect Events",
            "description": "Hostapd connect/disconnect events with resolved station names.",
            "type": "logs",
            "gridPos": {"h": 12, "w": 12, "x": 0, "y": (y := y + 8)},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {"refId": "A", "expr": (
                    f'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND _msg:auth_alg AND fields.{station_field}:~"$station"'
                    f' | extract "AP-STA-CONNECTED <mac> auth_alg=<auth>" from _msg'
                    f' | format "🟢 <_time> <fields.{station_field}> ▸ <tags.hostname> (<auth>) · <mac>" as _msg')},
                {"refId": "B", "expr": (
                    f'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND NOT _msg:auth_alg AND fields.{station_field}:~"$station"'
                    f' | extract "AP-STA-CONNECTED <mac>" from _msg'
                    f' | format "🟢 <_time> <fields.{station_field}> ▸ <tags.hostname> (open) · <mac>" as _msg')},
                {"refId": "C", "expr": (
                    f'tags.appname:hostapd AND _msg:AP-STA-DISCONNECTED AND fields.{station_field}:~"$station"'
                    f' | extract "AP-STA-DISCONNECTED <mac>" from _msg'
                    f' | format "🔴 <_time> <fields.{station_field}> ◂ <tags.hostname> · <mac>" as _msg')},
            ],
            "options": {},
        },
        _build_clients_panel(instance_re, snr_expr, panel_id=7, y_offset=y, width=12, x_offset=12, height=12),
        # === ACTIVITY: time series ===
        {
            "id": 8, "title": "Connects per Hour",
            "description": "AP-STA-CONNECTED events stacked by AP. Spikes indicate thrashing or mass reconnections.",
            "type": "timeseries", "interval": "1m",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": (y := y + 12)},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [{"refId": "A", "queryType": "statsRange", "legendFormat": "{{tags.hostname}}", "expr": (
                f'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND fields.{station_field}:~"$station"'
                ' | stats by (tags.hostname) count() connects')}],
            "fieldConfig": {"defaults": {"unit": "short", "noValue": "0", "custom": {
                "drawStyle": "line", "lineWidth": 2, "fillOpacity": 20,
                "stacking": {"mode": "normal"}, "showPoints": "never"}}, "overrides": []},
            "options": {"tooltip": {"mode": "multi", "sort": "desc"},
                        "legend": {"displayMode": "list", "placement": "bottom"}},
        },
        {
            "id": 9, "title": "FT vs Open Connects",
            "description": "Fast transition (802.11r) roams vs plain open connections.",
            "type": "timeseries", "interval": "1m",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": (y := y + 8)},
            "datasource": {"type": "victoriametrics-logs-datasource", "uid": "${DS_VICTORIALOGS}"},
            "targets": [
                {"refId": "A", "queryType": "statsRange", "legendFormat": "ft roams", "expr": (
                    'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND _msg:"auth_alg=ft" | stats count() ft_roams')},
                {"refId": "B", "queryType": "statsRange", "legendFormat": "open connects", "expr": (
                    'tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND _msg:"auth_alg=open" | stats count() open_connects')},
            ],
            "fieldConfig": {"defaults": {"unit": "short", "noValue": "0",
                "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 20, "showPoints": "never"}},
                "overrides": [
                    {"matcher": {"id": "byName", "options": "ft_roams"},
                     "properties": [{"id": "color", "value": {"fixedColor": "orange", "mode": "fixed"}}]},
                    {"matcher": {"id": "byName", "options": "open_connects"},
                     "properties": [{"id": "color", "value": {"fixedColor": "blue", "mode": "fixed"}}]}]},
            "options": {"tooltip": {"mode": "multi"}},
        },
        {
            "id": 10, "title": "RSSI Heatmap",
            "description": "Signal strength distribution over time in 5 dBm bands. Darker = more readings.",
            "type": "heatmap",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": (y := y + 8)},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [{"refId": "A", "expr": _with_station(rssi_expr), "legendFormat": "{{instance}} / {{station}}"}],
            "fieldConfig": {"defaults": {"unit": "dBm"}, "overrides": []},
            "options": {"calculate": True,
                        "calculation": {"xBuckets": {"mode": "size"}, "yBuckets": {"mode": "size", "value": "5"}},
                        "color": {"mode": "scheme", "scheme": "Blues"}, "yAxis": {"unit": "dBm"}},
        },
        # === BOTTOM: config reference (rarely changes) ===
        {
            "id": 11, "title": "TX Power by Radio",
            "description": "Current transmit power per radio.",
            "type": "bargauge",
            "gridPos": {"h": 8, "w": 8, "x": 0, "y": (y := y + 8)},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [{"refId": "A", "expr": f'wifi_radio_txpower_dbm{{instance=~"{instance_re}"}}',
                         "instant": True, "legendFormat": "{{instance}} / {{device}} ({{ssid}})"}],
            "fieldConfig": {"defaults": {"unit": "dBm", "min": 0, "max": 30,
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": "yellow", "value": None}, {"color": "green", "value": 10}, {"color": "orange", "value": 23}]}},
                "overrides": []},
            "options": {"orientation": "horizontal", "displayMode": "gradient",
                        "showUnfilled": True, "valueMode": "color", "textSizeMode": "auto"},
        },
        {
            "id": 12, "title": "802.11r/k/v Status",
            "description": "Fast roaming protocol support per AP/SSID.",
            "type": "table",
            "gridPos": {"h": 8, "w": 8, "x": 8, "y": y},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [{"refId": "A", "instant": True, "format": "table", "expr": (
                f'wifi_iface_ieee80211r_enabled{{instance=~"{instance_re}"}}'
                f' + on(instance, device, ifname, ssid) wifi_iface_ieee80211k_enabled'
                f' + on(instance, device, ifname, ssid) wifi_iface_ieee80211v_enabled')}],
            "transformations": [{"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "device": True,
                                  "ifname": True, "metric_format": True, "metric_source": True},
                "renameByName": {"instance": "AP", "ssid": "SSID", "Value": "Score"},
                "indexByName": {"instance": 0, "ssid": 1, "Value": 2}}}],
            "fieldConfig": {"defaults": {}, "overrides": [
                {"matcher": {"id": "byName", "options": "Score"}, "properties": [
                    {"id": "mappings", "value": [{"type": "value", "options": {
                        "0": {"text": "❌ 0/3", "color": "red"}, "1": {"text": "⚠️ 1/3", "color": "yellow"},
                        "2": {"text": "⚠️ 2/3", "color": "yellow"}, "3": {"text": "✅ 3/3", "color": "green"}}}]},
                    {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "red", "value": None}, {"color": "yellow", "value": 1}, {"color": "green", "value": 3}]}}]}]},
            "options": {"sortBy": [{"displayName": "AP"}]},
        },
        {
            "id": 13, "title": "usteer Config",
            "description": "Current usteer roaming parameters across all APs.",
            "type": "table",
            "gridPos": {"h": 8, "w": 8, "x": 16, "y": y},
            "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            "targets": [
                {"refId": "A", "expr": "avg(wifi_usteer_signal_diff_threshold)", "instant": True, "format": "table"},
                {"refId": "B", "expr": "avg(wifi_usteer_roam_scan_snr)", "instant": True, "format": "table"},
                {"refId": "C", "expr": "avg(wifi_usteer_roam_trigger_snr)", "instant": True, "format": "table"},
                {"refId": "D", "expr": "avg(wifi_usteer_min_snr)", "instant": True, "format": "table"},
                {"refId": "E", "expr": "avg(wifi_usteer_min_connect_snr)", "instant": True, "format": "table"},
                {"refId": "F", "expr": "avg(wifi_usteer_load_kick_enabled)", "instant": True, "format": "table"},
            ],
            "transformations": [
                {"id": "merge"},
                {"id": "organize", "options": {
                    "excludeByName": {"Time": True},
                    "renameByName": {
                        "Value #A": "signal_diff",
                        "Value #B": "roam_scan_snr",
                        "Value #C": "roam_trigger_snr",
                        "Value #D": "min_snr",
                        "Value #E": "min_connect_snr",
                        "Value #F": "load_kick",
                    },
                }},
                {"id": "reduce", "options": {"reducers": ["lastNotNull"], "includeTimeField": False}},
                {"id": "organize", "options": {
                    "renameByName": {"Field": "Parameter", "Last *": "Value"},
                }},
            ],
            "fieldConfig": {"defaults": {"unit": "dB"}, "overrides": [
                {"matcher": {"id": "byName", "options": "load_kick"}, "properties": [
                    {"id": "unit", "value": "bool_on_off"},
                ]},
            ]},
            "options": {},
        },
    ]

    return panels


def _station_variables(station_field: str = "station") -> list[dict[str, object]]:
    """Build station selector variable.

    Dynamic query variable using VL field_values endpoint.
    Single variable with allValue=".*" works for both datasources:
    - Prometheus: label_match(..., "station", "$station") — regex match
    - VictoriaLogs: fields.<station_field>:~"$station" — LogsQL regex filter
    """
    vl_field = f"fields.{station_field}"
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
                "field": vl_field,
                "query": f"tags.appname:hostapd AND _msg:AP-STA-CONNECTED AND {vl_field}:*",
                "limit": 500,
            },
            "includeAll": True,
            "allValue": ".*",
            "multi": False,
            "refresh": 1,
            "sort": 1,
        },
    ]


def _dashboard_shell(panels: list[dict[str, object]], station_field: str = "station") -> dict[str, object]:
    """Common dashboard structure shared by both formats."""
    variables = _station_variables(station_field)

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
        "graphTooltip": 1,
        "templating": {"list": variables},
        "annotations": {"list": []},
    }


def generate_dashboard(
    aps: list[APInfo],
    station_field: str = "station",
) -> str:
    """Generate Grafana dashboard JSON in file-import format.

    Output includes __inputs so the UI prompts for datasource selection.
    """
    panels = _build_panels(aps, station_field=station_field)
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
        ],
        "id": None,
        "uid": None,
        **_dashboard_shell(panels, station_field=station_field),
    }
    return json.dumps(dashboard, indent=2)


def generate_dashboard_api(
    aps: list[APInfo],
    prometheus_uid: str,
    victorialogs_uid: str,
    station_field: str = "station",
) -> dict[str, object]:
    """Generate Grafana dashboard dict for API push.

    Substitutes real datasource UIDs (no __inputs/__requires).
    """
    panels = _build_panels(aps, station_field=station_field)
    dashboard = {
        "uid": "wifi-dethrash",
        **_dashboard_shell(panels, station_field=station_field),
    }

    # Replace datasource placeholders with real UIDs
    raw = json.dumps(dashboard)
    raw = raw.replace("${DS_PROMETHEUS}", prometheus_uid)
    raw = raw.replace("${DS_VICTORIALOGS}", victorialogs_uid)
    return json.loads(raw)
