import json
import httpx
import pytest
import respx
from click.testing import CliRunner
from wifi_dethrash.cli import main


VM_LABEL_RESP = {"data": ["mowgli:9100", "pingu:9100"]}

VM_RSSI_RESP = {
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {"mac": "aa:bb:cc:dd:ee:01", "ifname": "phy1-ap0",
                           "instance": "pingu:9100"},
                "values": [[1700000000, "-55"]],
            },
        ],
    }
}

VM_NOISE_RESP = {
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {"device": "radio1", "frequency": "5745",
                           "instance": "pingu:9100"},
                "values": [[1700000000, "-92"]],
            },
        ],
    }
}

VM_TXPOWER_RESP = {
    "data": {
        "resultType": "vector",
        "result": [],
    }
}

VL_EVENTS = '{"_time":"2026-02-16T08:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:01 auth_alg=open","tags.hostname":"pingu"}\n'


class TestCLI:
    def test_runs_and_produces_report(self, respx_mock):
        # VM: label values
        respx_mock.get("http://vm:8428/api/v1/label/instance/values").respond(
            json=VM_LABEL_RESP
        )
        # VM: txpower instant query
        respx_mock.get("http://vm:8428/api/v1/query").respond(
            json=VM_TXPOWER_RESP
        )
        # VM: RSSI and noise query_range (both hit the same endpoint)
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=VM_RSSI_RESP
        )
        # VL: events
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            text=VL_EVENTS
        )

        runner = CliRunner()
        result = runner.invoke(main, [
            "--vm-url", "http://vm:8428",
            "--vl-url", "http://vl:9428",
            "--window", "1h",
        ])

        assert result.exit_code == 0
        assert "wifi-dethrash report" in result.output

    def test_vm_http_error_shows_friendly_message(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/label/instance/values").respond(
            status_code=400, text="bad query"
        )

        runner = CliRunner()
        result = runner.invoke(main, [
            "--vm-url", "http://vm:8428",
            "--vl-url", "http://vl:9428",
        ])

        assert result.exit_code != 0
        assert "Error: VictoriaMetrics" in result.output
        assert "HTTP 400" in result.output

    def test_vl_http_error_shows_friendly_message(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/label/instance/values").respond(
            json=VM_LABEL_RESP
        )
        respx_mock.get("http://vm:8428/api/v1/query").respond(
            json=VM_TXPOWER_RESP
        )
        respx_mock.get("http://vm:8428/api/v1/query_range").respond(
            json=VM_RSSI_RESP
        )
        respx_mock.get("http://vl:9428/select/logsql/query").respond(
            status_code=502, text="bad gateway"
        )

        runner = CliRunner()
        result = runner.invoke(main, [
            "--vm-url", "http://vm:8428",
            "--vl-url", "http://vl:9428",
        ])

        assert result.exit_code != 0
        assert "Error: VictoriaLogs" in result.output
        assert "HTTP 502" in result.output

    def test_connection_error_shows_friendly_message(self, respx_mock):
        respx_mock.get("http://vm:8428/api/v1/label/instance/values").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        runner = CliRunner()
        result = runner.invoke(main, [
            "--vm-url", "http://vm:8428",
            "--vl-url", "http://vl:9428",
        ])

        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "connect" in result.output.lower()

    def test_invalid_window_format(self):
        runner = CliRunner()
        result = runner.invoke(main, [
            "--vm-url", "http://vm:8428",
            "--vl-url", "http://vl:9428",
            "--window", "banana",
        ])

        assert result.exit_code != 0
        assert "Invalid window format" in result.output
