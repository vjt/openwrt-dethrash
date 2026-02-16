import pytest
from wifi_dethrash.report import render_report
from wifi_dethrash.analyzers.thrashing import ThrashSequence
from wifi_dethrash.analyzers.overlap import OverlapResult
from wifi_dethrash.analyzers.weak import WeakAssociation
from wifi_dethrash.recommender import UCICommand


class TestReport:
    def test_includes_thrash_sequences(self):
        thrash = [ThrashSequence(
            mac="aa:bb:cc:dd:ee:01",
            ap_pair=("golem", "pingu"),
            count=50,
            first_time="2026-02-16T08:00:00Z",
            last_time="2026-02-16T08:10:00Z",
        )]
        output = render_report(
            thrash=thrash, overlap=[], weak=[], commands=[],
        )
        assert "aa:bb:cc:dd:ee:01" in output
        assert "golem" in output
        assert "pingu" in output
        assert "50" in output

    def test_includes_commands_section(self):
        commands = [UCICommand(
            ap="pingu",
            ssh_prefix="ssh root@pingu",
            command="uci set wireless.radio1.txpower=14",
            reason="test reason",
        )]
        output = render_report(
            thrash=[], overlap=[], weak=[], commands=commands,
        )
        assert "ssh root@pingu uci set wireless.radio1.txpower=14" in output

    def test_empty_report(self):
        output = render_report(thrash=[], overlap=[], weak=[], commands=[])
        assert "No thrashing" in output or "clean" in output.lower()
