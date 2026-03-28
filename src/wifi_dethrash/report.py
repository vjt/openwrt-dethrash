from collections import defaultdict

from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.recommender import TxPowerRecommendation, UCICommand

MIN_OVERLAP_SAMPLES = 5


def render_report(
    *,
    thrash: list[ThrashSequence],
    overlap: list[OverlapResult],
    weak: list[WeakAssociation],
    txpower_recs: list[TxPowerRecommendation],
    usteer_commands: list[UCICommand],
) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  wifi-dethrash report")
    lines.append("=" * 60)
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
    if txpower_recs:
        for i, r in enumerate(txpower_recs, 1):
            if r.total_thrash_connects >= 50:
                severity = "CRITICAL"
            elif r.total_thrash_connects >= 10:
                severity = "HIGH"
            else:
                severity = "MODERATE"
            lines.append(f"  {i}. {r.ap_pair[0]} <-> {r.ap_pair[1]} ({r.radio}): {severity}")
            lines.append(f"     {r.total_thrash_connects} thrashing connects across {r.total_thrash_episodes} episodes")
            lines.append(
                f"     RSSI overlap: {r.avg_rssi_diff} dB avg diff ({r.overlap_pct}% of samples)"
            )

            # Show RSSI with optional txpower info
            a_info = f"{r.avg_rssi_a} dBm"
            b_info = f"{r.avg_rssi_b} dBm"
            if r.current_txpower_a is not None:
                a_info += f" (txpower {r.current_txpower_a} dBm)"
            if r.current_txpower_b is not None:
                b_info += f" (txpower {r.current_txpower_b} dBm)"
            lines.append(f"     {r.ap_pair[0]}: {a_info} | {r.ap_pair[1]}: {b_info}")

            if r.suggested_txpower is not None:
                louder_txp = r.current_txpower_a if r.louder_ap == r.ap_pair[0] else r.current_txpower_b
                lines.append(
                    f"     -> Reduce {r.louder_ap} {r.radio} txpower: {louder_txp} -> {r.suggested_txpower} dBm"
                )
                lines.append(
                    f"        ssh root@{r.louder_ap} uci set wireless.{r.radio}.txpower={r.suggested_txpower}"
                )
            elif r.skip_reason:
                lines.append(
                    f"     -> No txpower change: {r.skip_reason}"
                )
            else:
                lines.append(
                    f"     -> Consider reducing txpower on {r.louder_ap} ({r.radio})"
                )
            lines.append("")

    if usteer_commands:
        if txpower_recs:
            lines.append("  usteer:")
        for c in usteer_commands:
            lines.append(f"  {c}")
            lines.append(f"    # {c.reason}")

    if not txpower_recs and not usteer_commands:
        lines.append("  No changes recommended. Looking clean.")
    lines.append("")

    return "\n".join(lines)


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
