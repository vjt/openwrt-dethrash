from pathlib import Path

from wifi_dethrash.config import Config, load_config


def test_load_missing_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg == Config()


def test_load_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.toml"
    p.write_text("")
    cfg = load_config(p)
    assert cfg == Config()


def test_load_full_config(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text(
        'vm_url = "https://vm.example.com"\n'
        'vl_url = "https://vl.example.com"\n'
        'grafana_url = "https://grafana.example.com"\n'
        'grafana_api_key = "glsa_test"\n'
        'mesh_ssids = ["Mercury", "Saturn"]\n'
    )
    cfg = load_config(p)
    assert cfg.vm_url == "https://vm.example.com"
    assert cfg.vl_url == "https://vl.example.com"
    assert cfg.grafana_url == "https://grafana.example.com"
    assert cfg.grafana_api_key == "glsa_test"
    assert cfg.mesh_ssids == ["Mercury", "Saturn"]


def test_load_partial_config(tmp_path: Path) -> None:
    p = tmp_path / "partial.toml"
    p.write_text('vm_url = "https://vm.example.com"\n')
    cfg = load_config(p)
    assert cfg.vm_url == "https://vm.example.com"
    assert cfg.vl_url == ""
    assert cfg.mesh_ssids == []


def test_config_is_frozen(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('vm_url = "https://vm.example.com"\n')
    cfg = load_config(p)
    try:
        cfg.vm_url = "nope"  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass
