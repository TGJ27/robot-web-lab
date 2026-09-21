from pathlib import Path
import json

from backend.builds import BuildManager
from backend.registry import RobotRegistry


def test_build_manager_starts_with_zero_installed_robots(tmp_path: Path):
    manager = BuildManager(tmp_path / "build_state.json", RobotRegistry.default(), project_root=tmp_path)
    status = manager.status()
    assert status["installed_robots"] == []
    assert status["building"] is False


def test_mark_installed_persists_selected_packages(tmp_path: Path):
    path = tmp_path / "build_state.json"
    manager = BuildManager(path, RobotRegistry.default(), project_root=tmp_path)
    manager.mark_installed("unitree_g1", high_level=True, low_level=True)
    reloaded = BuildManager(path, RobotRegistry.default(), project_root=tmp_path)
    robot = reloaded.status()["robots"]["unitree_g1"]
    assert robot["installed"] is True
    assert robot["high_level"] is True
    assert robot["low_level"] is True
    assert reloaded.status()["installed_robots"] == ["unitree_g1"]


def test_build_request_rejects_unknown_or_unsupported_high_level(tmp_path: Path):
    manager = BuildManager(tmp_path / "build_state.json", RobotRegistry.default(), project_root=tmp_path)
    try:
        manager.validate_request([{"robot_id": "missing", "high_level": False, "low_level": True}])
        assert False, "unknown robot should fail"
    except ValueError:
        pass
    try:
        manager.validate_request([{"robot_id": "unitree_r1", "high_level": True, "low_level": True}])
        assert False, "R1 web high-level is intentionally unavailable"
    except ValueError:
        pass


def test_registry_defines_native_build_metadata():
    registry = RobotRegistry.default()
    g1 = registry.get("unitree_g1")
    assert g1.native_robot == "g1"
    assert g1.controller_dir == "deploy/robots/g1"
    assert g1.model_xml.endswith("scene_g1.xml")
    assert g1.supports_web_high_level is True
    assert registry.get("unitree_r1").supports_web_high_level is False

def test_r1_and_h2_use_pinned_unitree_mujoco_models_for_ll_simulation():
    registry=RobotRegistry.default()
    r1=registry.get('unitree_r1'); h2=registry.get('unitree_h2')
    assert r1.model_repo == 'unitree_mujoco' and r1.model_xml == 'unitree_robots/r1/scene.xml'
    assert h2.model_repo == 'unitree_mujoco' and h2.model_xml == 'unitree_robots/h2/scene.xml'
    assert h2.supports_low_level is True
