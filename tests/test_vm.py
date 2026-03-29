import pytest
from datetime import datetime, timezone
from wifi_dethrash.sources.vm import VictoriaMetricsClient, APInfo, RSSIReading, TxPowerReading


# --- Fixtures ---

LABEL_VALUES_RESPONSE = {
    "data": ["mowgli:9100", "pingu:9100", "albert:9100"]
}

QUERY_RANGE_RESPONSE = {
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {
                    "mac": "de:ad:be:ef:00:01",
                    "ifname": "phy1-ap0",
                    "instance": "mowgli:9100",
                },
                "values": [
                    [1700000000, "-55"],
                    [1700000030, "-57"],
                ],
            },
            {
                "metric": {
                    "mac": "de:ad:be:ef:00:01",
                    "ifname": "phy1-ap0",
                    "instance": "pingu:9100",
                },
                "values": [
                    [1700000000, "-62"],
                    [1700000030, "-60"],
                ],
            },
        ],
    }
}

NOISE_RESPONSE = {
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {
                    "device": "radio1",
                    "frequency": "5745",
                    "instance": "mowgli:9100",
                },
                "values": [
                    [1700000000, "-92"],
                    [1700000030, "-91"],
                ],
            },
        ],
    }
}


class TestDiscoverAPs:
    def test_extracts_hostnames_from_instance_label(self, respx_mock):
        respx_mock.get(
            "http://vm:8428/api/v1/label/instance/values",
            params={"match[]": "wifi_station_signal_dbm"},
        ).respond(json=LABEL_VALUES_RESPONSE)

        client = VictoriaMetricsClient("http://vm:8428", host_label="instance")
        aps = client.discover_aps()

        assert len(aps) == 3
        assert aps[0].hostname == "albert"
        assert aps[0].instance == "albert:9100"

    def test_custom_host_label(self, respx_mock):
        respx_mock.get(
            "http://vm:8428/api/v1/label/hostname/values",
            params={"match[]": "wifi_station_signal_dbm"},
        ).respond(json={"data": ["mowgli", "pingu"]})

        client = VictoriaMetricsClient("http://vm:8428", host_label="hostname")
        aps = client.discover_aps()

        assert len(aps) == 2
        assert aps[0].hostname == "mowgli"
        assert aps[0].instance == "mowgli"  # no port stripping needed


class TestFetchRSSI:
    def test_returns_readings_with_ap_and_mac(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=QUERY_RANGE_RESPONSE
        )

        client = VictoriaMetricsClient("http://vm:8428")
        start = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        end = datetime(2023, 11, 14, 22, 14, 20, tzinfo=timezone.utc)
        readings = client.fetch_rssi(start, end)

        assert len(readings) == 4  # 2 series x 2 values each
        r = readings[0]
        assert r.mac == "de:ad:be:ef:00:01"
        assert r.ap == "mowgli"
        assert r.rssi == -55
        assert r.timestamp == 1700000000

    def test_mac_filter_includes_mac_in_query(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=QUERY_RANGE_RESPONSE
        )

        client = VictoriaMetricsClient("http://vm:8428")
        start = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        end = datetime(2023, 11, 14, 22, 14, 20, tzinfo=timezone.utc)
        readings = client.fetch_rssi(start, end, macs=["de:ad:be:ef:00:01"])

        assert len(readings) == 4
        # Verify the query parameter included the MAC filter
        request = respx_mock.calls[0].request
        query_param = dict(request.url.params)["query"]
        assert 'de:ad:be:ef:00:01' in query_param


class TestFetchNoise:
    def test_returns_noise_per_ap_and_radio(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=NOISE_RESPONSE
        )

        client = VictoriaMetricsClient("http://vm:8428")
        start = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        end = datetime(2023, 11, 14, 22, 14, 20, tzinfo=timezone.utc)
        noise = client.fetch_noise(start, end)

        assert len(noise) == 2
        assert noise[0].ap == "mowgli"
        assert noise[0].radio == "radio1"
        assert noise[0].frequency == 5745
        assert noise[0].noise_dbm == -92


TXPOWER_RESPONSE = {
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"device": "radio1", "ifname": "phy1-ap0",
                           "ssid": "MyNet", "instance": "mowgli:9100"},
                "value": [1700000000, "20"],
            },
            {
                "metric": {"device": "radio0", "ifname": "phy0-ap0",
                           "ssid": "MyNet", "instance": "mowgli:9100"},
                "value": [1700000000, "14"],
            },
        ],
    }
}

CONFIGURED_TXPOWER_RESPONSE = {
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"device": "radio1", "instance": "mowgli:9100"},
                "value": [1700000000, "23"],
            },
        ],
    }
}

CHANNEL_RESPONSE = {
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"device": "radio1", "instance": "mowgli:9100"},
                "value": [1700000000, "149"],
            },
        ],
    }
}

FREQUENCY_RESPONSE = {
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"device": "radio1", "instance": "mowgli:9100"},
                "value": [1700000000, "5745"],
            },
        ],
    }
}


class TestFetchTxPower:
    def test_returns_txpower_per_radio(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query").mock(
            side_effect=lambda request: _txpower_route(request)
        )

        with VictoriaMetricsClient("http://vm:8428") as client:
            readings = client.fetch_txpower()

        assert len(readings) == 2
        r1 = next(r for r in readings if r.radio == "radio1")
        assert r1.ap == "mowgli"
        assert r1.txpower_dbm == 20
        assert r1.configured_txpower == 23
        assert r1.channel == 149
        assert r1.frequency_mhz == 5745
        assert r1.ssid == "MyNet"

    def test_works_without_configured_txpower(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query").mock(
            side_effect=lambda request: _txpower_route_minimal(request)
        )

        with VictoriaMetricsClient("http://vm:8428") as client:
            readings = client.fetch_txpower()

        assert len(readings) == 1
        assert readings[0].txpower_dbm == 20
        assert readings[0].configured_txpower is None
        assert readings[0].ssid == ""


def _txpower_route(request):
    import httpx
    query = dict(request.url.params).get("query", "")
    if query == "wifi_radio_txpower_dbm":
        return httpx.Response(200, json=TXPOWER_RESPONSE)
    elif query == "wifi_radio_configured_txpower":
        return httpx.Response(200, json=CONFIGURED_TXPOWER_RESPONSE)
    elif query == "wifi_radio_channel":
        return httpx.Response(200, json=CHANNEL_RESPONSE)
    elif query == "wifi_radio_frequency_mhz":
        return httpx.Response(200, json=FREQUENCY_RESPONSE)
    return httpx.Response(200, json={"data": {"resultType": "vector", "result": []}})


def _txpower_route_minimal(request):
    import httpx
    query = dict(request.url.params).get("query", "")
    if query == "wifi_radio_txpower_dbm":
        resp = {"data": {"resultType": "vector", "result": [
            {"metric": {"device": "radio1", "ifname": "phy1-ap0",
                         "instance": "mowgli:9100"},
             "value": [1700000000, "20"]},
        ]}}
        return httpx.Response(200, json=resp)
    return httpx.Response(200, json={"data": {"resultType": "vector", "result": []}})
