import pytest
from wifi_dethrash.recommender import Recommender, UCICommand
from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.sources.vm import TxPowerReading


def _thrash(pair, count):
    return ThrashSequence(mac="aa:bb:cc:dd:ee:01", ap_pair=pair,
                          count=count, first_time="T1", last_time="T2")


def _overlap(pair, rssi_a, rssi_b, diff=None, count=50, total=100):
    if diff is None:
        diff = abs(rssi_a - rssi_b)
    return OverlapResult(mac="aa:bb:cc:dd:ee:01", ap_pair=pair,
                         rssi_diff=diff, overlap_count=count, total_samples=total,
                         avg_rssi_a=rssi_a, avg_rssi_b=rssi_b,
                         ifname_a="phy1-ap0", ifname_b="phy1-ap0")


def _txp(ap, txpower):
    return TxPowerReading(ap=ap, radio="radio1", ifname="phy1-ap0",
                          txpower_dbm=txpower, configured_txpower=txpower,
                          channel=100, frequency_mhz=5500)


class TestTxPowerPlan:
    def test_reduces_louder_ap_when_healthy(self):
        """When RSSI is healthy, reduce the AP with higher txpower."""
        plan = Recommender().plan(
            [_thrash(("golem", "pingu"), 50)],
            [_overlap(("golem", "pingu"), -52, -55)],
            txpower=[_txp("golem", 23), _txp("pingu", 20)],
        )
        assert len(plan.changes) == 1
        c = plan.changes[0]
        assert c.ap == "golem"
        assert c.proposed == 21  # 23 - 2

    def test_increases_lower_txpower_ap_when_weak(self):
        """When RSSI is weak, increase the AP with lower txpower (more headroom)."""
        plan = Recommender(rssi_floor=-75).plan(
            [_thrash(("albert", "pingu"), 30)],
            [_overlap(("albert", "pingu"), -84, -83)],
            txpower=[_txp("albert", 19), _txp("pingu", 20)],
        )
        assert len(plan.changes) == 1
        c = plan.changes[0]
        assert c.ap == "albert"
        assert c.proposed == 21  # 19 + 2 (albert has lower txpower)

    def test_does_not_increase_high_txpower_ap_when_weak(self):
        """When RSSI is weak, don't increase the AP that already has higher txpower."""
        plan = Recommender(rssi_floor=-75).plan(
            [_thrash(("albert", "pingu"), 30)],
            [_overlap(("albert", "pingu"), -87, -85)],
            txpower=[_txp("albert", 21), _txp("pingu", 20)],
        )
        assert len(plan.changes) == 1
        c = plan.changes[0]
        # albert is RSSI-quieter but has higher txpower — increase pingu instead
        assert c.ap == "pingu"
        assert c.proposed == 22  # 20 + 2

    def test_no_change_when_weak_and_equal_txpower(self):
        """When RSSI is weak and both APs have equal txpower, it's a coverage gap."""
        plan = Recommender(rssi_floor=-75).plan(
            [_thrash(("albert", "pingu"), 30)],
            [_overlap(("albert", "pingu"), -84, -83)],
            txpower=[_txp("albert", 20), _txp("pingu", 20)],
        )
        assert len(plan.changes) == 0

    def test_consolidates_conflicting_votes(self):
        """When an AP gets increase and reduce votes, higher severity wins."""
        plan = Recommender(rssi_floor=-75).plan(
            [
                _thrash(("golem", "gordon"), 50),   # healthy, wants gordon reduced
                _thrash(("gordon", "pingu"), 5),     # weak, wants gordon increased
            ],
            [
                _overlap(("golem", "gordon"), -60, -58),    # healthy
                _overlap(("gordon", "pingu"), -80, -82),    # weak
            ],
            txpower=[_txp("golem", 16), _txp("gordon", 16), _txp("pingu", 20)],
        )
        gordon_changes = [c for c in plan.changes if c.ap == "gordon"]
        assert len(gordon_changes) == 1
        # 50 connects wants reduce, 5 wants increase -> reduce wins
        assert gordon_changes[0].proposed == 14

    def test_compound_impact_simulation(self):
        """Plan should show before/after RSSI diff for all pairs."""
        plan = Recommender().plan(
            [_thrash(("golem", "gordon"), 50)],
            [_overlap(("golem", "gordon"), -60, -58)],
            txpower=[_txp("golem", 20), _txp("gordon", 16)],
        )
        assert len(plan.pair_impacts) == 1
        i = plan.pair_impacts[0]
        assert i.rssi_diff_before == 2.0
        # golem has higher txpower -> gets reduced by 2
        # golem RSSI: -60 - 2 = -62, gordon stays -58, new diff = 4
        assert i.rssi_diff_after == 4.0

    def test_no_thrashing_empty_plan(self):
        plan = Recommender().plan([], [])
        assert plan.changes == []
        assert plan.pair_impacts == []

    def test_signal_diff_from_overlap(self):
        """signal_diff_threshold should cover max observed diff + margin."""
        plan = Recommender().plan(
            [_thrash(("golem", "pingu"), 20)],
            [_overlap(("golem", "pingu"), -60, -55, diff=5.0)],
            txpower=[_txp("golem", 16), _txp("pingu", 20)],
        )
        # int(5.0) + 3 = 8
        assert plan.signal_diff_threshold == 8

    def test_impact_shows_signal_diff_coverage(self):
        """Each pair impact should include signal_diff_threshold for comparison."""
        plan = Recommender().plan(
            [_thrash(("golem", "pingu"), 20)],
            [_overlap(("golem", "pingu"), -60, -55, diff=5.0)],
            txpower=[_txp("golem", 16), _txp("pingu", 20)],
        )
        assert plan.pair_impacts[0].signal_diff_threshold == 8


class TestUsteerRecommendation:
    def test_complete_config(self):
        """Should output full usteer config: signal_diff + explicit disables."""
        rec = Recommender()
        commands = rec.usteer_commands(9)
        cmd_text = " ".join(c.command for c in commands)

        assert "signal_diff_threshold=9" in cmd_text
        assert "roam_scan_snr=25" in cmd_text
        # Dangerous settings explicitly zeroed out
        assert "roam_trigger_snr=0" in cmd_text
        assert "min_connect_snr=0" in cmd_text
        assert "min_snr=0" in cmd_text
        assert "load_kick_enabled=0" in cmd_text

    def test_no_commands_when_zero(self):
        rec = Recommender()
        assert rec.usteer_commands(0) == []

    def test_ieee80211v_missing_generates_commands(self):
        """Should recommend enabling 802.11v on APs where it's missing."""
        rec = Recommender()
        commands = rec.usteer_commands(9, ieee80211v_missing=["parrot"])
        v_cmds = [c for c in commands if "ieee80211v" in c.command]
        assert len(v_cmds) == 1
        assert v_cmds[0].ap == "parrot"

    def test_ieee80211v_commands_before_usteer(self):
        """802.11v enable commands should come before usteer config."""
        rec = Recommender()
        commands = rec.usteer_commands(9, ieee80211v_missing=["parrot"])
        assert "ieee80211v" in commands[0].command

    def test_no_ieee80211v_when_all_enabled(self):
        """No 802.11v commands when all APs have it enabled."""
        rec = Recommender()
        commands = rec.usteer_commands(9, ieee80211v_missing=[])
        v_cmds = [c for c in commands if "ieee80211v" in c.command]
        assert len(v_cmds) == 0


class TestUCICommand:
    def test_ssh_format(self):
        cmd = UCICommand(
            ap="pingu",
            ssh_prefix="ssh root@pingu",
            command="uci set wireless.radio1.txpower=14",
            reason="Reduce overlap with golem on radio1 (avg 3 dB difference)",
        )
        assert str(cmd) == "ssh root@pingu uci set wireless.radio1.txpower=14"
