import bisect
from collections import defaultdict
from dataclasses import dataclass

from wifi_dethrash.sources.vm import RSSIReading, NoiseReading
from wifi_dethrash.utils import ifname_to_radio


@dataclass(frozen=True)
class WeakAssociation:
    mac: str
    ap: str
    avg_snr: float
    sample_count: int
    ifname: str = ""


class WeakAssociationAnalyzer:
    def __init__(self, snr_threshold: int = 15):
        self._threshold = snr_threshold

    def analyze(
        self,
        rssi: list[RSSIReading],
        noise: list[NoiseReading],
    ) -> list[WeakAssociation]:
        # Build noise lookup keyed by (ap, radio) for correct band matching
        noise_by_ap_radio: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
        for n in noise:
            noise_by_ap_radio[(n.ap, n.radio)].append((n.timestamp, n.noise_dbm))

        for key in noise_by_ap_radio:
            noise_by_ap_radio[key].sort()

        # Compute SNR for each RSSI reading, joining on (ap, radio)
        snr_by_mac_ap: dict[tuple[str, str], list[float]] = defaultdict(list)
        ifname_by_mac_ap: dict[tuple[str, str], str] = {}
        for r in rssi:
            radio = ifname_to_radio(r.ifname)
            noise_val = self._nearest_noise(
                noise_by_ap_radio.get((r.ap, radio), []), r.timestamp
            )
            if noise_val is not None:
                snr = r.rssi - noise_val
                snr_by_mac_ap[(r.mac, r.ap)].append(snr)
                ifname_by_mac_ap[(r.mac, r.ap)] = r.ifname

        results = []
        for (mac, ap), snrs in snr_by_mac_ap.items():
            avg = sum(snrs) / len(snrs)
            if avg < self._threshold:
                results.append(WeakAssociation(
                    mac=mac,
                    ap=ap,
                    avg_snr=round(avg),
                    sample_count=len(snrs),
                    ifname=ifname_by_mac_ap.get((mac, ap), ""),
                ))

        results.sort(key=lambda w: w.avg_snr)
        return results

    @staticmethod
    def _nearest_noise(
        noise_series: list[tuple[int, int]], ts: int
    ) -> int | None:
        """Find the noise reading closest to the given timestamp."""
        if not noise_series:
            return None
        idx = bisect.bisect_left(noise_series, (ts,))
        candidates = []
        if idx < len(noise_series):
            candidates.append(noise_series[idx])
        if idx > 0:
            candidates.append(noise_series[idx - 1])
        return min(candidates, key=lambda x: abs(x[0] - ts))[1]
