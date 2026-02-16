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
        dashboard = generate_dashboard(aps, datasource="Prometheus")
        parsed = json.loads(dashboard)

        assert "dashboard" in parsed
        assert parsed["dashboard"]["title"] == "WiFi Mesh Health"

    def test_has_rssi_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        panels = parsed["dashboard"]["panels"]
        titles = [p["title"] for p in panels]
        assert "RSSI by Station" in titles

    def test_has_noise_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        panels = parsed["dashboard"]["panels"]
        titles = [p["title"] for p in panels]
        assert "Noise Floor" in titles

    def test_has_events_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))

        panels = parsed["dashboard"]["panels"]
        titles = [p["title"] for p in panels]
        assert "Hostapd Events" in titles or "Connect/Disconnect Events" in titles
