import pytest
from datetime import datetime, timezone
from wifi_dethrash.sources.vl import VictoriaLogsClient, HostapdEvent


JSONL_RESPONSE = (
    '{"_time":"2026-02-16T07:49:56Z","_msg":"phy1-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=ft","tags.hostname":"pingu"}\n'
    '{"_time":"2026-02-16T07:52:47Z","_msg":"phy1-ap0: AP-STA-DISCONNECTED de:ad:be:ef:00:01","tags.hostname":"pingu"}\n'
    '{"_time":"2026-02-16T07:52:48Z","_msg":"phy0-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=open","tags.hostname":"golem"}\n'
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
        assert e.ifname == "phy1-ap0"
        assert e.time == "2026-02-16T07:49:56Z"

        e = events[1]
        assert e.event == "disconnected"
        assert e.mac == "de:ad:be:ef:00:01"
        assert e.ap == "pingu"
        assert e.auth_alg is None
        assert e.ifname == "phy1-ap0"

        e = events[2]
        assert e.event == "connected"
        assert e.auth_alg == "open"
        assert e.ap == "golem"
        assert e.ifname == "phy0-ap0"

    def test_mac_filter_includes_mac_in_query(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=JSONL_RESPONSE,
        )

        client = VictoriaLogsClient("http://vl:9428")
        start = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 8, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end, macs=["de:ad:be:ef:00:01"])

        assert len(events) == 3
        # Verify the query parameter included the MAC filter
        request = respx_mock.calls[0].request
        query_param = dict(request.url.params)["query"]
        assert 'de:ad:be:ef:00:01' in query_param

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

    def test_skips_malformed_json_lines(self, respx_mock):
        """Malformed JSONL lines should be silently skipped."""
        resp_text = (
            '{"_time":"2026-02-16T07:49:56Z","_msg":"phy1-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=ft","tags.hostname":"pingu"}\n'
            'NOT VALID JSON\n'
            '{"_time":"2026-02-16T07:52:48Z","_msg":"phy0-ap0: AP-STA-CONNECTED de:ad:be:ef:00:01 auth_alg=open","tags.hostname":"golem"}\n'
        )
        respx_mock.get("http://vl:9428/select/logsql/query").respond(text=resp_text)

        client = VictoriaLogsClient("http://vl:9428")
        start = datetime(2026, 2, 16, 7, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 16, 8, 0, tzinfo=timezone.utc)
        events = client.fetch_events(start, end)

        assert len(events) == 2
        assert events[0].ap == "pingu"
        assert events[1].ap == "golem"

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


DHCP_RESPONSE = (
    # Technitium format (dash-separated MAC)
    '{"_msg":"[2026-03-29 13:44:14 UTC] DHCP Server leased IP address [192.168.42.41] to enterprise [84-2F-57-07-9E-3D] for scope: Default","tags.appname":"docker"}\n'
    '{"_msg":"[2026-03-29 13:38:08 UTC] DHCP Server leased IP address [192.168.42.21] to tv [E0-85-4D-B3-BC-C0] for scope: Default","tags.appname":"docker"}\n'
    # dnsmasq format (colon-separated MAC)
    '{"_msg":"DHCPACK(br-lan) 192.168.253.164 7e:0b:7c:b7:30:8e Watch","tags.appname":"dnsmasq-dhcp"}\n'
)


class TestFetchMacNames:
    def test_parses_technitium_format(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=DHCP_RESPONSE,
        )

        client = VictoriaLogsClient("http://vl:9428")
        names = client.fetch_mac_names()

        assert names["84:2f:57:07:9e:3d"] == "enterprise"
        assert names["e0:85:4d:b3:bc:c0"] == "tv"

    def test_parses_dnsmasq_format(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=DHCP_RESPONSE,
        )

        client = VictoriaLogsClient("http://vl:9428")
        names = client.fetch_mac_names()

        assert names["7e:0b:7c:b7:30:8e"] == "Watch"

    def test_all_macs_lowercase(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=DHCP_RESPONSE,
        )

        client = VictoriaLogsClient("http://vl:9428")
        names = client.fetch_mac_names()

        assert all(k == k.lower() for k in names)

    def test_empty_response(self, respx_mock):
        respx_mock.get("http://vl:9428/select/logsql/query").respond(text="")

        client = VictoriaLogsClient("http://vl:9428")
        names = client.fetch_mac_names()

        assert names == {}
