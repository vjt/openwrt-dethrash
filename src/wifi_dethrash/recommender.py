from dataclasses import dataclass

from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation


@dataclass
class UCICommand:
    ap: str
    ssh_prefix: str
    command: str
    reason: str

    def __str__(self) -> str:
        return f"{self.ssh_prefix} {self.command}"


class Recommender:
    def __init__(self, target_power: int = 14, min_snr_value: int = 15):
        self._target_power = target_power
        self._min_snr_value = min_snr_value

    def txpower_commands(
        self,
        thrash: list[ThrashSequence],
        overlap: list[OverlapResult],
    ) -> list[UCICommand]:
        """Generate txpower reduction commands for thrashing AP pairs."""
        if not thrash:
            return []

        # Find AP pairs that both thrash AND have RSSI overlap
        overlap_pairs = {r.ap_pair for r in overlap}
        thrash_pairs = {s.ap_pair for s in thrash}
        confirmed = overlap_pairs & thrash_pairs

        commands = []
        affected_aps = set()
        for pair in confirmed:
            for ap in pair:
                if ap not in affected_aps:
                    affected_aps.add(ap)
                    other = pair[1] if pair[0] == ap else pair[0]
                    overlap_r = next(
                        (r for r in overlap if r.ap_pair == pair), None
                    )
                    diff = overlap_r.rssi_diff if overlap_r else "?"
                    commands.append(UCICommand(
                        ap=ap,
                        ssh_prefix=f"ssh root@{ap}",
                        command=f"uci set wireless.radio1.txpower={self._target_power}",
                        reason=f"Reduce overlap with {other} (avg {diff} dB difference)",
                    ))

        return commands

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
