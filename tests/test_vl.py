import pytest
from datetime import datetime, timezone
from wifi_dethrash.sources.vl import VictoriaLogsClient, HostapdEvent


JSONL_RESPONSE = (
    '{"_time":"2026-02-16T07:49:56Z","_msg":"phy1-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=ft","tags.hostname":"pingu"}\n'
    '{"_time":"2026-02-16T07:52:47Z","_msg":"phy1-ap0: AP-STA-DISCONNECTED de:ad:be:ef:00:01","tags.hostname":"pingu"}\n'
    '{"_time":"2026-02-16T07:52:48Z","_msg":"phy1-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=open","tags.hostname":"golem"}\n'
)


class TestFetchEvents:
    def test_parses_connect_and_disconnect(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=JSONL_RESPONSE,
        )

        client = VictoriaLogsClient("http://vl:9428")
        start = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 8, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end)

        assert len(events) == 3

        e = events[0]
        assert e.event == "connected"
        assert e.mac == "de:ad:be:ef:00:01"
        assert e.ap == "pingu"
        assert e.auth_alg == "ft"
        assert e.time == "2026-02-16T07:49:56Z"

        e = events[1]
        assert e.event == "disconnected"
        assert e.mac == "de:ad:be:ef:00:01"
        assert e.ap == "pingu"
        assert e.auth_alg is None

        e = events[2]
        assert e.event == "connected"
        assert e.auth_alg == "open"
        assert e.ap == "golem"

    def test_mac_filter(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=JSONL_RESPONSE,
        )

        client = VictoriaLogsClient("http://vl:9428")
        start = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 8, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end, macs=["de:ad:be:ef:00:01"])

        # The query should include a MAC filter — all 3 events match this MAC
        assert len(events) == 3

    def test_custom_hostname_field(self, respx_mock):
        resp_text = '{"_time":"2026-02-16T08:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:ff auth_alg=open","host":"router1"}\n'
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=resp_text,
        )

        client = VictoriaLogsClient("http://vl:9428", hostname_field="host")
        start = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 9, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end)

        assert events[0].ap == "router1"

    def test_sorts_by_time(self, respx_mock):
        # Out of order
        resp_text = (
            '{"_time":"2026-02-16T08:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:ff auth_alg=open","tags.hostname":"b"}\n'
            '{"_time":"2026-02-16T07:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:ff auth_alg=ft","tags.hostname":"a"}\n'
        )
        respx_mock.get("http://vl:9428/select/logsql/query").respond(text=resp_text)

        client = VictoriaLogsClient("http://vl:9428")
        start = datetime(2026, 2, 16, 6, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 9, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end)

        assert events[0].time == "2026-02-16T07:00:00Z"
        assert events[1].time == "2026-02-16T08:00:00Z"
