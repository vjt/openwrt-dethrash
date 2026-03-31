import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class APInfo:
    hostname: str
    instance: str


@dataclass(frozen=True)
class RSSIReading:
    mac: str
    ap: str
    ifname: str
    rssi: int
    timestamp: int


@dataclass(frozen=True)
class NoiseReading:
    ap: str
    radio: str
    frequency: int
    noise_dbm: int
    timestamp: int


@dataclass(frozen=True)
class TxPowerReading:
    ap: str
    radio: str
    ifname: str
    txpower_dbm: int
    configured_txpower: int | None
    channel: int
    frequency_mhz: int
    ssid: str = ""


class VictoriaMetricsClient:
    def __init__(self, base_url: str, host_label: str = "instance"):
        self._base_url = base_url.rstrip("/")
        self._host_label = host_label
        self._client = httpx.Client(timeout=30)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _hostname_from_label(self, label_value: str) -> str:
        """Extract hostname from label value. 'mowgli:9100' -> 'mowgli'."""
        return label_value.split(":")[0] if ":" in label_value else label_value

    def discover_aps(self) -> list[APInfo]:
        """Discover APs from metric label values."""
        resp = self._client.get(
            f"{self._base_url}/api/v1/label/{self._host_label}/values",
            params={"match[]": "wifi_station_signal_dbm"},
        )
        resp.raise_for_status()
        values = resp.json()["data"]
        return [
            APInfo(
                hostname=self._hostname_from_label(v),
                instance=v,
            )
            for v in sorted(values)
        ]

    def fetch_rssi(
        self,
        start: datetime,
        end: datetime,
        macs: list[str] | None = None,
        step: str = "30s",
    ) -> list[RSSIReading]:
        """Fetch wifi_station_signal_dbm over time window."""
        query = "wifi_station_signal_dbm"
        if macs:
            mac_re = "|".join(macs)
            query = f'wifi_station_signal_dbm{{mac=~"{mac_re}"}}'

        resp = self._client.get(
            f"{self._base_url}/api/v1/query_range",
            params={
                "query": query,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "step": step,
            },
        )
        resp.raise_for_status()

        readings = []
        for series in resp.json()["data"]["result"]:
            metric = series["metric"]
            ap = self._hostname_from_label(metric.get(self._host_label, ""))
            mac = metric["mac"]
            ifname = metric["ifname"]
            for ts, val in series["values"]:
                readings.append(RSSIReading(
                    mac=mac, ap=ap, ifname=ifname,
                    rssi=int(float(val)), timestamp=int(ts),
                ))
        return readings

    def fetch_noise(
        self,
        start: datetime,
        end: datetime,
        step: str = "30s",
    ) -> list[NoiseReading]:
        """Fetch wifi_network_noise_dbm over time window."""
        resp = self._client.get(
            f"{self._base_url}/api/v1/query_range",
            params={
                "query": "wifi_network_noise_dbm",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "step": step,
            },
        )
        resp.raise_for_status()

        readings = []
        for series in resp.json()["data"]["result"]:
            metric = series["metric"]
            ap = self._hostname_from_label(metric.get(self._host_label, ""))
            radio = metric.get("device", "")
            freq = int(metric.get("frequency", "0"))
            for ts, val in series["values"]:
                readings.append(NoiseReading(
                    ap=ap, radio=radio, frequency=freq,
                    noise_dbm=int(float(val)), timestamp=int(ts),
                ))
        return readings

    def fetch_txpower(self) -> list[TxPowerReading]:
        """Fetch current txpower per radio from wifi_radio_txpower_dbm (instant query)."""
        # Fetch effective txpower
        resp = self._client.get(
            f"{self._base_url}/api/v1/query",
            params={"query": "wifi_radio_txpower_dbm"},
        )
        resp.raise_for_status()

        # Build configured txpower lookup: (ap, radio) -> configured value
        configured: dict[tuple[str, str], int] = {}
        try:
            resp_cfg = self._client.get(
                f"{self._base_url}/api/v1/query",
                params={"query": "wifi_radio_configured_txpower"},
            )
            resp_cfg.raise_for_status()
            for series in resp_cfg.json()["data"]["result"]:
                m = series["metric"]
                ap = self._hostname_from_label(m.get(self._host_label, ""))
                radio = m.get("device", "")
                configured[(ap, radio)] = int(float(series["value"][1]))
        except httpx.HTTPError as exc:
            logger.debug("configured txpower unavailable: %s", exc)

        # Fetch channel/frequency from wifi_radio_channel and wifi_radio_frequency_mhz
        channels: dict[tuple[str, str], int] = {}
        frequencies: dict[tuple[str, str], int] = {}
        for metric_name, target_dict in [
            ("wifi_radio_channel", channels),
            ("wifi_radio_frequency_mhz", frequencies),
        ]:
            try:
                r = self._client.get(
                    f"{self._base_url}/api/v1/query",
                    params={"query": metric_name},
                )
                r.raise_for_status()
                for series in r.json()["data"]["result"]:
                    m = series["metric"]
                    ap = self._hostname_from_label(m.get(self._host_label, ""))
                    radio = m.get("device", "")
                    target_dict[(ap, radio)] = int(float(series["value"][1]))
            except httpx.HTTPError as exc:
                logger.debug("%s unavailable: %s", metric_name, exc)

        readings = []
        for series in resp.json()["data"]["result"]:
            m = series["metric"]
            ap = self._hostname_from_label(m.get(self._host_label, ""))
            radio = m.get("device", "")
            ifname = m.get("ifname", "")
            txpower = int(float(series["value"][1]))
            readings.append(TxPowerReading(
                ap=ap,
                radio=radio,
                ifname=ifname,
                txpower_dbm=txpower,
                configured_txpower=configured.get((ap, radio)),
                channel=channels.get((ap, radio), 0),
                frequency_mhz=frequencies.get((ap, radio), 0),
                ssid=m.get("ssid", ""),
            ))

        return readings

    def fetch_ieee80211v_missing(self) -> list[str]:
        """Return AP hostnames where 802.11v is not enabled on all interfaces.

        Without 802.11v, usteer cannot send BSS Transition Management frames
        to gently steer clients.  Returns empty list if metric is unavailable.
        """
        try:
            resp = self._client.get(
                f"{self._base_url}/api/v1/query",
                params={"query": "wifi_iface_ieee80211v_enabled"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("ieee80211v metric unavailable: %s", exc)
            return []

        ap_has_disabled: set[str] = set()
        for series in resp.json()["data"]["result"]:
            m = series["metric"]
            ap = self._hostname_from_label(m.get(self._host_label, ""))
            if int(float(series["value"][1])) == 0:
                ap_has_disabled.add(ap)

        return sorted(ap_has_disabled)
