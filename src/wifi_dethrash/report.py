from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.recommender import UCICommand


def render_report(
    *,
    thrash: list[ThrashSequence],
    overlap: list[OverlapResult],
    weak: list[WeakAssociation],
    commands: list[UCICommand],
) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  wifi-dethrash report")
    lines.append("=" * 60)
    lines.append("")

    # Thrashing
    lines.append("--- Thrashing sequences ---")
    if thrash:
        for s in thrash:
            lines.append(
                f"  {s.mac}  {s.ap_pair[0]} <-> {s.ap_pair[1]}  "
                f"{s.count} connects  ({s.first_time} to {s.last_time})"
            )
    else:
        lines.append("  No thrashing detected.")
    lines.append("")

    # Overlap
    lines.append("--- RSSI overlap ---")
    if overlap:
        for o in overlap:
            pct = round(o.overlap_count / o.total_samples * 100) if o.total_samples else 0
            lines.append(
                f"  {o.mac}  {o.ap_pair[0]} <-> {o.ap_pair[1]}  "
                f"avg diff {o.rssi_diff} dB  "
                f"({o.overlap_count}/{o.total_samples} samples = {pct}%)"
            )
    else:
        lines.append("  No significant overlap.")
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

    # Commands
    lines.append("--- Recommended commands ---")
    if commands:
        for c in commands:
            lines.append(f"  {c}")
            lines.append(f"    # {c.reason}")
    else:
        lines.append("  No changes recommended. Looking clean.")
    lines.append("")

    return "\n".join(lines)
