from collections import defaultdict

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
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  wifi-dethrash report")
    lines.append("=" * 60)
    lines.append("")

    # Network state table
    if txpower or noise:
        lines.append("--- Network state ---")
        lines.extend(_render_network_state(txpower or [], noise or []))
        lines.append("")

    # Thrashing — aggregated by (mac, ap_pair)
    lines.append("--- Thrashing summary ---")
    if thrash:
        agg = _aggregate_thrashing(thrash)
        for mac, pair, total, episodes, first, last in agg:
            first_short = first[:10]
            last_short = last[:10]
            lines.append(
                f"  {mac}  {pair[0]} <-> {pair[1]}  "
                f"{total} connects in {episodes} episodes  ({first_short} to {last_short})"
            )
    else:
        lines.append("  No thrashing detected.")
    lines.append("")

    # Overlap — filtered to significant results
    lines.append("--- RSSI overlap (significant) ---")
    significant = [o for o in overlap if o.overlap_count >= MIN_OVERLAP_SAMPLES]
    if significant:
        for o in significant:
            pct = round(o.overlap_count / o.total_samples * 100) if o.total_samples else 0
            lines.append(
                f"  {o.mac}  {o.ap_pair[0]} <-> {o.ap_pair[1]}  "
                f"avg diff {o.rssi_diff} dB  "
                f"({o.overlap_count}/{o.total_samples} samples = {pct}%)  "
                f"[{o.ap_pair[0]}: {o.avg_rssi_a} dBm, {o.ap_pair[1]}: {o.avg_rssi_b} dBm]"
            )
    else:
        lines.append("  No significant overlap.")
    if len(overlap) > len(significant):
        lines.append(f"  ({len(overlap) - len(significant)} minor overlaps with <{MIN_OVERLAP_SAMPLES} samples omitted)")
    lines.append("")

    # Weak associations
    lines.append("--- Weak associations ---")
    if weak:
        for w in weak:
            lines.append(
                f"  {w.mac} on {w.ap}  avg SNR {w.avg_snr} dB  "
                f"({w.sample_count} samples)"
            )
    else:
        lines.append("  No weak associations.")
    lines.append("")

    # Recommendations
    lines.append("--- Recommendations ---")
    has_recs = False

    if plan and plan.changes:
        has_recs = True
        lines.append("  Txpower plan:")
        for c in plan.changes:
            delta = c.proposed - c.current
            sign = "+" if delta > 0 else ""
            lines.append(
                f"    {c.ap:<12s} {c.radio}: {c.current} -> {c.proposed} dBm ({sign}{delta})"
            )
            lines.append(
                f"      ssh root@{c.ap} uci set wireless.{c.radio}.txpower={c.proposed}"
            )
        lines.append("")

        lines.append("  Expected impact on thrashing pairs:")
        for i in plan.pair_impacts:
            if i.rssi_diff_after > i.rssi_diff_before + 0.5:
                mark = "+"
            elif i.rssi_diff_after < i.rssi_diff_before - 0.5:
                mark = "-"
            else:
                mark = "~"
            covered = "ok" if i.rssi_diff_after >= i.signal_diff_threshold else \
                      f"< signal_diff {i.signal_diff_threshold}"
            lines.append(
                f"    {mark} {i.ap_pair[0]} <-> {i.ap_pair[1]}:  "
                f"diff {i.rssi_diff_before} -> {i.rssi_diff_after} dB  "
                f"({i.total_thrash_connects} connects)  [{covered}]"
            )
        lines.append("")

    if usteer_commands:
        has_recs = True
        lines.append("  usteer:")
        for c in usteer_commands:
            lines.append(f"    {c}")
            lines.append(f"      # {c.reason}")
        lines.append("")

    if not has_recs:
        lines.append("  No changes recommended. Looking clean.")
        lines.append("")

    return "\n".join(lines)


def _render_network_state(
    txpower: list[TxPowerReading],
    noise: list[NoiseReading],
) -> list[str]:
    """Render a per-AP, per-radio network state table."""
    # Build noise lookup: (ap, radio) -> latest noise reading
    noise_by_ap_radio: dict[tuple[str, str], int] = {}
    for n in noise:
        key = (n.ap, n.radio)
        noise_by_ap_radio[key] = n.noise_dbm

    # Build rows from txpower data (one row per AP+radio)
    rows: list[tuple[str, str, int, int, str, int | None]] = []
    for t in txpower:
        noise_val = noise_by_ap_radio.get((t.ap, t.radio))
        band = "5 GHz" if t.frequency_mhz > 4000 else "2.4 GHz"
        rows.append((t.ap, t.radio, t.channel, t.txpower_dbm, band, noise_val))

    rows.sort(key=lambda r: (r[4], r[0], r[1]))

    lines: list[str] = []
    current_band = ""
    for ap, radio, channel, txp, band, noise_val in rows:
        if band != current_band:
            current_band = band
            lines.append(f"  {band}:")
            lines.append(f"    {'AP':<12s} {'Radio':<8s} {'Ch':>4s} {'TxPwr':>6s} {'Noise':>6s}")
            lines.append(f"    {'—'*12} {'—'*8} {'—'*4} {'—'*6} {'—'*6}")
        noise_str = f"{noise_val}" if noise_val is not None else "?"
        lines.append(
            f"    {ap:<12s} {radio:<8s} {channel:>4d} {txp:>4d} dB {noise_str:>4s} dB"
        )
    return lines


def _aggregate_thrashing(
    thrash: list[ThrashSequence],
) -> list[tuple[str, tuple[str, str], int, int, str, str]]:
    """Aggregate thrashing sequences by (mac, ap_pair).

    Returns list of (mac, ap_pair, total_connects, episode_count, first_time, last_time)
    sorted by total_connects descending.
    """
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
