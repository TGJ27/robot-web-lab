from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


class BuildProfileError(ValueError):
    pass


class BuildProfileStore:
    """YAML-backed build profiles for built-in and workspace low-level sources.

    Filenames are only identifiers. Build behavior comes from the assigned
    profile, so copied/renamed files keep the same compiler/linker settings.
    """

    VERSION = 1

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(self._defaults())
        else:
            self._ensure_default_assignments()

    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "version": BuildProfileStore.VERSION,
            "profiles": {
                "cpp_default": {
                    "cxx_standard": 17,
                    "libraries": ["unitree_sdk2"],
                    "include_builtin_root": True,
                    "defines": {},
                },
                "g1_dual_arm": {
                    "inherits": "cpp_default",
                    "libraries": ["yaml-cpp"],
                    "defines": {"BLIB_DIR": "${SDK_EXAMPLE_ROOT}/behavior_lib/"},
                },
                "h2_dual_arm": {
                    "inherits": "cpp_default",
                    "libraries": ["yaml-cpp"],
                    "defines": {"H2_DUAL_ARM_BEHAVIOR_DIR": "${SDK_EXAMPLE_ROOT}/behavior_lib/"},
                },
                "terminations": {
                    "inherits": "cpp_default",
                    "find_packages": ["Boost REQUIRED COMPONENTS program_options"],
                    "libraries": ["Boost::program_options"],
                },
                "python_default": {"language": "python"},
            },
            "files": {
                "unitree_g1:builtin:g1_dual_arm_example.cpp": "g1_dual_arm",
                "unitree_g1_23dof:builtin:g1_dual_arm_example.cpp": "g1_dual_arm",
                "unitree_h2:builtin:h2_dual_arm_example.cpp": "h2_dual_arm",
                "unitree_g1:builtin:terminations.cpp": "terminations",
                "unitree_g1_23dof:builtin:terminations.cpp": "terminations",
                "unitree_h2:builtin:terminations.cpp": "terminations",
            },
        }

    def _ensure_default_assignments(self) -> None:
        data = self._read()
        defaults = self._defaults()
        changed = False
        for name, profile in defaults["profiles"].items():
            if name not in data["profiles"]:
                data["profiles"][name] = profile
                changed = True
        for key, profile in defaults["files"].items():
            if key not in data["files"]:
                data["files"][key] = profile
                changed = True
        if changed:
            self._write(data)

    def _read(self) -> dict[str, Any]:
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise BuildProfileError(f"Invalid build profile YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise BuildProfileError("Build profile YAML root must be a mapping")
        data.setdefault("version", self.VERSION)
        data.setdefault("profiles", {})
        data.setdefault("files", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def save_text(self, text: str) -> None:
        try:
            data = yaml.safe_load(text) or {}
        except Exception as exc:
            raise BuildProfileError(f"Invalid build profile YAML: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("profiles", {}), dict) or not isinstance(data.get("files", {}), dict):
            raise BuildProfileError("YAML must contain mapping sections: profiles and files")
        data.setdefault("version", self.VERSION)
        self._write(data)

    @staticmethod
    def _file_key(robot_id: str, kind: str, relative_path: str) -> str:
        return f"{robot_id}:{kind}:{Path(relative_path).as_posix()}"

    @staticmethod
    def builtin_profile_name(relative_path: str) -> str:
        return "python_default" if Path(relative_path).suffix.lower() == ".py" else "cpp_default"

    @staticmethod
    def detect_profile_name(path: Path) -> str:
        if path.suffix.lower() == ".py":
            return "python_default"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if "yaml-cpp/yaml.h" in text:
            if "H2_DUAL_ARM_BEHAVIOR_DIR" in text:
                return "h2_dual_arm"
            if "BLIB_DIR" in text or "behavior_lib" in text:
                return "g1_dual_arm"
        if "boost/program_options" in text:
            return "terminations"
        return "cpp_default"

    def assign_builtin(self, robot_id: str, relative_path: str) -> str:
        data = self._read()
        key = self._file_key(robot_id, "builtin", relative_path)
        profile = data["files"].get(key) or self.builtin_profile_name(relative_path)
        if key not in data["files"]:
            data["files"][key] = profile
            self._write(data)
        return profile

    def assign_workspace(self, robot_id: str, relative_path: str, source_path: Path | None = None, profile: str | None = None) -> str:
        data = self._read()
        key = self._file_key(robot_id, "workspace", relative_path)
        assigned = data["files"].get(key)
        if assigned:
            return assigned
        assigned = profile or self.detect_profile_name(source_path or Path(relative_path))
        data["files"][key] = assigned
        self._write(data)
        return assigned

    def inherit_copy(self, robot_id: str, builtin_relative: str, workspace_relative: str) -> str:
        profile = self.assign_builtin(robot_id, builtin_relative)
        return self.assign_workspace(robot_id, workspace_relative, profile=profile)

    def rename_workspace(self, robot_id: str, old_relative: str, new_relative: str) -> None:
        data = self._read()
        old_key = self._file_key(robot_id, "workspace", old_relative)
        new_key = self._file_key(robot_id, "workspace", new_relative)
        profile = data["files"].pop(old_key, None)
        if profile:
            data["files"][new_key] = profile
            self._write(data)

    def delete_workspace(self, robot_id: str, relative_path: str) -> None:
        data = self._read()
        key = self._file_key(robot_id, "workspace", relative_path)
        if data["files"].pop(key, None) is not None:
            self._write(data)

    def resolve_profile(self, robot_id: str, relative_path: str, *, builtin: bool, source_path: Path) -> dict[str, Any]:
        data = self._read()
        name = self.assign_builtin(robot_id, relative_path) if builtin else self.assign_workspace(robot_id, relative_path, source_path)
        profiles = data["profiles"]
        if name not in profiles:
            raise BuildProfileError(f"Unknown build profile: {name}")

        def merge(profile_name: str, seen: set[str]) -> dict[str, Any]:
            if profile_name in seen:
                raise BuildProfileError(f"Build profile inheritance cycle: {profile_name}")
            raw = deepcopy(profiles.get(profile_name) or {})
            parent = raw.pop("inherits", None)
            result: dict[str, Any] = {}
            if parent:
                result = merge(parent, seen | {profile_name})
            for key, value in raw.items():
                if key in {"libraries", "find_packages", "include_dirs"}:
                    result[key] = list(dict.fromkeys([*(result.get(key) or []), *(value or [])]))
                elif key == "defines":
                    result[key] = {**(result.get(key) or {}), **(value or {})}
                else:
                    result[key] = value
            return result

        profile = merge(name, set())
        profile["name"] = name
        return profile
