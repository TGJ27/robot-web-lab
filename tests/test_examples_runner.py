from pathlib import Path

import pytest

from backend.examples import ExampleService, UnsafePathError
from backend.registry import RobotRegistry
from backend.runner import LowLevelRunner, ControlOwnershipError


def make_sdk(tmp_path: Path) -> Path:
    sdk = tmp_path / "unitree_sdk2"
    source = sdk / "example/g1/low_level/g1_test.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main(){return 0;}\n", encoding="utf-8")
    return sdk


def test_discovery_gracefully_returns_empty_when_submodule_missing(tmp_path: Path):
    service = ExampleService(tmp_path / "missing", tmp_path / "workspace", RobotRegistry.default())
    assert service.list_examples("unitree_g1") == []


def test_discover_read_and_copy_builtin_example(tmp_path: Path):
    sdk = make_sdk(tmp_path)
    workspace = tmp_path / "workspace"
    service = ExampleService(sdk, workspace, RobotRegistry.default())
    examples = service.list_examples("unitree_g1")
    assert [item.relative_path for item in examples] == ["g1_test.cpp"]
    assert service.read_builtin("unitree_g1", "g1_test.cpp").startswith("int main")

    copied = service.copy_to_workspace("unitree_g1", "g1_test.cpp", "my_g1_test.cpp")
    assert copied == workspace / "unitree_g1" / "my_g1_test.cpp"
    assert copied.read_text() == "int main(){return 0;}\n"


def test_path_traversal_is_rejected(tmp_path: Path):
    sdk = make_sdk(tmp_path)
    service = ExampleService(sdk, tmp_path / "workspace", RobotRegistry.default())
    with pytest.raises(UnsafePathError):
        service.read_builtin("unitree_g1", "../../../../etc/passwd")
    with pytest.raises(UnsafePathError):
        service.create_example("unitree_g1", "../escape", "cpp", "blank")


def test_create_new_examples_from_templates(tmp_path: Path):
    service = ExampleService(tmp_path / "missing", tmp_path / "workspace", RobotRegistry.default())
    cpp = service.create_example("unitree_g1", "motor_test", "cpp", "lowstate")
    py = service.create_example("unitree_g1", "imu_test", "python", "blank")
    assert cpp.name == "motor_test.cpp"
    assert "rt/lowstate" in cpp.read_text()
    assert py.name == "imu_test.py"
    assert py.read_text().startswith("#!/usr/bin/env python3")



def test_r1_discovers_only_low_level_directory(tmp_path: Path):
    sdk = tmp_path / "unitree_sdk2"
    low = sdk / "example/r1/low_level/r1_ankle_swing_example.cpp"
    high = sdk / "example/r1/high_level/r1_arm_action_example.cpp"
    low.parent.mkdir(parents=True)
    high.parent.mkdir(parents=True)
    low.write_text("// low level\n", encoding="utf-8")
    high.write_text("// high level\n", encoding="utf-8")

    service = ExampleService(sdk, tmp_path / "workspace", RobotRegistry.default())
    examples = service.list_examples("unitree_r1")
    assert [item.relative_path for item in examples] == ["r1_ankle_swing_example.cpp"]


def test_go2_only_exposes_explicit_low_level_example(tmp_path: Path):
    sdk = tmp_path / "unitree_sdk2"
    root = sdk / "example/go2"
    root.mkdir(parents=True)
    (root / "go2_low_level.cpp").write_text("// lowcmd lowstate\n", encoding="utf-8")
    (root / "go2_sport_client.cpp").write_text("// high-level sport client\n", encoding="utf-8")
    (root / "go2_stand_example.cpp").write_text("// requires motion service\n", encoding="utf-8")

    service = ExampleService(sdk, tmp_path / "workspace", RobotRegistry.default())
    examples = service.list_examples("unitree_go2")
    assert [item.relative_path for item in examples] == ["go2_low_level.cpp"]

    with pytest.raises(FileNotFoundError):
        service.read_builtin("unitree_go2", "go2_sport_client.cpp")
    with pytest.raises(FileNotFoundError):
        service.copy_to_workspace("unitree_go2", "go2_sport_client.cpp", "sport.cpp")


def test_robot_without_sim_compatible_low_level_examples_lists_none(tmp_path: Path):
    sdk = tmp_path / "unitree_sdk2"
    root = sdk / "example/a2"
    (root / "sport").mkdir(parents=True)
    (root / "sport/a2_sport_client.cpp").write_text("// high level\n", encoding="utf-8")

    service = ExampleService(sdk, tmp_path / "workspace", RobotRegistry.default())
    assert service.list_examples("unitree_a2") == []

def test_runner_rejects_run_when_high_level_owns_control(tmp_path: Path):
    workspace = tmp_path / "workspace"
    source = workspace / "unitree_g1/test.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('ok')\n")
    runner = LowLevelRunner(workspace, tmp_path / "sdk", owner=lambda: "high")
    with pytest.raises(ControlOwnershipError):
        runner.command_for(source)


def test_runner_builds_safe_commands_in_low_level_mode(tmp_path: Path):
    workspace = tmp_path / "workspace"
    py = workspace / "unitree_g1/test.py"
    cpp = workspace / "unitree_g1/test.cpp"
    py.parent.mkdir(parents=True)
    py.write_text("print('ok')\n")
    cpp.write_text("int main(){return 0;}\n")
    runner = LowLevelRunner(workspace, tmp_path / "sdk", owner=lambda: "low")

    import sys
    assert runner.command_for(py) == [sys.executable, str(py), "lo"]
    command = runner.command_for(cpp)
    assert command[0].endswith("rwl_test")
    assert command[-1] == "lo"
    assert ".." not in " ".join(command)

    with pytest.raises(UnsafePathError):
        runner.command_for(tmp_path / "outside.py")

def test_python_build_is_allowed_while_high_level_owns_control(tmp_path: Path):
    workspace = tmp_path / "workspace"
    source = workspace / "unitree_g1/check.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('syntax ok')\n")
    runner = LowLevelRunner(workspace, tmp_path / "sdk", owner=lambda: "high")
    ok, output = runner.build(source)
    assert ok is True


def test_runner_status_reports_built_and_active_source(tmp_path: Path):
    from backend.runner import LowLevelRunner
    workspace = tmp_path / "workspace"
    sdk = tmp_path / "sdk"
    source = workspace / "g1" / "demo.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main(){return 0;}\n")
    runner = LowLevelRunner(workspace, sdk, owner=lambda: "low")
    status = runner.status(source)
    assert status == {"built": False, "running": False, "pid": None, "path": str(source)}
    binary = runner.binary_for(source)
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("binary")
    status = runner.status(source)
    assert status["built"] is True
    assert status["running"] is False
