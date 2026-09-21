from __future__ import annotations

from collections import deque
from pathlib import Path
import os
import signal
import sys
import subprocess
import threading
from typing import Callable

from .build_profiles import BuildProfileStore
from .examples import UnsafePathError
from .registry import RobotRegistry


class ControlOwnershipError(RuntimeError):
    pass


class ProcessBusyError(RuntimeError):
    pass


class LowLevelRunner:
    def __init__(self, workspace_root: Path, sdk_root: Path, owner: Callable[[], str], sdk_prefix: Path | None = None, registry: RobotRegistry | None = None, profile_store: BuildProfileStore | None = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.sdk_root = Path(sdk_root).resolve()
        self._owner = owner
        self.sdk_prefix = Path(sdk_prefix).resolve() if sdk_prefix else None
        self.registry = registry or RobotRegistry.default()
        self.profile_store = profile_store
        self._process: subprocess.Popen[str] | None = None
        self._active_source: Path | None = None
        self._active_robot_id: str | None = None
        self._logs: deque[str] = deque(maxlen=1000)
        self._lock = threading.Lock()
        self.runtime_dir = self.workspace_root.parent / 'run' / 'native'
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def _validate_source(self, source: Path) -> Path:
        source = Path(source).resolve()
        allowed = (
            source == self.workspace_root or self.workspace_root in source.parents or
            source == self.sdk_root or self.sdk_root in source.parents
        )
        if not allowed:
            raise UnsafePathError("Only managed workspace or approved SDK files can be executed")
        if not source.is_file():
            raise FileNotFoundError(source)
        return source

    def _require_low_owner(self) -> None:
        if self._owner() != "low":
            raise ControlOwnershipError("Switch to Low-Level Debug mode before running SDK code")

    def _robot_for_source(self, source: Path, robot_id: str | None = None):
        if robot_id:
            return self.registry.get(robot_id)
        if self.workspace_root in source.parents:
            relative = source.relative_to(self.workspace_root)
            if not relative.parts:
                raise UnsafePathError("Workspace source is not associated with a robot")
            aliases = {"g1":"unitree_g1","r1":"unitree_r1","go2":"unitree_go2","h1":"unitree_h1","h2":"unitree_h2","a2":"unitree_a2"}
            return self.registry.get(aliases.get(relative.parts[0], relative.parts[0]))
        for robot in self.registry.list():
            root = (self.sdk_root / robot.sdk_example_path).resolve()
            if root == source or root in source.parents:
                return robot
        raise UnsafePathError("SDK source is not associated with a known robot")

    def _is_builtin(self, source: Path) -> bool:
        return self.sdk_root in source.parents

    def _relative_for_profile(self, source: Path, robot_id: str) -> str:
        robot = self.registry.get(robot_id)
        if self._is_builtin(source):
            root = (self.sdk_root / robot.sdk_example_path).resolve()
            return source.relative_to(root).as_posix()
        root = self.workspace_root / robot_id
        if root.resolve() in source.parents:
            return source.relative_to(root.resolve()).as_posix()
        # compatibility aliases for older workspace folder names
        return source.name

    def binary_for(self, source: Path, robot_id: str | None = None) -> Path:
        source = self._validate_source(source)
        robot = self._robot_for_source(source, robot_id)
        if self._is_builtin(source):
            build_dir = self.workspace_root / ".build_builtin" / robot.id / source.stem
        else:
            try:
                rel = source.relative_to(self.workspace_root)
                bucket = rel.parts[0] if rel.parts else robot.id
            except ValueError:
                bucket = robot.id
            build_dir = self.workspace_root / ".build" / bucket / source.stem
        return build_dir / f"rwl_{source.stem}"

    def command_for(self, source: Path, interface: str = "lo", robot_id: str | None = None) -> list[str]:
        self._require_low_owner()
        source = self._validate_source(source)
        if source.suffix.lower() == ".py":
            return [sys.executable, str(source), interface]
        if source.suffix.lower() not in {".cpp", ".cc", ".cxx"}:
            raise ValueError("Unsupported source type")
        return [str(self.binary_for(source, robot_id)), interface]

    def cmake_project_for(self, source: Path, robot_id: str | None = None, relative_path: str | None = None, builtin: bool | None = None) -> str:
        source = self._validate_source(source)
        robot = self._robot_for_source(source, robot_id)
        robot_id = robot.id
        target = f"rwl_{source.stem}"
        builtin_low_root = (self.sdk_root / robot.sdk_example_path).resolve()
        is_builtin = self._is_builtin(source) if builtin is None else builtin
        relative_path = relative_path or self._relative_for_profile(source, robot_id)
        profile = None
        if self.profile_store:
            profile = self.profile_store.resolve_profile(robot_id, relative_path, builtin=is_builtin, source_path=source)
        profile = profile or {"name":"cpp_default","cxx_standard":17,"libraries":["unitree_sdk2"],"include_builtin_root":True,"defines":{}}

        lines = [
            "cmake_minimum_required(VERSION 3.16)",
            f"project({target} LANGUAGES CXX)",
            f"set(CMAKE_CXX_STANDARD {int(profile.get('cxx_standard',17))})",
        ]
        config = self.sdk_prefix / "lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake" if self.sdk_prefix else None
        if config and config.exists():
            lines += [f'list(PREPEND CMAKE_PREFIX_PATH "{self.sdk_prefix.as_posix()}")', "find_package(unitree_sdk2 REQUIRED)"]
        else:
            lines += ["set(BUILD_EXAMPLES OFF CACHE BOOL \"\" FORCE)", f'add_subdirectory("{self.sdk_root.as_posix()}" "${{CMAKE_BINARY_DIR}}/unitree_sdk2" EXCLUDE_FROM_ALL)']

        for package in profile.get("find_packages", []) or []:
            lines.append(f"find_package({package})")
        libraries = list(profile.get("libraries", []) or ["unitree_sdk2"])
        if "yaml-cpp" in libraries and not any("yaml-cpp" in p for p in profile.get("find_packages", []) or []):
            lines.append("find_package(yaml-cpp REQUIRED)")
        if any("Boost::" in lib for lib in libraries) and not any(str(p).startswith("Boost ") for p in profile.get("find_packages", []) or []):
            lines.append("find_package(Boost REQUIRED COMPONENTS program_options)")

        lines.append(f'add_executable({target} "{source.as_posix()}")')
        include_dirs = []
        if profile.get("include_builtin_root", True):
            include_dirs.append(builtin_low_root.as_posix())
        include_dirs.extend(profile.get("include_dirs", []) or [])
        if include_dirs:
            rendered = " ".join(f'"{str(x).replace("${SDK_EXAMPLE_ROOT}", builtin_low_root.as_posix())}"' for x in include_dirs)
            lines.append(f"target_include_directories({target} PRIVATE {rendered})")
        lines.append(f'target_link_libraries({target} PRIVATE {" ".join(libraries)})')

        defines = profile.get("defines", {}) or {}
        if defines:
            rendered=[]
            for key,value in defines.items():
                value=str(value).replace("${SDK_EXAMPLE_ROOT}", builtin_low_root.as_posix())
                rendered.append(f'{key}=\\"{value}\\"')
            lines.append(f'target_compile_definitions({target} PRIVATE {" ".join(rendered)})')
        return "\n".join(lines) + "\n"

    def build(self, source: Path, robot_id: str | None = None, relative_path: str | None = None, builtin: bool | None = None) -> tuple[bool, str]:
        source = self._validate_source(source)
        if source.suffix.lower() == ".py":
            result = subprocess.run([sys.executable, "-m", "py_compile", str(source)], text=True, capture_output=True)
            return result.returncode == 0, result.stdout + result.stderr
        binary = self.binary_for(source, robot_id)
        build_dir = binary.parent
        build_dir.mkdir(parents=True, exist_ok=True)
        cmake_file = build_dir / "CMakeLists.txt"
        cmake_file.write_text(self.cmake_project_for(source, robot_id=robot_id, relative_path=relative_path, builtin=builtin), encoding="utf-8")
        configure = subprocess.run(["cmake", "-S", str(build_dir), "-B", str(build_dir / "cmake")], text=True, capture_output=True)
        if configure.returncode != 0:
            return False, configure.stdout + configure.stderr
        build = subprocess.run(["cmake", "--build", str(build_dir / "cmake"), "--target", f"rwl_{source.stem}", "-j", str(max(1, os.cpu_count() or 1))], text=True, capture_output=True)
        built = build_dir / "cmake" / f"rwl_{source.stem}"
        if build.returncode == 0 and built.exists():
            binary.write_bytes(built.read_bytes()); binary.chmod(0o755)
        return build.returncode == 0, configure.stdout + configure.stderr + build.stdout + build.stderr

    def status(self, source: Path, robot_id: str | None = None) -> dict:
        source = self._validate_source(source)
        process = self._process
        running = process is not None and process.poll() is None and self._active_source == source
        return {"built": source.suffix.lower()==".py" or self.binary_for(source, robot_id).is_file(), "running": running, "pid": process.pid if running else None, "path": str(source)}

    def start(self, source: Path, interface: str = "lo", robot_id: str | None = None) -> int:
        source = self._validate_source(source)
        command = self.command_for(source, interface, robot_id)
        with self._lock:
            if self._process and self._process.poll() is None:
                raise ProcessBusyError("A low-level program is already running")
            self._active_source = source
            self._active_robot_id = robot_id
            self._process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True, bufsize=1)
            process = self._process
            (self.runtime_dir / 'll.pid').write_text(f'{process.pid}\n')
        threading.Thread(target=self._collect_output, args=(process,), daemon=True).start()
        return process.pid

    def _collect_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            self._logs.append(line.rstrip("\n"))
        try:
            process.wait(timeout=0.1)
        except Exception:
            pass
        try:
            pid_path=self.runtime_dir/'ll.pid'
            if pid_path.exists() and pid_path.read_text().strip()==str(process.pid): pid_path.unlink()
        except OSError:
            pass

    def stop(self) -> bool:
        with self._lock:
            process = self._process
            if process is None:
                return False
            if process.poll() is not None:
                try: process.wait(timeout=0)
                except Exception: pass
                self._process = None
                try: (self.runtime_dir/'ll.pid').unlink()
                except FileNotFoundError: pass
                return False
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=2)
        with self._lock:
            if self._process is process:
                self._process = None
        try: (self.runtime_dir/'ll.pid').unlink()
        except FileNotFoundError: pass
        return True

    def logs(self) -> list[str]:
        return list(self._logs)

    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None
