import re
import ssl
import sys
from datetime import datetime, timedelta, timezone

import click
import httpx
import truststore

truststore.inject_into_ssl()

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


def _handle_error(source: str, exc: Exception) -> None:
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
@click.option("--vm-url", required=True, help="VictoriaMetrics base URL")
@click.option("--vl-url", required=True, help="VictoriaLogs base URL")
@click.option("--window", default="24h", help="Time window to analyze (e.g. 1h, 24h, 7d)")
@click.option("--host-label", default="instance", help="Metric label containing AP hostname")
@click.option("--mac", multiple=True, help="Filter to specific MAC address(es)")
@click.option("--generate-dashboard", type=click.Path(), default=None,
              help="Write Grafana dashboard JSON to file and exit")
@click.option("--overlap-threshold", default=6, help="Max RSSI diff (dB) to count as overlap")
@click.option("--snr-threshold", default=15, help="Min SNR (dB) for a healthy association")
def main(vm_url, vl_url, window, host_label, mac, generate_dashboard,
         overlap_threshold, snr_threshold):
    """WiFi mesh thrashing analyzer for OpenWrt."""
    delta = _parse_window(window)
    end = datetime.now(timezone.utc)
    start = end - delta

    macs = list(mac) if mac else None

    try:
        with VictoriaMetricsClient(vm_url, host_label=host_label) as vm:
            if generate_dashboard:
                from wifi_dethrash.dashboard import generate_dashboard as gen_dash
                aps = vm.discover_aps()
                dashboard_json = gen_dash(aps)
                with open(generate_dashboard, "w") as f:
                    f.write(dashboard_json)
                click.echo(f"Dashboard written to {generate_dashboard}")
                return

            click.echo(f"Discovering APs from {vm_url} ...")
            aps = vm.discover_aps()
            click.echo(f"Found {len(aps)} APs: {', '.join(a.hostname for a in aps)}")

            click.echo(f"Fetching RSSI data ({window} window) ...")
            rssi = vm.fetch_rssi(start, end, macs=macs)

            click.echo("Fetching noise floor data ...")
            noise = vm.fetch_noise(start, end)
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException,
            ssl.SSLError) as exc:
        _handle_error(f"VictoriaMetrics ({vm_url})", exc)

    try:
        with VictoriaLogsClient(vl_url) as vl:
            click.echo("Fetching hostapd events ...")
            events = vl.fetch_events(start, end, macs=macs)
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException,
            ssl.SSLError) as exc:
        _handle_error(f"VictoriaLogs ({vl_url})", exc)

    click.echo(f"Got {len(rssi)} RSSI readings, {len(events)} hostapd events.")

    click.echo("Analyzing ...")
    thrash = ThrashingDetector().detect(events)
    overlap = OverlapAnalyzer(overlap_threshold).analyze(rssi)
    weak = WeakAssociationAnalyzer(snr_threshold).analyze(rssi, noise)

    rec = Recommender(min_snr_value=snr_threshold)
    txpower_recs = rec.txpower_recommendations(thrash, overlap)
    usteer_commands = rec.usteer_commands(weak)

    click.echo("")
    click.echo(render_report(
        thrash=thrash, overlap=overlap, weak=weak,
        txpower_recs=txpower_recs, usteer_commands=usteer_commands,
    ))
