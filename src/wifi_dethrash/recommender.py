from collections import defaultdict
from dataclasses import dataclass, field

from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.sources.vm import TxPowerReading
from wifi_dethrash.utils import ifname_to_radio


@dataclass(frozen=True)
class PairAnalysis:
    """Per-pair thrashing + overlap analysis (diagnostic, not actionable)."""
    ap_pair: tuple[str, str]
    radio: str
    total_thrash_connects: int
    total_thrash_episodes: int
    avg_rssi_diff: float
    overlap_pct: int
    avg_rssi_a: float
    avg_rssi_b: float
    current_txpower_a: int | None = None
    current_txpower_b: int | None = None


@dataclass(frozen=True)
class TxPowerChange:
    """A single proposed txpower change for one (AP, radio)."""
    ap: str
    radio: str
    current: int
    proposed: int
    reasons: tuple[str, ...]  # which pairs drove this change


@dataclass(frozen=True)
class PairImpact:
    """Before/after RSSI diff for a thrashing pair under proposed plan."""
    ap_pair: tuple[str, str]
    radio: str
    total_thrash_connects: int
    rssi_diff_before: float
    rssi_diff_after: float
    signal_diff_threshold: int


@dataclass(frozen=True)
class TxPowerPlan:
    """Consolidated txpower plan with compound impact analysis."""
    changes: list[TxPowerChange]
    pair_impacts: list[PairImpact]
    signal_diff_threshold: int


@dataclass
class UCICommand:
    ap: str
    ssh_prefix: str
    command: str
    reason: str

    def __str__(self) -> str:
        return f"{self.ssh_prefix} {self.command}"


class Recommender:
    def __init__(self, overlap_threshold: int = 6, rssi_floor: int = -75):
        self._overlap_threshold = overlap_threshold
        self._rssi_floor = rssi_floor

    def plan(
        self,
        thrash: list[ThrashSequence],
        overlap: list[OverlapResult],
        txpower: list[TxPowerReading] | None = None,
    ) -> TxPowerPlan:
        """Produce a consolidated txpower plan considering compound effects."""
        # Build txpower lookup: (ap, radio) -> TxPowerReading
        txp_lookup: dict[tuple[str, str], TxPowerReading] = {}
        if txpower:
            for t in txpower:
                txp_lookup[(t.ap, t.radio)] = t

        # Analyze each confirmed thrashing pair
        pairs = self._analyze_pairs(thrash, overlap, txp_lookup)

        # Compute signal_diff_threshold from overlap data
        thrash_pairs = {s.ap_pair for s in thrash}
        thrash_diffs = [o.rssi_diff for o in overlap if o.ap_pair in thrash_pairs]
        signal_diff = int(max(thrash_diffs)) + 3 if thrash_diffs else 0

        # Collect per-AP votes from all pairs, weighted by severity
        votes: dict[tuple[str, str], list[tuple[int, int, str]]] = defaultdict(list)
        # votes[(ap, radio)] = list of (weight, delta, reason)

        for p in pairs:
            a, b = p.ap_pair
            txp_a = p.current_txpower_a
            txp_b = p.current_txpower_b
            if txp_a is None or txp_b is None:
                continue

            weight = p.total_thrash_connects
            louder = a if p.avg_rssi_a > p.avg_rssi_b else b
            louder_rssi = max(p.avg_rssi_a, p.avg_rssi_b)
            louder_txp = txp_a if louder == a else txp_b
            quieter = b if louder == a else a
            quieter_txp = txp_b if louder == a else txp_a

            pair_label = f"{a}<->{b}"

            if louder_rssi > self._rssi_floor:
                # Healthy signal: reduce the AP with more headroom
                if louder_txp >= quieter_txp:
                    votes[(louder, p.radio)].append(
                        (weight, -2, f"reduce for {pair_label}"))
                else:
                    votes[(quieter, p.radio)].append(
                        (weight, -2, f"reduce for {pair_label}"))
            else:
                # Weak signal: increase the quieter AP for coverage
                votes[(quieter, p.radio)].append(
                    (weight, +2, f"increase for {pair_label}"))

        # Consolidate: for each (ap, radio), resolve votes into one delta
        changes: list[TxPowerChange] = []
        plan_deltas: dict[tuple[str, str], int] = {}  # (ap, radio) -> net delta

        for (ap, radio), ap_votes in sorted(votes.items()):
            # Weighted vote: sum(weight * sign(delta))
            up_weight = sum(w for w, d, _ in ap_votes if d > 0)
            down_weight = sum(w for w, d, _ in ap_votes if d < 0)

            reading = txp_lookup.get((ap, radio))
            if not reading:
                continue

            if up_weight > down_weight:
                delta = +2
            elif down_weight > up_weight:
                delta = -2
            else:
                continue  # tie — don't change

            proposed = max(reading.txpower_dbm + delta, 5)
            if proposed == reading.txpower_dbm:
                continue

            reasons = tuple(r for _, _, r in ap_votes)
            plan_deltas[(ap, radio)] = delta
            changes.append(TxPowerChange(
                ap=ap,
                radio=radio,
                current=reading.txpower_dbm,
                proposed=proposed,
                reasons=reasons,
            ))

        # Simulate compound impact on all thrashing pairs
        impacts: list[PairImpact] = []
        for p in pairs:
            delta_a = plan_deltas.get((p.ap_pair[0], p.radio), 0)
            delta_b = plan_deltas.get((p.ap_pair[1], p.radio), 0)

            new_rssi_a = p.avg_rssi_a + delta_a
            new_rssi_b = p.avg_rssi_b + delta_b
            diff_before = abs(p.avg_rssi_a - p.avg_rssi_b)
            diff_after = abs(new_rssi_a - new_rssi_b)

            impacts.append(PairImpact(
                ap_pair=p.ap_pair,
                radio=p.radio,
                total_thrash_connects=p.total_thrash_connects,
                rssi_diff_before=round(diff_before, 1),
                rssi_diff_after=round(diff_after, 1),
                signal_diff_threshold=signal_diff,
            ))

        impacts.sort(key=lambda i: i.total_thrash_connects, reverse=True)

        return TxPowerPlan(
            changes=changes,
            pair_impacts=impacts,
            signal_diff_threshold=signal_diff,
        )

    def usteer_commands(
        self,
        signal_diff_threshold: int,
    ) -> list[UCICommand]:
        """Generate complete usteer config: signal_diff for steering,
        explicit disables for everything that kicks clients.

        SNR-based kicking (min_snr, min_connect_snr, roam_trigger, load_kick)
        causes disconnect storms in weak-coverage areas where clients get
        kicked and can't find a better AP. Explicitly zero them out so
        usteer defaults don't bite.
        """
        if signal_diff_threshold <= 0:
            return []

        return [
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command=f"uci set usteer.@usteer[0].signal_diff_threshold={signal_diff_threshold}",
                reason=f"Don't roam unless new AP is {signal_diff_threshold}+ dB stronger",
            ),
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command="uci set usteer.@usteer[0].roam_scan_snr=25",
                reason="Scan for alternatives when SNR < 25 dB (passive, no kick)",
            ),
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command="uci set usteer.@usteer[0].roam_trigger_snr=0",
                reason="Disable forced roaming — kicks by another name",
            ),
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command="uci set usteer.@usteer[0].min_connect_snr=0",
                reason="Disable — was rejecting associations in weak-coverage areas",
            ),
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command="uci set usteer.@usteer[0].min_snr=0",
                reason="Disable — was causing kick/reconnect storms",
            ),
            UCICommand(
                ap="all",
                ssh_prefix="ssh root@<ap>",
                command="uci set usteer.@usteer[0].load_kick_enabled=0",
                reason="Disable — force-disconnects clients under load",
            ),
        ]

    def _analyze_pairs(
        self,
        thrash: list[ThrashSequence],
        overlap: list[OverlapResult],
        txp_lookup: dict[tuple[str, str], TxPowerReading],
    ) -> list[PairAnalysis]:
        """Build per-pair analysis for all confirmed thrashing+overlap pairs."""
        thrash_by_pair: dict[tuple[str, str], list[ThrashSequence]] = defaultdict(list)
        for s in thrash:
            thrash_by_pair[s.ap_pair].append(s)

        overlap_by_pair: dict[tuple[str, str], list[OverlapResult]] = defaultdict(list)
        for o in overlap:
            overlap_by_pair[o.ap_pair].append(o)

        confirmed = set(thrash_by_pair.keys()) & set(overlap_by_pair.keys())
        pairs = []

        for pair in confirmed:
            episodes = thrash_by_pair[pair]
            total_connects = sum(s.count for s in episodes)
            best = max(overlap_by_pair[pair], key=lambda o: o.overlap_count)

            ifname = best.ifname_a or best.ifname_b or ""
            radio = ifname_to_radio(ifname) if ifname else "unknown"
            pct = round(best.overlap_count / best.total_samples * 100) if best.total_samples else 0

            txp_a = txp_lookup.get((pair[0], radio))
            txp_b = txp_lookup.get((pair[1], radio))

            pairs.append(PairAnalysis(
                ap_pair=pair,
                radio=radio,
                total_thrash_connects=total_connects,
                total_thrash_episodes=len(episodes),
                avg_rssi_diff=best.rssi_diff,
                overlap_pct=pct,
                avg_rssi_a=best.avg_rssi_a,
                avg_rssi_b=best.avg_rssi_b,
                current_txpower_a=txp_a.txpower_dbm if txp_a else None,
                current_txpower_b=txp_b.txpower_dbm if txp_b else None,
            ))

        pairs.sort(key=lambda p: p.total_thrash_connects, reverse=True)
        return pairs
