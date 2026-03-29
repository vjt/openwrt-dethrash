import json
import pytest
from wifi_dethrash.dashboard import generate_dashboard, generate_dashboard_api
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
        assert "usteer Config" in titles


    def test_has_thrashing_rate_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))
        titles = [p["title"] for p in parsed["panels"]]
        assert "Connects per Hour" in titles

    def test_has_roaming_timeline_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))
        titles = [p["title"] for p in parsed["panels"]]
        assert "Roaming Events" in titles

    def test_has_rssi_heatmap_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))
        titles = [p["title"] for p in parsed["panels"]]
        assert "RSSI Heatmap" in titles

    def test_has_snr_distribution_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))
        titles = [p["title"] for p in parsed["panels"]]
        assert "SNR Distribution" in titles

    def test_has_usteer_effectiveness_panel(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))
        titles = [p["title"] for p in parsed["panels"]]
        assert "usteer Effectiveness" in titles

    def test_panel_count_without_locations(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))
        assert len(parsed["panels"]) == 11

    def test_panel_count_with_locations(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        locations = {"mowgli": "-1 / Garden"}
        parsed = json.loads(generate_dashboard(aps, ap_locations=locations))
        assert len(parsed["panels"]) == 12

    def test_topology_panel_present_with_locations(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        locations = {"mowgli": "-1 / Garden"}
        parsed = json.loads(generate_dashboard(aps, ap_locations=locations))
        titles = [p["title"] for p in parsed["panels"]]
        assert "AP Topology" in titles

    def test_topology_panel_absent_without_locations(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        parsed = json.loads(generate_dashboard(aps))
        titles = [p["title"] for p in parsed["panels"]]
        assert "AP Topology" not in titles

    def test_topology_groups_by_floor(self):
        aps = [
            APInfo(hostname="golem", instance="golem:9100"),
            APInfo(hostname="albert", instance="albert:9100"),
        ]
        locations = {
            "golem": "Ground floor / Living room",
            "albert": "First floor / Bedroom",
        }
        parsed = json.loads(generate_dashboard(aps, ap_locations=locations))
        topo = next(p for p in parsed["panels"] if p["title"] == "AP Topology")
        elements = topo["options"]["root"]["elements"]
        names = [e["name"] for e in elements]
        assert "floor-Ground floor" in names
        assert "floor-First floor" in names
        assert "ap-golem" in names
        assert "ap-albert" in names


class TestDashboardAPI:
    def test_returns_dict_not_string(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        result = generate_dashboard_api(aps, "prom-abc", "vl-xyz")
        assert isinstance(result, dict)

    def test_has_fixed_uid(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        result = generate_dashboard_api(aps, "prom-abc", "vl-xyz")
        assert result["uid"] == "wifi-dethrash"

    def test_no_inputs_or_requires(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        result = generate_dashboard_api(aps, "prom-abc", "vl-xyz")
        assert "__inputs" not in result
        assert "__requires" not in result

    def test_substitutes_datasource_uids(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        result = generate_dashboard_api(aps, "prom-abc", "vl-xyz")

        raw = json.dumps(result)
        assert "${DS_PROMETHEUS}" not in raw
        assert "${DS_VICTORIALOGS}" not in raw
        assert "prom-abc" in raw
        assert "vl-xyz" in raw

    def test_panels_match_file_import_count(self):
        aps = [APInfo(hostname="mowgli", instance="mowgli:9100")]
        file_parsed = json.loads(generate_dashboard(aps))
        api_result = generate_dashboard_api(aps, "prom-abc", "vl-xyz")
        api_panels: list[object] = api_result["panels"]  # type: ignore[assignment]
        assert len(api_panels) == len(file_parsed["panels"])
