import json
import pytest
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

VL_EVENTS = '{"_time":"2026-02-16T08:00:00Z","_msg":"phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:01 auth_alg=open","tags.hostname":"pingu"}\n'


class TestCLI:
    def test_runs_and_produces_report(self, respx_mock):
        # VM: label values
        respx_mock.get("http://vm:8428/api/v1/label/instance/values").respond(
            json=VM_LABEL_RESP
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
