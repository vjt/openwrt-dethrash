import pytest
from wifi_dethrash.report import render_report
from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.recommender import TxPowerRecommendation, UCICommand


class TestReport:
    def test_includes_aggregated_thrash(self):
        thrash = [
            ThrashSequence(mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
                           count=20, first_time="2026-02-16T08:00:00Z",
                           last_time="2026-02-16T08:05:00Z"),
            ThrashSequence(mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
                           count=30, first_time="2026-02-16T09:00:00Z",
                           last_time="2026-02-16T09:10:00Z"),
        ]
        output = render_report(
            thrash=thrash, overlap=[], weak=[],
            txpower_recs=[], usteer_commands=[],
        )
        assert "aa:bb:cc:dd:ee:01" in output
        assert "golem" in output
        assert "50 connects in 2 episodes" in output

    def test_includes_txpower_recommendation(self):
        recs = [TxPowerRecommendation(
            ap_pair=("golem", "pingu"),
            radio="radio1",
            total_thrash_connects=50,
            total_thrash_episodes=5,
            avg_rssi_diff=3.0,
            overlap_pct=34,
            avg_rssi_a=-52,
            avg_rssi_b=-55,
            louder_ap="golem",
        )]
        output = render_report(
            thrash=[], overlap=[], weak=[],
            txpower_recs=recs, usteer_commands=[],
        )
        assert "golem <-> pingu" in output
        assert "CRITICAL" in output
        assert "Consider reducing txpower on golem" in output
        assert "-52" in output
        assert "-55" in output

    def test_includes_usteer_commands(self):
        commands = [UCICommand(
            ap="all",
            ssh_prefix="ssh root@<ap>",
            command="uci set usteer.@usteer[0].min_connect_snr=15",
            reason="test reason",
        )]
        output = render_report(
            thrash=[], overlap=[], weak=[],
            txpower_recs=[], usteer_commands=commands,
        )
        assert "usteer" in output.lower()
        assert "min_connect_snr=15" in output

    def test_filters_low_sample_overlap(self):
        overlap = [
            OverlapResult(mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
                          rssi_diff=3.0, overlap_count=50, total_samples=100,
                          avg_rssi_a=-52, avg_rssi_b=-55),
            OverlapResult(mac="aa:bb:cc:dd:ee:02", ap_pair=("albert", "pingu"),
                          rssi_diff=2.0, overlap_count=2, total_samples=10,
                          avg_rssi_a=-60, avg_rssi_b=-58),
        ]
        output = render_report(
            thrash=[], overlap=overlap, weak=[],
            txpower_recs=[], usteer_commands=[],
        )
        # High-sample overlap should be shown
        assert "golem <-> pingu" in output
        # Low-sample overlap should be omitted
        assert "albert <-> pingu" not in output.split("omitted")[0]
        assert "1 minor overlaps" in output

    def test_empty_report(self):
        output = render_report(
            thrash=[], overlap=[], weak=[],
            txpower_recs=[], usteer_commands=[],
        )
        assert "No thrashing" in output or "clean" in output.lower()

    def test_overlap_shows_rssi_values(self):
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
            rssi_diff=3.0, overlap_count=50, total_samples=100,
            avg_rssi_a=-52, avg_rssi_b=-55,
        )]
        output = render_report(
            thrash=[], overlap=overlap, weak=[],
            txpower_recs=[], usteer_commands=[],
        )
        assert "-52 dBm" in output
        assert "-55 dBm" in output
