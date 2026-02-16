import pytest
from wifi_dethrash.analyzers.overlap import OverlapAnalyzer, OverlapResult
from wifi_dethrash.sources.vm import RSSIReading


def _r(mac, ap, rssi, ts, ifname="phy1-ap0"):
    return RSSIReading(mac=mac, ap=ap, ifname=ifname, rssi=rssi, timestamp=ts)


class TestOverlapAnalysis:
    def test_detects_overlap(self):
        """Two APs seeing the same MAC within 6 dB = overlap."""
        readings = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000),
            _r("aa:bb:cc:dd:ee:01", "golem", -58, 1000),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)

        assert len(results) == 1
        r = results[0]
        assert r.mac == "aa:bb:cc:dd:ee:01"
        assert set(r.ap_pair) == {"pingu", "golem"}
        assert r.rssi_diff == 3  # |(-55) - (-58)|
        assert r.avg_rssi_a == -58  # golem (alphabetically first)
        assert r.avg_rssi_b == -55  # pingu
        assert r.ifname_a == "phy1-ap0"
        assert r.ifname_b == "phy1-ap0"

    def test_no_overlap_when_difference_large(self):
        """20 dB difference = no overlap."""
        readings = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000),
            _r("aa:bb:cc:dd:ee:01", "golem", -75, 1000),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)
        assert results == []

    def test_overlap_across_time(self):
        """Overlap is computed per-timestamp, then aggregated."""
        readings = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000),
            _r("aa:bb:cc:dd:ee:01", "golem", -58, 1000),
            _r("aa:bb:cc:dd:ee:01", "pingu", -56, 1030),
            _r("aa:bb:cc:dd:ee:01", "golem", -59, 1030),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)

        assert len(results) == 1
        assert results[0].overlap_count == 2  # overlap at both timestamps

    def test_multiple_macs(self):
        readings = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000),
            _r("aa:bb:cc:dd:ee:01", "golem", -57, 1000),
            _r("aa:bb:cc:dd:ee:02", "albert", -50, 1000),
            _r("aa:bb:cc:dd:ee:02", "gordon", -52, 1000),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)
        assert len(results) == 2

    def test_normalizes_mac_to_lowercase(self):
        """MACs from VM metrics (uppercase) should be normalized to lowercase."""
        readings = [
            _r("AA:BB:CC:DD:EE:01", "pingu", -55, 1000),
            _r("AA:BB:CC:DD:EE:01", "golem", -58, 1000),
        ]
        analyzer = OverlapAnalyzer(overlap_threshold=6)
        results = analyzer.analyze(readings)

        assert len(results) == 1
        assert results[0].mac == "aa:bb:cc:dd:ee:01"
