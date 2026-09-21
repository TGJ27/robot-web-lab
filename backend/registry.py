from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RobotDefinition:
    id: str
    display_name: str
    family: str
    sdk_example_path: str
    joint_count: int | None
    supports_high_level: bool
    supports_low_level: bool = True
    sdk_example_files: tuple[str, ...] | None = None
    native_robot: str | None = None
    controller_dir: str | None = None
    model_xml: str | None = None
    model_repo: str = "unitree_rl_mjlab"
    supports_web_high_level: bool = False
    supports_mimic: bool = False
    note: str = ""


class RobotRegistry:
    def __init__(self, robots: Iterable[RobotDefinition]):
        self._robots = {robot.id: robot for robot in robots}

    @classmethod
    def default(cls) -> "RobotRegistry":
        return cls([
            RobotDefinition(
                "unitree_g1", "Unitree G1", "humanoid", "example/g1/low_level", 29, True,
                native_robot="g1", controller_dir="deploy/robots/g1",
                model_xml="src/assets/robots/unitree_g1/xmls/scene_g1.xml",
                supports_web_high_level=True, supports_mimic=True,
                note="Full Robot Web Lab HL + LL integration.",
            ),
            RobotDefinition(
                "unitree_g1_23dof", "Unitree G1 23DoF", "humanoid", "example/g1/low_level", 23, True,
                native_robot="g1_23dof", controller_dir="deploy/robots/g1_23dof",
                model_xml="src/assets/robots/unitree_g1/xmls/scene_g1_23dof.xml",
                supports_web_high_level=False,
                note="Low-level web workflow; the upstream controller remains available for later integration.",
            ),
            RobotDefinition(
                "unitree_r1", "Unitree R1", "humanoid", "example/r1/low_level", 26, True,
                native_robot="r1", controller_dir="deploy/robots/r1",
                model_xml="unitree_robots/r1/scene.xml", model_repo="unitree_mujoco",
                supports_web_high_level=False,
                note="Low-level simulator workflow; the web High-Level adapter is not enabled.",
            ),
            RobotDefinition(
                "unitree_go2", "Unitree Go2", "quadruped", "example/go2", 12, True,
                sdk_example_files=("go2_low_level.cpp",), native_robot="go2",
                controller_dir="deploy/robots/go2",
                model_xml="src/assets/robots/unitree_go2/xmls/scene_go2.xml",
                supports_web_high_level=False,
                note="Only the simulator-compatible low-level SDK example is exposed.",
            ),
            RobotDefinition(
                "unitree_h1", "Unitree H1-2", "humanoid", "example/h1/low_level", None, True,
                native_robot="h1_2", controller_dir="deploy/robots/h1_2",
                model_xml="src/assets/robots/unitree_h1_2/xmls/scene_h1_2.xml",
                supports_web_high_level=False,
                note="H1-2 native deployment target from pinned unitree_rl_mjlab.",
            ),
            RobotDefinition(
                "unitree_a2", "Unitree A2", "quadruped", "example/a2", None, True,
                supports_low_level=False, sdk_example_files=(), native_robot="a2",
                controller_dir="deploy/robots/a2",
                model_xml="src/assets/robots/unitree_a2/xmls/scene_a2.xml",
                supports_web_high_level=False,
                note="No simulator-compatible SDK2 low-level example in the pinned SDK revision.",
            ),
            RobotDefinition(
                "unitree_h2", "Unitree H2", "humanoid", "example/h2/low_level", None, False,
                native_robot="h2", controller_dir=None, model_xml="unitree_robots/h2/scene.xml", model_repo="unitree_mujoco",
                supports_web_high_level=False,
                note="Low-level SDK + MuJoCo model from the pinned Unitree repositories.",
            ),
        ])

    def list(self) -> list[RobotDefinition]:
        return list(self._robots.values())

    def get(self, robot_id: str) -> RobotDefinition:
        try:
            return self._robots[robot_id]
        except KeyError as exc:
            raise KeyError(f"Unknown robot: {robot_id}") from exc
