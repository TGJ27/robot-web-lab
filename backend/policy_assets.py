from __future__ import annotations

from pathlib import Path

from .registry import RobotDefinition


def _rl_root(project_root: Path) -> Path:
    return Path(project_root).resolve() / "third_party" / "unitree_rl_mjlab"


def high_level_required_assets(project_root: Path, robot: RobotDefinition) -> list[Path]:
    root = _rl_root(project_root)
    required: list[Path] = []
    if robot.velocity_policy_rel:
        required.append(root / robot.velocity_policy_rel)
    if robot.mimic_policy_rel:
        required.append(root / robot.mimic_policy_rel)
    if robot.mimic_motion_rel:
        required.append(root / robot.mimic_motion_rel)
    return required


def missing_high_level_assets(project_root: Path, robot: RobotDefinition) -> list[Path]:
    return [path for path in high_level_required_assets(project_root, robot) if not path.is_file()]


def policy_status(project_root: Path, robot: RobotDefinition) -> dict:
    root = _rl_root(project_root)
    velocity_ready = bool(robot.velocity_policy_rel and (root / robot.velocity_policy_rel).is_file())
    mimic_required = [rel for rel in (robot.mimic_policy_rel, robot.mimic_motion_rel) if rel]
    mimic_ready = bool(mimic_required) and all((root / rel).is_file() for rel in mimic_required)
    missing = [path.relative_to(root).as_posix() for path in missing_high_level_assets(project_root, robot)]
    high_level_ready = bool(robot.supports_web_high_level and not missing)
    return {
        "high_level_ready": high_level_ready,
        "velocity_policy_ready": velocity_ready,
        "mimic_ready": bool(robot.supports_mimic and mimic_ready),
        "missing_high_level_assets": missing,
    }
