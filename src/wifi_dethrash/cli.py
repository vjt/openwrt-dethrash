import re
import ssl
import sys
from datetime import datetime, timedelta, timezone
from typing import NoReturn

import click
import httpx
import truststore

truststore.inject_into_ssl()

from wifi_dethrash.config import CONFIG_PATH, load_config
from wifi_dethrash.sources.vm import VictoriaMetricsClient
from wifi_dethrash.sources.vl import VictoriaLogsClient
from wifi_dethrash.analyzers.thrashing import ThrashingDetector
from wifi_dethrash.analyzers.overlap import OverlapAnalyzer
from wifi_dethrash.analyzers.weak import WeakAssociationAnalyzer
from wifi_dethrash.recommender import Recommender
from wifi_dethrash.report import render_report


def _parse_window(window: str) -> timedelta:
    """Parse '1h', '24h', '7d' into timedelta."""
    m = re.match(r"^(\d+)([hd])$", window)
    if not m:
        raise click.BadParameter(f"Invalid window format: {window}. Use e.g. 1h, 24h, 7d")
    val, unit = int(m.group(1)), m.group(2)
    if unit == "h":
        return timedelta(hours=val)
    return timedelta(days=val)


def _handle_error(source: str, exc: Exception) -> NoReturn:
    """Print a user-friendly error message and exit."""
    if isinstance(exc, httpx.HTTPStatusError):
        click.echo(
            f"Error: {source} returned HTTP {exc.response.status_code} "
            f"for {exc.request.url}",
            err=True,
        )
        body = exc.response.text[:500]
        if body:
            click.echo(f"  Response: {body}", err=True)
    elif isinstance(exc, httpx.ConnectError):
        click.echo(f"Error: cannot connect to {source}: {exc}", err=True)
    elif isinstance(exc, ssl.SSLError):
        click.echo(f"Error: SSL/TLS error connecting to {source}: {exc}", err=True)
    elif isinstance(exc, httpx.TimeoutException):
        click.echo(f"Error: request to {source} timed out", err=True)
    else:
        click.echo(f"Error: {source}: {exc}", err=True)
    sys.exit(1)


@click.command()
@click.option("--config", "config_path", type=click.Path(), default=None,
              help="Config file path (default: ~/.config/wifi-dethrash/config.toml)")
@click.option("--vm-url", default=None, help="VictoriaMetrics base URL")
@click.option("--vl-url", default=None, help="VictoriaLogs base URL (required for analysis)")
@click.option("--grafana-url", default=None, help="Grafana base URL")
@click.option("--grafana-api-key", default=None, help="Grafana service account token")
@click.option("--mesh-ssids", multiple=True, help="Mesh SSIDs to filter APs (e.g. Mercury Saturn)")
@click.option("--window", default="24h", help="Time window to analyze (e.g. 1h, 24h, 7d)")
@click.option("--host-label", default="instance", help="Metric label containing AP hostname")
@click.option("--mac", multiple=True, help="Filter to specific MAC address(es)")
@click.option("--generate-dashboard", type=click.Path(), default=None,
              help="Write Grafana dashboard JSON to file and exit")
@click.option("--push-dashboard", is_flag=True, default=False,
              help="Push dashboard to Grafana via API and exit")
@click.option("--annotate", default=None,
              help="Add annotation to Grafana dashboard and exit")
@click.option("--overlap-threshold", default=6, help="Max RSSI diff (dB) to count as overlap")
@click.option("--snr-threshold", default=15, help="Min SNR (dB) for a healthy association")
@click.option("--rssi-floor", default=-75, help="Min RSSI (dBm) below which txpower reduction is skipped")
def main(config_path, vm_url, vl_url, grafana_url, grafana_api_key,
         mesh_ssids, window, host_label, mac, generate_dashboard,
         push_dashboard, annotate, overlap_threshold, snr_threshold, rssi_floor):
    """WiFi mesh thrashing analyzer for OpenWrt."""
    from pathlib import Path

    cfg = load_config(Path(config_path) if config_path else CONFIG_PATH)

    # CLI options override config file
    effective_vm_url = vm_url or cfg.vm_url
    effective_vl_url = vl_url or cfg.vl_url
    effective_grafana_url = grafana_url or cfg.grafana_url
    effective_grafana_api_key = grafana_api_key or cfg.grafana_api_key
    effective_mesh_ssids = list(mesh_ssids) if mesh_ssids else cfg.mesh_ssids

    if push_dashboard or annotate:
        if not effective_grafana_url:
            raise click.UsageError("--grafana-url required (or set grafana_url in config)")
        if not effective_grafana_api_key:
            raise click.UsageError("--grafana-api-key required (or set grafana_api_key in config)")

    if annotate:
        from wifi_dethrash.grafana import GrafanaClient
        with GrafanaClient(effective_grafana_url, effective_grafana_api_key) as gf:
            ann_id = gf.annotate(annotate)
        click.echo(f"Annotation created (id={ann_id}): {annotate}")
        return

    if not effective_vm_url:
        raise click.UsageError("--vm-url required (or set vm_url in config)")

    delta = _parse_window(window)
    end = datetime.now(timezone.utc)
    start = end - delta

    macs = list(mac) if mac else None

    if not generate_dashboard and not push_dashboard and not effective_vl_url:
        raise click.UsageError("--vl-url is required for analysis mode (or set vl_url in config)")

    try:
        with VictoriaMetricsClient(effective_vm_url, host_label=host_label) as vm:
            click.echo(f"Discovering APs from {effective_vm_url} ...")
            aps = vm.discover_aps()

            click.echo("Fetching txpower data ...")
            try:
                txpower = vm.fetch_txpower()
            except Exception:
                txpower = None

            # SSID-based AP filtering
            if effective_mesh_ssids and txpower:
                mesh_aps = {t.ap for t in txpower if t.ssid in effective_mesh_ssids}
                if mesh_aps:
                    filtered = [a for a in aps if a.hostname in mesh_aps]
                    excluded = len(aps) - len(filtered)
                    if excluded:
                        click.echo(f"Filtered to {len(filtered)} mesh APs "
                                   f"({excluded} non-mesh excluded)")
                    aps = filtered
                    txpower = [t for t in txpower if t.ap in mesh_aps]

            click.echo(f"Found {len(aps)} APs: {', '.join(a.hostname for a in aps)}")

            if generate_dashboard:
                from wifi_dethrash.dashboard import generate_dashboard as gen_dash
                dashboard_json = gen_dash(aps, ap_locations=cfg.aps)
                with open(generate_dashboard, "w") as f:
                    f.write(dashboard_json)
                click.echo(f"Dashboard written to {generate_dashboard}")
                return

            if push_dashboard:
                from wifi_dethrash.dashboard import generate_dashboard_api
                from wifi_dethrash.grafana import GrafanaClient

                dash_mac_names: dict[str, str] = {}
                if effective_vl_url:
                    click.echo("Resolving MAC addresses ...")
                    with VictoriaLogsClient(effective_vl_url) as vl:
                        dash_mac_names = vl.fetch_mac_names()
                    click.echo(f"Resolved {len(dash_mac_names)} MAC names")

                with GrafanaClient(effective_grafana_url, effective_grafana_api_key) as gf:
                    datasources = gf.discover_datasources()
                    prom_uid = gf.find_datasource_uid(datasources, "prometheus")
                    vl_uid = gf.find_datasource_uid(
                        datasources, "victoriametrics-logs-datasource")
                    dashboard = generate_dashboard_api(
                        aps, prom_uid, vl_uid,
                        ap_locations=cfg.aps, mac_names=dash_mac_names)
                    url = gf.push_dashboard(dashboard)
                click.echo(f"Dashboard pushed: {effective_grafana_url}{url}")
                return

            click.echo(f"Fetching RSSI data ({window} window) ...")
            rssi = vm.fetch_rssi(start, end, macs=macs)

            click.echo("Fetching noise floor data ...")
            noise = vm.fetch_noise(start, end)

    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException,
            ssl.SSLError) as exc:
        _handle_error(f"VictoriaMetrics ({effective_vm_url})", exc)

    try:
        with VictoriaLogsClient(effective_vl_url) as vl:
            click.echo("Fetching hostapd events ...")
            events = vl.fetch_events(start, end, macs=macs)

            click.echo("Resolving MAC addresses ...")
            mac_names = vl.fetch_mac_names()
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException,
            ssl.SSLError) as exc:
        _handle_error(f"VictoriaLogs ({effective_vl_url})", exc)

    click.echo(f"Got {len(rssi)} RSSI readings, {len(events)} hostapd events, {len(mac_names)} MAC names.")

    click.echo("Analyzing ...")
    thrash = ThrashingDetector().detect(events)
    overlap = OverlapAnalyzer(overlap_threshold).analyze(rssi)
    weak = WeakAssociationAnalyzer(snr_threshold).analyze(rssi, noise)

    rec = Recommender(overlap_threshold=overlap_threshold, rssi_floor=rssi_floor)
    txpower_plan = rec.plan(thrash, overlap, txpower=txpower)
    usteer_commands = rec.usteer_commands(txpower_plan.signal_diff_threshold)

    click.echo("")
    click.echo(render_report(
        thrash=thrash, overlap=overlap, weak=weak,
        plan=txpower_plan, usteer_commands=usteer_commands,
        txpower=txpower, noise=noise,
        mac_names=mac_names,
    ))
