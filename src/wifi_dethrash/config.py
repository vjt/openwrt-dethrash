import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path("~/.config/wifi-dethrash/config.toml").expanduser()


@dataclass(frozen=True)
class Config:
    vm_url: str = ""
    vl_url: str = ""
    grafana_url: str = ""
    grafana_api_key: str = ""
    mesh_ssids: list[str] = field(default_factory=list)
    station_field: str = "station"
    station_ip_field: str = "station_ip"


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Load config from TOML file. Returns empty Config if file doesn't exist."""
    if not path.exists():
        return Config()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return Config(
        vm_url=data.get("vm_url", ""),
        vl_url=data.get("vl_url", ""),
        grafana_url=data.get("grafana_url", ""),
        grafana_api_key=data.get("grafana_api_key", ""),
        mesh_ssids=data.get("mesh_ssids", []),
        station_field=data.get("station_field", "station"),
        station_ip_field=data.get("station_ip_field", "station_ip"),
    )
