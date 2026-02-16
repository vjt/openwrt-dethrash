from wifi_dethrash.utils import ifname_to_radio


class TestIfnameToRadio:
    def test_phy_modern_naming(self):
        assert ifname_to_radio("phy1-ap0") == "radio1"
        assert ifname_to_radio("phy0-ap0") == "radio0"

    def test_wlan_legacy_naming(self):
        assert ifname_to_radio("wlan0") == "radio0"
        assert ifname_to_radio("wlan1") == "radio1"

    def test_unknown_passthrough(self):
        assert ifname_to_radio("eth0") == "eth0"
