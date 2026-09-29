from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil

from .registry import RobotRegistry


class UnsafePathError(ValueError):
    pass


def _safe_child(root: Path, relative: str | Path) -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise UnsafePathError(f"Path escapes managed root: {relative}")
    return candidate


def _safe_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise UnsafePathError(f"Unsafe filename: {name}")
    if name in {".", ".."}:
        raise UnsafePathError(f"Unsafe filename: {name}")
    return name


@dataclass(frozen=True)
class ExampleEntry:
    name: str
    relative_path: str
    language: str


CPP_LOWSTATE_TEMPLATE = r'''#include <iostream>
#include <thread>
#include <unitree/robot/channel/channel_subscriber.hpp>
#include <unitree/idl/hg/LowState_.hpp>

static const std::string LOWSTATE_TOPIC = "rt/lowstate";

int main(int argc, char** argv) {
    std::cout << "Robot Web Lab LowState template. Interface: "
              << (argc > 1 ? argv[1] : "lo") << std::endl;
    // Add your Unitree SDK2 subscriber here.
    return 0;
}
'''

PY_BLANK_TEMPLATE = '''#!/usr/bin/env python3\n\n# Robot Web Lab low-level Python example\nprint("Robot Web Lab example")\n'''
CPP_BLANK_TEMPLATE = '''#include <iostream>\n\nint main(int argc, char** argv) {\n    std::cout << "Robot Web Lab example" << std::endl;\n    return 0;\n}\n'''


class ExampleService:
    def __init__(self, sdk_root: Path, workspace_root: Path, registry: RobotRegistry, python_sdk_root: Path | None = None):
        self.sdk_root = Path(sdk_root)
        self.python_sdk_root = Path(python_sdk_root) if python_sdk_root else None
        self.workspace_root = Path(workspace_root)
        self.registry = registry

    def builtin_root(self, robot_id: str) -> Path:
        robot = self.registry.get(robot_id)
        return self.sdk_root / robot.sdk_example_path

    def _builtin_location(self, robot_id: str, relative_path: str) -> tuple[Path, str, tuple[str, ...] | None]:
        robot = self.registry.get(robot_id)
        if relative_path.startswith("python/"):
            if self.python_sdk_root is None or not robot.python_sdk_example_path:
                raise FileNotFoundError(relative_path)
            inner = relative_path[len("python/"):]
            return self.python_sdk_root / robot.python_sdk_example_path, inner, robot.python_sdk_example_files
        return self.builtin_root(robot_id), relative_path, robot.sdk_example_files

    @staticmethod
    def _is_source(path: Path) -> bool:
        return path.suffix.lower() in {".cpp", ".cc", ".cxx", ".py"}

    def _allowed_builtin(self, robot_id: str, relative_path: str) -> bool:
        robot = self.registry.get(robot_id)
        if not robot.supports_low_level:
            return False
        try:
            _root, inner, allowed = self._builtin_location(robot_id, relative_path)
        except FileNotFoundError:
            return False
        if allowed is None:
            return True
        return Path(inner).as_posix() in allowed

    def list_examples(self, robot_id: str) -> list[ExampleEntry]:
        robot = self.registry.get(robot_id)
        if not robot.supports_low_level:
            return []

        entries: list[ExampleEntry] = []
        cpp_root = self.builtin_root(robot_id)
        if cpp_root.exists():
            cpp_candidates = (
                sorted(cpp_root.rglob("*"))
                if robot.sdk_example_files is None
                else [cpp_root / relative for relative in robot.sdk_example_files]
            )
            for path in cpp_candidates:
                if path.is_file() and path.suffix.lower() in {".cpp", ".cc", ".cxx"}:
                    rel = path.relative_to(cpp_root).as_posix()
                    entries.append(ExampleEntry(path.stem, rel, "cpp"))

        if self.python_sdk_root is not None and robot.python_sdk_example_path:
            py_root = self.python_sdk_root / robot.python_sdk_example_path
            if py_root.exists():
                py_candidates = (
                    sorted(py_root.rglob("*.py"))
                    if robot.python_sdk_example_files is None
                    else [py_root / relative for relative in robot.python_sdk_example_files]
                )
                for path in py_candidates:
                    if path.is_file() and path.suffix.lower() == ".py":
                        rel = path.relative_to(py_root).as_posix()
                        entries.append(ExampleEntry(path.stem, f"python/{rel}", "python"))
        return entries

    def builtin_path(self, robot_id: str, relative_path: str) -> Path:
        root, inner, _allowed = self._builtin_location(robot_id, relative_path)
        path = _safe_child(root, inner)
        if not self._allowed_builtin(robot_id, relative_path) or not path.is_file() or not self._is_source(path):
            raise FileNotFoundError(relative_path)
        return path

    def read_builtin(self, robot_id: str, relative_path: str) -> str:
        return self.builtin_path(robot_id, relative_path).read_text(encoding="utf-8", errors="replace")

    def rename_workspace(self, robot_id: str, relative_path: str, new_name: str) -> Path:
        root = self.robot_workspace(robot_id)
        source = _safe_child(root, relative_path)
        if not source.is_file():
            raise FileNotFoundError(relative_path)
        _safe_name(new_name)
        suffix = source.suffix
        if Path(new_name).suffix:
            if Path(new_name).suffix.lower() != suffix.lower():
                raise UnsafePathError("Renamed source must keep its file extension")
            filename = new_name
        else:
            filename = new_name + suffix
        destination = _safe_child(source.parent, filename)
        if destination.exists():
            raise FileExistsError(filename)
        source.rename(destination)
        return destination

    def delete_workspace(self, robot_id: str, relative_path: str) -> bool:
        root = self.robot_workspace(robot_id)
        path = _safe_child(root, relative_path)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def robot_workspace(self, robot_id: str) -> Path:
        self.registry.get(robot_id)
        path = self.workspace_root / robot_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_workspace(self, robot_id: str) -> list[ExampleEntry]:
        root = self.robot_workspace(robot_id)
        entries: list[ExampleEntry] = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".cpp", ".cc", ".cxx", ".py"}:
                rel = path.relative_to(root).as_posix()
                entries.append(ExampleEntry(path.stem, rel, "python" if path.suffix == ".py" else "cpp"))
        return entries

    def read_workspace(self, robot_id: str, relative_path: str) -> str:
        root = self.robot_workspace(robot_id)
        path = _safe_child(root, relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        return path.read_text(encoding="utf-8", errors="replace")

    def save_workspace(self, robot_id: str, relative_path: str, content: str) -> Path:
        root = self.robot_workspace(robot_id)
        path = _safe_child(root, relative_path)
        if path.suffix.lower() not in {".cpp", ".cc", ".cxx", ".py"}:
            raise UnsafePathError("Unsupported workspace source extension")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def copy_to_workspace(self, robot_id: str, builtin_relative: str, destination_name: str) -> Path:
        _safe_name(destination_name)
        source = self.builtin_path(robot_id, builtin_relative)
        destination = _safe_child(self.robot_workspace(robot_id), destination_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    def create_example(self, robot_id: str, name: str, language: str, template: str) -> Path:
        _safe_name(name)
        if language not in {"cpp", "python"}:
            raise ValueError("language must be 'cpp' or 'python'")
        suffix = ".cpp" if language == "cpp" else ".py"
        filename = name if name.endswith(suffix) else name + suffix
        path = _safe_child(self.robot_workspace(robot_id), filename)
        if path.exists():
            raise FileExistsError(filename)
        if language == "cpp" and template == "lowstate":
            content = CPP_LOWSTATE_TEMPLATE
        elif language == "cpp":
            content = CPP_BLANK_TEMPLATE
        else:
            content = PY_BLANK_TEMPLATE
        path.write_text(content, encoding="utf-8")
        if language == "python":
            path.chmod(0o755)
        return path
