# Grafana VictoriaLogs Plugin Gotchas

## Query Types

The VL datasource plugin uses `queryType` on each target to select the
query mode. Not documented anywhere obvious — learned by trial and error.

| queryType | Purpose | Example |
|-----------|---------|---------|
| (default) | Log lines | `tags.appname:hostapd AND _msg:AP-STA-CONNECTED` |
| `statsRange` | Time series from `stats` pipe | `... \| stats by (tags.hostname) count() connects` |
| `hits` | Event count histogram | `tags.appname:hostapd AND _msg:AP-STA-` |
| `fieldValue` | Variable dropdown values | Used with `field` + `query` + `limit` |

## Variable Pattern

Station dropdown uses `fieldValue` type with `allValue=".*"` that works
across both datasources:

- **Prometheus panels**: `label_match(..., "station", "$station")` — regex
- **VictoriaLogs panels**: `fields.client_host:~"$station"` — LogsQL regex

The VL plugin's `correctRegExpValueAll()` converts `:~"*"` to `:~".*"`,
so regex with the `$station` variable works despite editor warnings.

## Known Issues

- VL plugin strips custom formatting from variable display — if you need
  both display name and value, use two variables (one for display, one for
  filter value).
- Panel-level `interval` sets the minimum step floor for stats queries.
  The `step` field on individual targets controls `stats_query_range` step.
- Plugin ID is `victoriametrics-logs-datasource` (not `victorialogs-datasource`).
