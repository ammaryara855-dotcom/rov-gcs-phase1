import json
from pathlib import Path

from gcs.config_manager import ConfigManager
from gcs.events import EventBus


def test_config_loads_and_hot_reloads(tmp_path: Path):
    cfg_dir = tmp_path / "config"
    profiles_dir = cfg_dir / "profiles"
    profiles_dir.mkdir(parents=True)

    (cfg_dir / "settings.json").write_text(
        json.dumps({"poll_rate_hz": 50, "deadzone": 0.1, "active_profile": "default"}),
        encoding="utf-8",
    )
    (profiles_dir / "default.json").write_text(
        json.dumps({"name": "default", "axes": {"0": "surge"}, "buttons": {}, "keys": {}}),
        encoding="utf-8",
    )

    bus = EventBus()
    mgr = ConfigManager(cfg_dir, bus)
    assert mgr.get_deadzone() == 0.1

    # Modify file without restarting
    (cfg_dir / "settings.json").write_text(
        json.dumps({"poll_rate_hz": 100, "deadzone": 0.25, "active_profile": "default"}),
        encoding="utf-8",
    )
    mgr.reload()

    assert mgr.get_poll_rate_hz() == 100.0
    assert mgr.get_deadzone() == 0.25
    