import click


@click.command()
@click.option("--vm-url", required=True, help="VictoriaMetrics base URL")
@click.option("--vl-url", required=True, help="VictoriaLogs base URL")
@click.option("--window", default="24h", help="Time window to analyze (e.g. 1h, 24h, 7d)")
@click.option("--host-label", default="instance", help="Metric label containing AP hostname")
@click.option("--mac", multiple=True, help="Filter to specific MAC address(es)")
@click.option("--generate-dashboard", type=click.Path(), default=None,
              help="Write Grafana dashboard JSON to file and exit")
def main(vm_url, vl_url, window, host_label, mac, generate_dashboard):
    """WiFi mesh thrashing analyzer for OpenWrt."""
    click.echo(f"vm_url={vm_url} vl_url={vl_url} window={window}")
    click.echo("Not implemented yet.")
