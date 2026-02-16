import pytest
from wifi_dethrash.analyzers.thrashing import ThrashingDetector, ThrashSequence
from wifi_dethrash.sources.vl import HostapdEvent


def _connect(mac, ap, time, auth_alg="ft"):
    return HostapdEvent(event="connected", mac=mac, ap=ap, time=time, auth_alg=auth_alg)


def _disconnect(mac, ap, time):
    return HostapdEvent(event="disconnected", mac=mac, ap=ap, time=time)


class TestThrashingDetection:
    def test_detects_simple_thrash(self):
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:06Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:09Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        assert len(sequences) == 1
        s = sequences[0]
        assert s.mac == "aa:bb:cc:dd:ee:01"
        assert set(s.ap_pair) == {"pingu", "golem"}
        assert s.count == 4

    def test_too_few_connects_not_thrashing(self):
        """Two connects between the same pair is below min_count=3."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)
        assert sequences == []

    def test_large_gap_not_thrashing(self):
        """Three connects with gaps exceeding max_gap are not thrashing."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:05:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:10:00Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)
        assert sequences == []

    def test_gap_breaks_sequence(self):
        """Long gap between connects breaks the thrash sequence."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:06Z"),
            # 5 minute gap — breaks the sequence
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:05:06Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        assert len(sequences) == 1
        assert sequences[0].count == 3  # only first 3

    def test_multiple_macs(self):
        """Detects thrashing per-MAC independently."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:02", "albert", "2026-02-16T08:00:01Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:02Z"),
            _connect("aa:bb:cc:dd:ee:02", "gordon", "2026-02-16T08:00:03Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:04Z"),
            _connect("aa:bb:cc:dd:ee:02", "albert", "2026-02-16T08:00:05Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        assert len(sequences) == 2

    def test_disconnects_are_ignored(self):
        """Only connect events contribute to thrashing detection."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _disconnect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:01Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
            _disconnect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:04Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:06Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        assert len(sequences) == 1
        assert sequences[0].count == 3

    def test_three_ap_cycle_not_a_pair(self):
        """A->B->C->A is not a pair thrash — it's normal roaming through rooms."""
        events = [
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:00Z"),
            _connect("aa:bb:cc:dd:ee:01", "golem", "2026-02-16T08:00:03Z"),
            _connect("aa:bb:cc:dd:ee:01", "albert", "2026-02-16T08:00:06Z"),
            _connect("aa:bb:cc:dd:ee:01", "pingu", "2026-02-16T08:00:09Z"),
        ]
        detector = ThrashingDetector(max_gap=60)
        sequences = detector.detect(events)

        # Should NOT detect as thrash — it visited 3 different APs
        assert sequences == []
