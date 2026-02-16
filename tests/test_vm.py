import pytest
from datetime import datetime, timezone
from dethrash.sources.vm import VictoriaMetricsClient, APInfo, RSSIReading


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
                    "mac": "de:ad:be:ef:99:99",
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
                    "mac": "de:ad:be:ef:99:99",
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
        assert r.mac == "de:ad:be:ef:99:99"
        assert r.ap == "mowgli"
        assert r.rssi == -55
        assert r.timestamp == 1700000000

    def test_mac_filter(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=QUERY_RANGE_RESPONSE
        )

        client = VictoriaMetricsClient("http://vm:8428")
        start = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        end = datetime(2023, 11, 14, 22, 14, 20, tzinfo=timezone.utc)
        readings = client.fetch_rssi(start, end, macs=["de:ad:be:ef:99:99"])

        # All readings match, so same count — but the query should have a label filter
        assert len(readings) == 4


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
