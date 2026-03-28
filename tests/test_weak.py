import pytest
from wifi_dethrash.analyzers.weak import WeakAssociationAnalyzer, WeakAssociation
from wifi_dethrash.sources.vm import RSSIReading, NoiseReading


def _r(mac, ap, rssi, ts, ifname="phy1-ap0"):
    return RSSIReading(mac=mac, ap=ap, ifname=ifname, rssi=rssi, timestamp=ts)


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
        assert r.ifname == "phy1-ap0"

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

    def test_matches_noise_by_radio(self):
        """RSSI on phy0-ap0 should match noise from radio0, not radio1."""
        rssi = [_r("aa:bb:cc:dd:ee:01", "pingu", -80, 1000, ifname="phy0-ap0")]
        noise = [
            _n("pingu", -85, 1000, radio="radio0", freq=2412),  # 2.4 GHz — correct match
            _n("pingu", -95, 1000, radio="radio1", freq=5745),  # 5 GHz — wrong band
        ]

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)

        assert len(results) == 1
        # Should use radio0 noise (-85), not radio1 noise (-95)
        # SNR = -80 - (-85) = 5
        assert results[0].avg_snr == 5

    def test_normalizes_mac_to_lowercase(self):
        """Uppercase MACs in RSSI data should be normalized."""
        rssi = [_r("AA:BB:CC:DD:EE:01", "pingu", -80, 1000)]
        noise = [_n("pingu", -90, 1000)]

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)

        assert len(results) == 1
        assert results[0].mac == "aa:bb:cc:dd:ee:01"

    def test_no_noise_for_radio_skips(self):
        """If no noise data exists for the station's radio, skip it."""
        rssi = [_r("aa:bb:cc:dd:ee:01", "pingu", -80, 1000, ifname="phy0-ap0")]
        noise = [_n("pingu", -92, 1000, radio="radio1")]  # only 5 GHz noise

        analyzer = WeakAssociationAnalyzer(snr_threshold=15)
        results = analyzer.analyze(rssi, noise)

        # No radio0 noise available, so no SNR can be computed
        assert results == []
