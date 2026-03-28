from collections import defaultdict
from dataclasses import dataclass

from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.sources.vm import TxPowerReading
from wifi_dethrash.utils import ifname_to_radio


@dataclass(frozen=True)
class TxPowerRecommendation:
    ap_pair: tuple[str, str]
    radio: str
    total_thrash_connects: int
    total_thrash_episodes: int
    avg_rssi_diff: float
    overlap_pct: int
    avg_rssi_a: float              # avg RSSI for ap_pair[0]
    avg_rssi_b: float              # avg RSSI for ap_pair[1]
    louder_ap: str                 # AP to reduce (highest headroom or strongest signal)
    current_txpower_a: int | None = None
    current_txpower_b: int | None = None
    suggested_txpower: int | None = None  # for louder_ap
    skip_reason: str | None = None        # why suggestion was skipped


@dataclass
class UCICommand:
    ap: str
    ssh_prefix: str
    command: str
    reason: str

    def __str__(self) -> str:
        return f"{self.ssh_prefix} {self.command}"


class Recommender:
    def __init__(self, min_snr_value: int = 15, overlap_threshold: int = 6,
                 rssi_floor: int = -75):
        self._min_snr_value = min_snr_value
        self._overlap_threshold = overlap_threshold
        self._rssi_floor = rssi_floor

    def txpower_recommendations(
        self,
        thrash: list[ThrashSequence],
        overlap: list[OverlapResult],
        txpower: list[TxPowerReading] | None = None,
    ) -> list[TxPowerRecommendation]:
        """Analyze thrashing+overlap to produce ranked power recommendations."""
        if not thrash:
            return []

        # Build txpower lookup: (ap, radio) -> TxPowerReading
        txp_lookup: dict[tuple[str, str], TxPowerReading] = {}
        if txpower:
            for t in txpower:
                txp_lookup[(t.ap, t.radio)] = t

        # Aggregate thrashing by ap_pair
        thrash_by_pair: dict[tuple[str, str], list[ThrashSequence]] = defaultdict(list)
        for s in thrash:
            thrash_by_pair[s.ap_pair].append(s)

        # Index overlap by ap_pair
        overlap_by_pair: dict[tuple[str, str], list[OverlapResult]] = defaultdict(list)
        for o in overlap:
            overlap_by_pair[o.ap_pair].append(o)

        # Only recommend for pairs with both thrashing AND overlap
        confirmed = set(thrash_by_pair.keys()) & set(overlap_by_pair.keys())

        recs = []
        for pair in confirmed:
            episodes = thrash_by_pair[pair]
            total_connects = sum(s.count for s in episodes)

            overlaps = overlap_by_pair[pair]
            # Use the overlap entry with most samples for this pair
            best = max(overlaps, key=lambda o: o.overlap_count)

            ifname = best.ifname_a or best.ifname_b or ""
            radio = ifname_to_radio(ifname) if ifname else "unknown"

            pct = round(best.overlap_count / best.total_samples * 100) if best.total_samples else 0

            louder = pair[0] if best.avg_rssi_a > best.avg_rssi_b else pair[1]

            # Look up current txpower for each AP on this radio
            txp_a_reading = txp_lookup.get((pair[0], radio))
            txp_b_reading = txp_lookup.get((pair[1], radio))
            current_txpower_a = txp_a_reading.txpower_dbm if txp_a_reading else None
            current_txpower_b = txp_b_reading.txpower_dbm if txp_b_reading else None

            # Compute suggested txpower for the AP with more headroom
            suggested = None
            louder_rssi = best.avg_rssi_a if louder == pair[0] else best.avg_rssi_b

            # Pick which AP to reduce: prefer the one with higher txpower
            # (more headroom). Fall back to louder signal if txpower is equal.
            reduce_ap = louder
            reduce_txp = current_txpower_a if louder == pair[0] else current_txpower_b
            other_txp = current_txpower_b if louder == pair[0] else current_txpower_a

            if reduce_txp is not None and other_txp is not None:
                if other_txp > reduce_txp:
                    # Other AP has more headroom — reduce that one instead
                    reduce_ap = pair[1] if louder == pair[0] else pair[0]
                    reduce_txp = other_txp
                    louder_rssi = best.avg_rssi_b if louder == pair[0] else best.avg_rssi_a

            louder = reduce_ap

            skip_reason = None
            if reduce_txp is not None and louder_rssi > self._rssi_floor:
                # Conservative: 2 dBm step. Iterate rather than overshoot.
                suggested = max(reduce_txp - 2, 5)
            elif reduce_txp is not None:
                skip_reason = (
                    f"RSSI already weak ({louder_rssi} dBm <= {self._rssi_floor} dBm floor)"
                )

            recs.append(TxPowerRecommendation(
                ap_pair=pair,
                radio=radio,
                total_thrash_connects=total_connects,
                total_thrash_episodes=len(episodes),
                avg_rssi_diff=best.rssi_diff,
                overlap_pct=pct,
                avg_rssi_a=best.avg_rssi_a,
                avg_rssi_b=best.avg_rssi_b,
                louder_ap=louder,
                current_txpower_a=current_txpower_a,
                current_txpower_b=current_txpower_b,
                suggested_txpower=suggested,
                skip_reason=skip_reason,
            ))

        recs.sort(key=lambda r: r.total_thrash_connects, reverse=True)
        return recs

    def usteer_commands(
        self,
        weak: list[WeakAssociation],
    ) -> list[UCICommand]:
        """Generate usteer threshold commands for weak associations."""
        if not weak:
            return []

        commands = [
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command=f"uci set usteer.@usteer[0].min_connect_snr={self._min_snr_value}",
                reason=f"Reject new associations below {self._min_snr_value} dB SNR",
            ),
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command=f"uci set usteer.@usteer[0].min_snr={self._min_snr_value - 3}",
                reason=f"Kick existing clients below {self._min_snr_value - 3} dB SNR",
            ),
        ]
        return commands
