import json
import pytest
from wifi_dethrash.dashboard import generate_dashboard
from wifi_dethrash.sources.vm import APInfo


class TestDashboard:
    def test_valid_json(self):
        aps = [
            APInfo(hostname="mowgli", instance="mowgli:9100"),
            APInfo(hostname="pingu", instance="pingu:9100"),
        ]
        dashboard = generate_dashboard(aps)
        parsed = json.loads(dashboard)

        assert parsed["title"] == "WiFi Mesh Health"
        assert parsed["schemaVersion"] >= 39
        assert parsed["id"] is None

    def test_has_inputs_for_datasource_selection(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        inputs = {i["name"]: i for i in parsed["__inputs"]}
        assert "DS_PROMETHEUS" in inputs
        assert "DS_VICTORIALOGS" in inputs
        assert inputs["DS_PROMETHEUS"]["pluginId"] == "prometheus"

    def test_has_rssi_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        titles = [p["title"] for p in parsed["panels"]]
        assert "RSSI by Station" in titles

    def test_has_noise_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        titles = [p["title"] for p in parsed["panels"]]
        assert "Noise Floor" in titles

    def test_has_events_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        titles = [p["title"] for p in parsed["panels"]]
        assert "Connect/Disconnect Events" in titles

    def test_panels_have_ids(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        ids = [p["id"] for p in parsed["panels"]]
        assert len(ids) == len(set(ids))  # unique
        assert all(isinstance(i, int) for i in ids)

    def test_datasource_uses_input_variables(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        rssi_panel = parsed["panels"][0]
        assert rssi_panel["datasource"]["uid"] == "${DS_PROMETHEUS}"

    def test_instance_regex_includes_all_aps(self):
        aps = [
            APInfo(hostname="mowgli", instance="mowgli:9100"),
            APInfo(hostname="pingu", instance="pingu:9100"),
        ]
        parsed = json.loads(generate_dashboard(aps))

        expr = parsed["panels"][0]["targets"][0]["expr"]
        assert "mowgli:9100" in expr
        assert "pingu:9100" in expr

    def test_has_txpower_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        titles = [p["title"] for p in parsed["panels"]]
        assert "TX Power by Radio" in titles

    def test_has_80211_status_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        titles = [p["title"] for p in parsed["panels"]]
        assert "802.11r/k/v Status" in titles

    def test_has_usteer_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        titles = [p["title"] for p in parsed["panels"]]
        assert "Usteer Thresholds" in titles
