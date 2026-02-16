import re


def ifname_to_radio(ifname: str) -> str:
    """Convert interface name to radio name.

    'phy1-ap0' -> 'radio1'  (modern OpenWrt naming)
    'wlan0'    -> 'radio0'  (legacy OpenWrt naming)
    """
    m = re.match(r"phy(\d+)", ifname)
    if m:
        return f"radio{m.group(1)}"
    m = re.match(r"wlan(\d+)", ifname)
    if m:
        return f"radio{m.group(1)}"
    return ifname
