import json
import logging
from pathlib import Path
import threading
from typing import Any

from gcs.events import Event, EventBus

logger = logging.getLogger("gcs.config")


class ConfigManager:
    """Loads settings and profiles from JSON, supports hot-reload without restart."""

    def __init__(self, config_dir: Path, event_bus: EventBus) -> None:
        self.config_dir = config_dir
        self.profiles_dir = config_dir / "profiles"
        self.settings_path = config_dir / "settings.json"
        self.event_bus = event_bus
        self._lock = threading.Lock()

        self.settings: dict[str, Any] = {}
        self.active_profile_name: str = "default"
        self.profile: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        """Reload settings and active profile from disk."""
        with self._lock:
            self.settings = self._read_json(self.settings_path)
            requested_profile = self.settings.get("active_profile", "default")
            self._load_profile_locked(requested_profile)

        logger.info(
            "Config loaded: rate=%sHz, deadzone=%.2f, profile='%s'",
            self.get_poll_rate_hz(),
            self.get_deadzone(),
            self.active_profile_name,
        )
        self.event_bus.publish(
            Event(
                name="config.reloaded",
                payload={
                    "profile": self.active_profile_name,
                    "poll_rate_hz": self.get_poll_rate_hz(),
                    "deadzone": self.get_deadzone(),
                },
            )
        )

    def select_profile(self, profile_name: str) -> None:
        """Switch to a named profile and save it to settings."""
        with self._lock:
            self._load_profile_locked(profile_name)
            self.settings["active_profile"] = self.active_profile_name
            self._write_json(self.settings_path, self.settings)

        logger.info("Switched active profile to '%s'", self.active_profile_name)
        self.event_bus.publish(
            Event(name="profile.changed", payload={"profile": self.active_profile_name})
        )

    def apply_profile_for_device(self, device_name: str) -> None:
        """Auto-load profile mapped to a recognized controller name."""
        with self._lock:
            device_map: dict[str, str] = self.settings.get("device_profiles", {})
            mapped_name = device_map.get(device_name)
            if not mapped_name or mapped_name == self.active_profile_name:
                return
            self._load_profile_locked(mapped_name)
            self.settings["active_profile"] = self.active_profile_name
            self._write_json(self.settings_path, self.settings)

        logger.info("Auto-loaded profile '%s' for device '%s'", mapped_name, device_name)
        self.event_bus.publish(
            Event(
                name="profile.auto_loaded",
                payload={"device": device_name, "profile": mapped_name},
            )
        )

    def get_poll_rate_hz(self) -> float:
        with self._lock:
            return float(self.settings.get("poll_rate_hz", 50))

    def get_deadzone(self) -> float:
        with self._lock:
            return float(self.settings.get("deadzone", 0.1))

    def get_profile(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self.profile))

    def _load_profile_locked(self, profile_name: str) -> None:
        profile_path = self.profiles_dir / f"{profile_name}.json"
        if not profile_path.exists():
            logger.warning("Profile '%s' not found; falling back to 'default'", profile_name)
            profile_name = "default"
            profile_path = self.profiles_dir / "default.json"
        self.profile = self._read_json(profile_path)
        self.active_profile_name = profile_name

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            