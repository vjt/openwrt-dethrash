import pytest
from wifi_dethrash.analyzers.weak import WeakAssociationAnalyzer, WeakAssociation
from wifi_dethrash.sources.vm import RSSIReading, NoiseReading


def _r(mac, ap, rssi, ts):
    return RSSIReading(mac=mac, ap=ap, ifname="phy1-ap0", rssi=rssi, timestamp=ts)


def _n(ap, noise, ts, radio="radio1", freq=5745):
    return NoiseReading(ap=ap, radio=radio, frequency=freq, noise_dbm=noise, timestamp=ts)


class TestWeakAssociation:
    def test_detects_low_snr(self):
        """Station with SNR < threshold = weak."""
        rssi = [_r("aa:bb:cc:dd:ee:01", "pingu", -80, 1000)]
        noise = [_n("pingu", -90, 1000)]

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)

        assert len(results) == 1
        r = results[0]
        assert r.mac == "aa:bb:cc:dd:ee:01"
        assert r.ap == "pingu"
        assert r.avg_snr == 10  # -80 - (-90) = 10

    def test_good_snr_not_flagged(self):
        """Station with SNR > threshold = fine."""
        rssi = [_r("aa:bb:cc:dd:ee:01", "pingu", -55, 1000)]
        noise = [_n("pingu", -92, 1000)]

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)
        assert results == []

    def test_averages_over_time(self):
        """SNR is averaged over multiple samples."""
        rssi = [
            _r("aa:bb:cc:dd:ee:01", "pingu", -78, 1000),
            _r("aa:bb:cc:dd:ee:01", "pingu", -82, 1030),
        ]
        noise = [
            _n("pingu", -90, 1000),
            _n("pingu", -90, 1030),
        ]

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)

        assert len(results) == 1
        assert results[0].avg_snr == 10  # avg(-78, -82) - (-90) = -80 - (-90) = 10
