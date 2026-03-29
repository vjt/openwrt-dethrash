from collections import defaultdict
from io import StringIO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.recommender import TxPowerPlan, UCICommand
from wifi_dethrash.sources.vm import NoiseReading, TxPowerReading

MIN_OVERLAP_SAMPLES = 5


def render_report(
    *,
    thrash: list[ThrashSequence],
    overlap: list[OverlapResult],
    weak: list[WeakAssociation],
    plan: TxPowerPlan | None = None,
    usteer_commands: list[UCICommand] | None = None,
    txpower: list[TxPowerReading] | None = None,
    noise: list[NoiseReading] | None = None,
) -> str:
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100)

    console.print(Panel("[bold]wifi-dethrash report[/bold]", expand=False,
                        border_style="blue"))
    console.print()

    # Network state
    if txpower or noise:
        _render_network_state(console, txpower or [], noise or [])

    # Thrashing
    _render_thrashing(console, thrash)

    # Overlap
    _render_overlap(console, overlap)

    # Weak associations
    _render_weak(console, weak)

    # Recommendations
    _render_recommendations(console, plan, usteer_commands)

    return buf.getvalue()


def _render_network_state(
    console: Console,
    txpower: list[TxPowerReading],
    noise: list[NoiseReading],
) -> None:
    noise_by_ap_radio: dict[tuple[str, str], int] = {}
    for n in noise:
        noise_by_ap_radio[(n.ap, n.radio)] = n.noise_dbm

    rows: list[tuple[str, str, int, int, str, int | None]] = []
    for t in txpower:
        noise_val = noise_by_ap_radio.get((t.ap, t.radio))
        band = "5 GHz" if t.frequency_mhz > 4000 else "2.4 GHz"
        rows.append((t.ap, t.radio, t.channel, t.txpower_dbm, band, noise_val))

    rows.sort(key=lambda r: (r[4], r[0], r[1]))

    for band_name in ("2.4 GHz", "5 GHz"):
        band_rows = [r for r in rows if r[4] == band_name]
        if not band_rows:
            continue

        table = Table(title=f"Network State \u2014 {band_name}",
                      title_style="bold cyan", border_style="dim")
        table.add_column("AP", style="bold")
        table.add_column("Radio")
        table.add_column("Ch", justify="right")
        table.add_column("TxPwr", justify="right")
        table.add_column("Noise", justify="right")

        for ap, radio, channel, txp, _, noise_val in band_rows:
            noise_str = f"{noise_val} dB" if noise_val is not None else "?"
            table.add_row(ap, radio, str(channel), f"{txp} dB", noise_str)

        console.print(table)
        console.print()


def _render_thrashing(console: Console, thrash: list[ThrashSequence]) -> None:
    table = Table(title="Thrashing Summary", title_style="bold yellow",
                  border_style="dim")
    table.add_column("MAC", style="dim")
    table.add_column("AP Pair", style="bold")
    table.add_column("Connects", justify="right", style="red")
    table.add_column("Episodes", justify="right")
    table.add_column("Period")

    if not thrash:
        console.print("[green]No thrashing detected.[/green]")
        console.print()
        return

    agg = _aggregate_thrashing(thrash)
    for mac, pair, total, episodes, first, last in agg:
        table.add_row(
            mac,
            f"{pair[0]} \u2194 {pair[1]}",
            str(total),
            str(episodes),
            f"{first[:10]} \u2192 {last[:10]}",
        )

    console.print(table)
    console.print()


def _render_overlap(console: Console, overlap: list[OverlapResult]) -> None:
    significant = [o for o in overlap if o.overlap_count >= MIN_OVERLAP_SAMPLES]

    table = Table(title="RSSI Overlap (significant)",
                  title_style="bold magenta", border_style="dim")
    table.add_column("MAC", style="dim")
    table.add_column("AP Pair", style="bold")
    table.add_column("Avg Diff", justify="right")
    table.add_column("Samples", justify="right")
    table.add_column("RSSI", justify="right")

    if not significant:
        console.print("[green]No significant overlap.[/green]")
        console.print()
        return

    for o in significant:
        pct = round(o.overlap_count / o.total_samples * 100) if o.total_samples else 0
        table.add_row(
            o.mac,
            f"{o.ap_pair[0]} \u2194 {o.ap_pair[1]}",
            f"{o.rssi_diff} dB",
            f"{o.overlap_count}/{o.total_samples} ({pct}%)",
            f"{o.avg_rssi_a}/{o.avg_rssi_b} dBm",
        )

    console.print(table)
    omitted = len(overlap) - len(significant)
    if omitted:
        console.print(f"  [dim]({omitted} minor overlaps with <{MIN_OVERLAP_SAMPLES} samples omitted)[/dim]")
    console.print()


def _render_weak(console: Console, weak: list[WeakAssociation]) -> None:
    if not weak:
        console.print("[green]No weak associations.[/green]")
        console.print()
        return

    table = Table(title="Weak Associations", title_style="bold red",
                  border_style="dim")
    table.add_column("MAC", style="dim")
    table.add_column("AP", style="bold")
    table.add_column("Avg SNR", justify="right")
    table.add_column("Samples", justify="right")

    for w in weak:
        snr_style = "red bold" if w.avg_snr < 10 else "yellow"
        table.add_row(
            w.mac, w.ap,
            Text(f"{w.avg_snr} dB", style=snr_style),
            str(w.sample_count),
        )

    console.print(table)
    console.print()


def _render_recommendations(
    console: Console,
    plan: TxPowerPlan | None,
    usteer_commands: list[UCICommand] | None,
) -> None:
    has_recs = False

    if plan and plan.changes:
        has_recs = True

        # Txpower plan table
        table = Table(title="Txpower Plan", title_style="bold green",
                      border_style="dim")
        table.add_column("AP", style="bold")
        table.add_column("Radio")
        table.add_column("Current", justify="right")
        table.add_column("", justify="center")
        table.add_column("Proposed", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("Command", style="dim")

        for c in plan.changes:
            delta = c.proposed - c.current
            sign = "+" if delta > 0 else ""
            delta_style = "green" if delta > 0 else "red"
            table.add_row(
                c.ap, c.radio,
                f"{c.current} dB",
                "\u2192",
                f"{c.proposed} dB",
                Text(f"{sign}{delta}", style=delta_style),
                f"ssh root@{c.ap} uci set wireless.{c.radio}.txpower={c.proposed}",
            )

        console.print(table)
        console.print()

        # Impact analysis table
        impact_table = Table(title="Expected Impact on Thrashing Pairs",
                             title_style="bold", border_style="dim")
        impact_table.add_column("", justify="center", width=2)
        impact_table.add_column("AP Pair", style="bold")
        impact_table.add_column("Before", justify="right")
        impact_table.add_column("", justify="center")
        impact_table.add_column("After", justify="right")
        impact_table.add_column("Connects", justify="right", style="dim")
        impact_table.add_column("Coverage", justify="left")

        for i in plan.pair_impacts:
            if i.rssi_diff_after > i.rssi_diff_before + 0.5:
                mark = Text("\u2191", style="green bold")
            elif i.rssi_diff_after < i.rssi_diff_before - 0.5:
                mark = Text("\u2193", style="red bold")
            else:
                mark = Text("\u2022", style="yellow")

            if i.rssi_diff_after >= i.signal_diff_threshold:
                covered = Text("ok", style="green")
            else:
                covered = Text(
                    f"< signal_diff {i.signal_diff_threshold}",
                    style="yellow",
                )

            impact_table.add_row(
                mark,
                f"{i.ap_pair[0]} \u2194 {i.ap_pair[1]}",
                f"{i.rssi_diff_before} dB",
                "\u2192",
                f"{i.rssi_diff_after} dB",
                str(i.total_thrash_connects),
                covered,
            )

        console.print(impact_table)
        console.print()

    if usteer_commands:
        has_recs = True
        usteer_table = Table(title="usteer Configuration",
                             title_style="bold blue", border_style="dim")
        usteer_table.add_column("Command", style="bold")
        usteer_table.add_column("Reason", style="dim")

        for c in usteer_commands:
            usteer_table.add_row(
                f"ssh root@<ap> {c.command}",
                c.reason,
            )

        console.print(usteer_table)
        console.print()

    if not has_recs:
        console.print("[green bold]No changes recommended. Looking clean.[/green bold]")
        console.print()


def _aggregate_thrashing(
    thrash: list[ThrashSequence],
) -> list[tuple[str, tuple[str, str], int, int, str, str]]:
    """Aggregate thrashing sequences by (mac, ap_pair)."""
    agg: dict[tuple[str, tuple[str, str]], list[ThrashSequence]] = defaultdict(list)
    for s in thrash:
        agg[(s.mac, s.ap_pair)].append(s)

    result = []
    for (mac, pair), episodes in agg.items():
        total = sum(e.count for e in episodes)
        first = min(e.first_time for e in episodes)
        last = max(e.last_time for e in episodes)
        result.append((mac, pair, total, len(episodes), first, last))

    result.sort(key=lambda x: x[2], reverse=True)
    return result
