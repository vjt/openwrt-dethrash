import pytest
from wifi_dethrash.recommender import Recommender, UCICommand
from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation


class TestTxPowerRecommendation:
    def test_recommends_power_reduction_for_thrashing_pair(self):
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
        )]

        rec = Recommender()
        commands = rec.txpower_commands(thrash, overlap)

        # Should recommend reducing power on both APs in the pair
        assert len(commands) >= 2
        assert all(c.command.startswith("uci set") for c in commands)
        assert any("golem" in c.ssh_prefix for c in commands)
        assert any("pingu" in c.ssh_prefix for c in commands)

    def test_no_thrashing_no_recommendations(self):
        rec = Recommender()
        commands = rec.txpower_commands([], [])
        assert commands == []


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
            reason="Reduce overlap with golem (avg 3 dB difference)",
        )
        assert str(cmd) == "ssh root@pingu uci set wireless.radio1.txpower=14"
