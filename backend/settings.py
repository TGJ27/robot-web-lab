from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .registry import RobotRegistry

DEFAULT_KEYMAP = {
    "passive": "1", "fix_stand": "2", "velocity": "3", "dance_default": "U",
    "enter_ll_debug": "0", "forward": "W", "backward": "S", "left": "A",
    "right": "D", "yaw_left": "Q", "yaw_right": "E",
    "hanger_attach": "ArrowLeft", "hanger_release": "ArrowRight",
    "hanger_raise": "ArrowUp", "hanger_lower": "ArrowDown", "reset": "R",
}


@dataclass
class AppSettings:
    theme: Literal["dark", "light"] = "light"
    active_robot: str | None = None
    ui_level: Literal["high", "low"] = "high"
    installed_robots: list[str] | None = None
    keymap: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.installed_robots is None:
            self.installed_robots = []
        if self.keymap is None:
            self.keymap = dict(DEFAULT_KEYMAP)
        else:
            # Legacy settings migration: the old generic "mimic" shortcut maps
            # to the built-in/default dance policy shortcut.
            if "dance_default" not in self.keymap and "mimic" in self.keymap:
                self.keymap["dance_default"] = self.keymap.pop("mimic")


class KeyConflictError(ValueError):
    def __init__(self, key: str, existing_action: str):
        super().__init__(f"Key {key!r} is already assigned to {existing_action}")
        self.key = key
        self.existing_action = existing_action


class SettingsStore:
    def __init__(self, path: Path, registry: RobotRegistry):
        self.path = Path(path)
        self.registry = registry

    def default_settings(self) -> AppSettings:
        return AppSettings()

    def load(self) -> AppSettings:
        if not self.path.exists():
            return self.default_settings()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        settings = AppSettings(**raw)
        if settings.active_robot is not None:
            self.registry.get(settings.active_robot)
        for robot_id in settings.installed_robots:
            self.registry.get(robot_id)
        return settings

    def save(self, settings: AppSettings) -> None:
        if settings.active_robot is not None:
            self.registry.get(settings.active_robot)
        for robot_id in settings.installed_robots:
            self.registry.get(robot_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True), encoding="utf-8")

    def remap_key(self, settings: AppSettings, action: str, new_key: str, *, resolution: Literal["reject", "replace", "swap"] = "reject") -> None:
        old_key = settings.keymap.get(action)
        existing_action = next((name for name, key in settings.keymap.items() if key == new_key and name != action), None)
        if existing_action is None:
            settings.keymap[action] = new_key
            return
        if resolution == "reject":
            raise KeyConflictError(new_key, existing_action)
        if resolution == "replace":
            del settings.keymap[existing_action]
            settings.keymap[action] = new_key
            return
        if resolution == "swap":
            settings.keymap[action] = new_key
            if old_key is None:
                del settings.keymap[existing_action]
            else:
                settings.keymap[existing_action] = old_key
            return
        raise ValueError(f"Unsupported resolution: {resolution}")
