import pytest
from wifi_dethrash.recommender import Recommender, TxPowerRecommendation, UCICommand
from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.sources.vm import TxPowerReading


class TestTxPowerRecommendation:
    def test_recommends_for_thrashing_pair_with_overlap(self):
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=50,
            first_time="2026-02-16T08:00:00Z",
            last_time="2026-02-16T08:10:00Z",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            rssi_diff=3.0,
            overlap_count=100,
            total_samples=120,
            avg_rssi_a=-52,
            avg_rssi_b=-55,
            ifname_a="phy1-ap0",
            ifname_b="phy1-ap0",
        )]

        rec = Recommender()
        recs = rec.txpower_recommendations(thrash, overlap)

        assert len(recs) == 1
        r = recs[0]
        assert r.ap_pair == ("golem", "pingu")
        assert r.radio == "radio1"
        assert r.total_thrash_connects == 50
        assert r.total_thrash_episodes == 1
        assert r.avg_rssi_diff == 3.0
        # golem is louder (-52 > -55)
        assert r.louder_ap == "golem"

    def test_identifies_louder_ap(self):
        """Should recommend reducing power on the AP with stronger signal."""
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("albert", "pingu"),
            count=20,
            first_time="2026-02-16T08:00:00Z",
            last_time="2026-02-16T08:05:00Z",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("albert", "pingu"),
            rssi_diff=4.0,
            overlap_count=50,
            total_samples=60,
            avg_rssi_a=-60,
            avg_rssi_b=-54,  # pingu is louder
            ifname_a="phy1-ap0",
            ifname_b="phy1-ap0",
        )]

        rec = Recommender()
        recs = rec.txpower_recommendations(thrash, overlap)

        assert len(recs) == 1
        assert recs[0].louder_ap == "pingu"

    def test_aggregates_thrash_episodes(self):
        """Multiple episodes for same pair should be aggregated."""
        thrash = [
            ThrashSequence(mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
                           count=20, first_time="2026-02-16T08:00:00Z",
                           last_time="2026-02-16T08:05:00Z"),
            ThrashSequence(mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
                           count=30, first_time="2026-02-16T09:00:00Z",
                           last_time="2026-02-16T09:05:00Z"),
        ]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            rssi_diff=3.0,
            overlap_count=100,
            total_samples=120,
            avg_rssi_a=-52,
            avg_rssi_b=-55,
            ifname_a="phy1-ap0",
            ifname_b="phy1-ap0",
        )]

        rec = Recommender()
        recs = rec.txpower_recommendations(thrash, overlap)

        assert len(recs) == 1
        assert recs[0].total_thrash_connects == 50
        assert recs[0].total_thrash_episodes == 2

    def test_uses_correct_radio_for_24ghz(self):
        """Thrashing on 2.4 GHz should show radio0."""
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=20,
            first_time="2026-02-16T08:00:00Z",
            last_time="2026-02-16T08:05:00Z",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            rssi_diff=4.0,
            overlap_count=50,
            total_samples=60,
            avg_rssi_a=-52,
            avg_rssi_b=-55,
            ifname_a="phy0-ap0",
            ifname_b="phy0-ap0",
        )]

        rec = Recommender()
        recs = rec.txpower_recommendations(thrash, overlap)

        assert len(recs) == 1
        assert recs[0].radio == "radio0"

    def test_no_thrashing_no_recommendations(self):
        rec = Recommender()
        recs = rec.txpower_recommendations([], [])
        assert recs == []

    def test_sorted_by_severity(self):
        """Most thrashing pair should be first."""
        thrash = [
            ThrashSequence(mac="aa:bb:cc:dd:ee:01", ap_pair=("albert", "golem"),
                           count=5, first_time="T1", last_time="T2"),
            ThrashSequence(mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
                           count=50, first_time="T1", last_time="T2"),
        ]
        overlap = [
            OverlapResult(mac="aa:bb:cc:dd:ee:01", ap_pair=("albert", "golem"),
                          rssi_diff=3.0, overlap_count=10, total_samples=20,
                          avg_rssi_a=-55, avg_rssi_b=-58,
                          ifname_a="phy1-ap0", ifname_b="phy1-ap0"),
            OverlapResult(mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
                          rssi_diff=2.0, overlap_count=80, total_samples=100,
                          avg_rssi_a=-52, avg_rssi_b=-54,
                          ifname_a="phy1-ap0", ifname_b="phy1-ap0"),
        ]

        rec = Recommender()
        recs = rec.txpower_recommendations(thrash, overlap)

        assert len(recs) == 2
        assert recs[0].ap_pair == ("golem", "pingu")
        assert recs[1].ap_pair == ("albert", "golem")

    def test_includes_txpower_data_when_available(self):
        """With txpower data, recommendations include current and suggested values."""
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=50,
            first_time="2026-02-16T08:00:00Z",
            last_time="2026-02-16T08:10:00Z",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            rssi_diff=3.0,
            overlap_count=100,
            total_samples=120,
            avg_rssi_a=-52,
            avg_rssi_b=-55,
            ifname_a="phy1-ap0",
            ifname_b="phy1-ap0",
        )]
        txpower = [
            TxPowerReading(ap="golem", radio="radio1", ifname="phy1-ap0",
                           txpower_dbm=23, configured_txpower=23, channel=149, frequency_mhz=5745),
            TxPowerReading(ap="pingu", radio="radio1", ifname="phy1-ap0",
                           txpower_dbm=20, configured_txpower=20, channel=149, frequency_mhz=5745),
        ]

        rec = Recommender(overlap_threshold=6)
        recs = rec.txpower_recommendations(thrash, overlap, txpower=txpower)

        assert len(recs) == 1
        r = recs[0]
        assert r.louder_ap == "golem"
        assert r.current_txpower_a == 23
        assert r.current_txpower_b == 20
        assert r.suggested_txpower is not None
        # Conservative 2 dBm step: 23 - 2 = 21
        assert r.suggested_txpower == 21

    def test_suggested_txpower_clamped_to_minimum(self):
        """Suggested txpower should not go below 5 dBm."""
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=50,
            first_time="T1",
            last_time="T2",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            rssi_diff=0.5,
            overlap_count=100,
            total_samples=120,
            avg_rssi_a=-52,
            avg_rssi_b=-55,
            ifname_a="phy1-ap0",
            ifname_b="phy1-ap0",
        )]
        txpower = [
            TxPowerReading(ap="golem", radio="radio1", ifname="phy1-ap0",
                           txpower_dbm=6, configured_txpower=6, channel=149, frequency_mhz=5745),
        ]

        rec = Recommender(overlap_threshold=6)
        recs = rec.txpower_recommendations(thrash, overlap, txpower=txpower)

        assert recs[0].suggested_txpower == 5

    def test_skips_when_rssi_below_floor(self):
        """Should not suggest reduction when RSSI is already weak."""
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("albert", "pingu"),
            count=30,
            first_time="T1",
            last_time="T2",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("albert", "pingu"),
            rssi_diff=3.5,
            overlap_count=60,
            total_samples=353,
            avg_rssi_a=-84,
            avg_rssi_b=-83,
            ifname_a="phy1-ap0",
            ifname_b="phy1-ap0",
        )]
        txpower = [
            TxPowerReading(ap="albert", radio="radio1", ifname="phy1-ap0",
                           txpower_dbm=19, configured_txpower=19, channel=100, frequency_mhz=5500),
            TxPowerReading(ap="pingu", radio="radio1", ifname="phy1-ap0",
                           txpower_dbm=20, configured_txpower=20, channel=100, frequency_mhz=5500),
        ]

        rec = Recommender(overlap_threshold=6, rssi_floor=-75)
        recs = rec.txpower_recommendations(thrash, overlap, txpower=txpower)

        assert len(recs) == 1
        assert recs[0].suggested_txpower is None
        assert recs[0].skip_reason is not None
        assert "-75" in recs[0].skip_reason

    def test_prefers_higher_txpower_ap(self):
        """Should reduce the AP with higher txpower (more headroom)."""
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=20,
            first_time="T1",
            last_time="T2",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            rssi_diff=1.0,
            overlap_count=50,
            total_samples=100,
            avg_rssi_a=-60,  # golem slightly louder
            avg_rssi_b=-61,
            ifname_a="phy1-ap0",
            ifname_b="phy1-ap0",
        )]
        txpower = [
            TxPowerReading(ap="golem", radio="radio1", ifname="phy1-ap0",
                           txpower_dbm=16, configured_txpower=16, channel=100, frequency_mhz=5500),
            TxPowerReading(ap="pingu", radio="radio1", ifname="phy1-ap0",
                           txpower_dbm=22, configured_txpower=22, channel=100, frequency_mhz=5500),
        ]

        rec = Recommender()
        recs = rec.txpower_recommendations(thrash, overlap, txpower=txpower)

        assert len(recs) == 1
        # pingu has higher txpower (22 vs 16), reduce that one
        assert recs[0].louder_ap == "pingu"
        assert recs[0].suggested_txpower == 20

    def test_no_txpower_data_gives_none(self):
        """Without txpower data, fields should be None."""
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=50,
            first_time="T1",
            last_time="T2",
        )]
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            rssi_diff=3.0,
            overlap_count=100,
            total_samples=120,
            avg_rssi_a=-52,
            avg_rssi_b=-55,
            ifname_a="phy1-ap0",
            ifname_b="phy1-ap0",
        )]

        rec = Recommender()
        recs = rec.txpower_recommendations(thrash, overlap)

        assert recs[0].current_txpower_a is None
        assert recs[0].suggested_txpower is None


class TestUsteerRecommendation:
    def test_recommends_min_snr_for_weak_associations(self):
        weak = [WeakAssociation(
            mac="aa:bb:cc:dd:ee:01",
            ap="pingu",
            avg_snr=8,
            sample_count=100,
        )]

        rec = Recommender()
        commands = rec.usteer_commands(weak)

        assert len(commands) >= 1
        assert any("min_snr" in c.command or "min_connect_snr" in c.command
                    for c in commands)


class TestUCICommand:
    def test_ssh_format(self):
        cmd = UCICommand(
            ap="pingu",
            ssh_prefix="ssh root@pingu",
            command="uci set wireless.radio1.txpower=14",
            reason="Reduce overlap with golem on radio1 (avg 3 dB difference)",
        )
        assert str(cmd) == "ssh root@pingu uci set wireless.radio1.txpower=14"
