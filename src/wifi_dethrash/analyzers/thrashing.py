from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from wifi_dethrash.sources.vl import HostapdEvent


@dataclass(frozen=True)
class ThrashSequence:
    mac: str
    ap_pair: tuple[str, str]
    count: int
    first_time: str
    last_time: str


class ThrashingDetector:
    def __init__(self, max_gap: int = 60, min_count: int = 3):
        self._max_gap = max_gap
        self._min_count = min_count

    def detect(self, events: list[HostapdEvent]) -> list[ThrashSequence]:
        """Detect thrashing sequences from sorted hostapd events."""
        # Group connect events by MAC
        connects_by_mac: dict[str, list[HostapdEvent]] = defaultdict(list)
        for e in events:
            if e.event == "connected":
                connects_by_mac[e.mac].append(e)

        sequences = []
        for mac, connects in connects_by_mac.items():
            sequences.extend(self._detect_for_mac(mac, connects))

        sequences.sort(key=lambda s: s.count, reverse=True)
        return sequences

    def _detect_for_mac(
        self, mac: str, connects: list[HostapdEvent]
    ) -> list[ThrashSequence]:
        """Find thrash sequences for a single MAC."""
        if len(connects) < self._min_count:
            return []

        sequences = []
        run_start = 0

        for i in range(1, len(connects)):
            prev_t = self._parse_time(connects[i - 1].time)
            curr_t = self._parse_time(connects[i].time)
            gap = (curr_t - prev_t).total_seconds()

            if gap > self._max_gap:
                # Gap too large — flush current run
                seq = self._check_run(mac, connects[run_start:i])
                if seq:
                    sequences.append(seq)
                run_start = i

        # Flush final run
        seq = self._check_run(mac, connects[run_start:])
        if seq:
            sequences.append(seq)

        return sequences

    def _check_run(
        self, mac: str, connects: list[HostapdEvent]
    ) -> ThrashSequence | None:
        """Check if a run of connects is a pair thrash."""
        if len(connects) < self._min_count:
            return None

        aps = {c.ap for c in connects}
        if len(aps) != 2:
            return None

        ap_pair = tuple(sorted(aps))
        return ThrashSequence(
            mac=mac,
            ap_pair=ap_pair,
            count=len(connects),
            first_time=connects[0].time,
            last_time=connects[-1].time,
        )

    @staticmethod
    def _parse_time(iso: str) -> datetime:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
