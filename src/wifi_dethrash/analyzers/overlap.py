from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from wifi_dethrash.sources.vm import RSSIReading


@dataclass(frozen=True)
class OverlapResult:
    mac: str
    ap_pair: tuple[str, str]       # sorted alphabetically
    rssi_diff: float               # mean abs RSSI difference when overlapping
    overlap_count: int             # number of timestamps with overlap
    total_samples: int             # total timestamps where both APs saw the MAC
    ifname_a: str = ""             # ifname on ap_pair[0]
    ifname_b: str = ""             # ifname on ap_pair[1]


class OverlapAnalyzer:
    def __init__(self, overlap_threshold: int = 6):
        self._threshold = overlap_threshold

    def analyze(self, readings: list[RSSIReading]) -> list[OverlapResult]:
        # Group: (mac, timestamp) -> {ap: rssi}
        by_mac_ts: dict[str, dict[int, dict[str, int]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        # Track ifname per (mac, ap) — last seen wins (they're consistent per radio)
        ifname_by_mac_ap: dict[tuple[str, str], str] = {}
        for r in readings:
            by_mac_ts[r.mac][r.timestamp][r.ap] = r.rssi
            ifname_by_mac_ap[(r.mac, r.ap)] = r.ifname

        results = []
        for mac, ts_map in by_mac_ts.items():
            # For each AP pair this MAC was seen on, check overlap
            pair_stats: dict[tuple[str, str], list[int]] = defaultdict(list)
            for ts, ap_rssi in ts_map.items():
                for a, b in combinations(sorted(ap_rssi.keys()), 2):
                    diff = abs(ap_rssi[a] - ap_rssi[b])
                    pair_stats[(a, b)].append(diff)

            for pair, diffs in pair_stats.items():
                overlaps = [d for d in diffs if d <= self._threshold]
                if overlaps:
                    results.append(OverlapResult(
                        mac=mac,
                        ap_pair=pair,
                        rssi_diff=round(sum(overlaps) / len(overlaps), 1),
                        overlap_count=len(overlaps),
                        total_samples=len(diffs),
                        ifname_a=ifname_by_mac_ap.get((mac, pair[0]), ""),
                        ifname_b=ifname_by_mac_ap.get((mac, pair[1]), ""),
                    ))

        results.sort(key=lambda r: r.overlap_count, reverse=True)
        return results
