import pytest
from wifi_dethrash.report import render_report
from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.recommender import (
    TxPowerPlan, TxPowerChange, PairImpact, UCICommand,
)


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
        output = render_report(thrash=thrash, overlap=[], weak=[])
        assert "aa:bb:cc:dd:ee:01" in output
        assert "golem" in output
        assert "50 connects in 2 episodes" in output

    def test_includes_txpower_plan(self):
        plan = TxPowerPlan(
            changes=[TxPowerChange(
                ap="golem", radio="radio1", current=23, proposed=21,
                reasons=("reduce for golem<->pingu",),
            )],
            pair_impacts=[PairImpact(
                ap_pair=("golem", "pingu"), radio="radio1",
                total_thrash_connects=50,
                rssi_diff_before=2.0, rssi_diff_after=4.0,
                signal_diff_threshold=9,
            )],
            signal_diff_threshold=9,
        )
        output = render_report(thrash=[], overlap=[], weak=[], plan=plan)
        assert "Txpower plan:" in output
        assert "golem" in output
        assert "23 -> 21" in output
        assert "uci set wireless.radio1.txpower=21" in output

    def test_shows_pair_impact(self):
        plan = TxPowerPlan(
            changes=[TxPowerChange(
                ap="golem", radio="radio1", current=16, proposed=18,
                reasons=("increase for golem<->mowgli",),
            )],
            pair_impacts=[PairImpact(
                ap_pair=("golem", "mowgli"), radio="radio1",
                total_thrash_connects=20,
                rssi_diff_before=1.0, rssi_diff_after=3.0,
                signal_diff_threshold=9,
            )],
            signal_diff_threshold=9,
        )
        output = render_report(thrash=[], overlap=[], weak=[], plan=plan)
        assert "Expected impact" in output
        assert "golem <-> mowgli" in output
        assert "1.0 -> 3.0" in output

    def test_includes_usteer_commands(self):
        commands = [UCICommand(
            ap="all",
            ssh_prefix="ssh root@<ap>",
            command="uci set usteer.@usteer[0].signal_diff_threshold=9",
            reason="test reason",
        )]
        output = render_report(
            thrash=[], overlap=[], weak=[],
            usteer_commands=commands,
        )
        assert "usteer" in output.lower()
        assert "signal_diff_threshold=9" in output

    def test_filters_low_sample_overlap(self):
        overlap = [
            OverlapResult(mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
                          rssi_diff=3.0, overlap_count=50, total_samples=100,
                          avg_rssi_a=-52, avg_rssi_b=-55),
            OverlapResult(mac="aa:bb:cc:dd:ee:02", ap_pair=("albert", "pingu"),
                          rssi_diff=2.0, overlap_count=2, total_samples=10,
                          avg_rssi_a=-60, avg_rssi_b=-58),
        ]
        output = render_report(thrash=[], overlap=overlap, weak=[])
        assert "golem <-> pingu" in output
        assert "albert <-> pingu" not in output.split("omitted")[0]
        assert "1 minor overlaps" in output

    def test_empty_report(self):
        output = render_report(thrash=[], overlap=[], weak=[])
        assert "No thrashing" in output or "clean" in output.lower()

    def test_overlap_shows_rssi_values(self):
        overlap = [OverlapResult(
            mac="aa:bb:cc:dd:ee:01", ap_pair=("golem", "pingu"),
            rssi_diff=3.0, overlap_count=50, total_samples=100,
            avg_rssi_a=-52, avg_rssi_b=-55,
        )]
        output = render_report(thrash=[], overlap=overlap, weak=[])
        assert "-52 dBm" in output
        assert "-55 dBm" in output
