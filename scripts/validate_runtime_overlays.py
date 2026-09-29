#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


PROJECT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
RL = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else PROJECT / "third_party" / "unitree_rl_mjlab"

errors: list[str] = []
warnings: list[str] = []


def require(cond: bool, message: str) -> None:
    if not cond:
        errors.append(message)


def read(path: Path) -> str:
    if not path.is_file():
        errors.append(f"missing file: {path}")
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


# 1) Patch-source sanity.
bad_raw_single = "r" + "'''" + "\\n"
bad_raw_double = "r" + '"' * 3 + "\\n"
for script in sorted((PROJECT / "scripts").glob("apply_*.py")):
    source = read(script)
    if bad_raw_single in source or bad_raw_double in source:
        errors.append(
            f"{script.relative_to(PROJECT)} contains a raw-string literal \\n "
            "immediately after the opening quotes"
        )

# 2) Shared deploy headers used by all rl_mjlab high-level controllers.
ctrl = RL / "deploy" / "include" / "FSM" / "CtrlFSM.h"
ctrl_text = read(ctrl)
if ctrl_text:
    bad_lines = [i + 1 for i, line in enumerate(ctrl_text.splitlines()) if line.strip() == r"\n"]
    require(not bad_lines, f"CtrlFSM.h contains literal \\n source line(s): {bad_lines}")
    require(
        ctrl_text.count("inline void rwl_write_fsm_state(const std::string& state)") == 1,
        "CtrlFSM.h must contain exactly one generic rwl_write_fsm_state() helper",
    )
    require(
        ctrl_text.count("rwl_write_fsm_state(currentState->getStateString());") >= 2,
        "CtrlFSM.h must publish both initial and transitioned FSM states",
    )
    require(
        'std::getenv("RWL_SIM_RUNTIME_DIR")' in ctrl_text,
        "CtrlFSM.h generic state writer must use RWL_SIM_RUNTIME_DIR",
    )

fsm = RL / "deploy" / "include" / "FSM" / "FSMState.h"
fsm_text = read(fsm)
if fsm_text:
    require(
        "rwl_web_control::apply(lowstate->joystick);" in fsm_text,
        "FSMState.h is missing Robot Web Lab web-control application",
    )
    require(
        'std::getenv("RWL_SIM_RUNTIME_DIR")' in fsm_text,
        "FSMState.h web-control bridge must use RWL_SIM_RUNTIME_DIR",
    )
    require(
        '#include "../param.h"' in fsm_text,
        "FSMState.h must resolve the deploy param.h explicitly",
    )

param_h = RL / "deploy" / "include" / "param.h"
param_text = read(param_h)
if param_text:
    require("parser_policy_dir" in param_text, "deploy/include/param.h is missing parser_policy_dir()")

# 3) Every high-level controller shipped by the pinned rl_mjlab revision.
controllers = {
    "g1": "g1_ctrl",
    "g1_23dof": "g1_ctrl",
    "go2": "go2_ctrl",
    "h1_2": "h1_2_ctrl",
    "a2": "a2_ctrl",
    "r1": "r1_ctrl",
}
for directory, target in controllers.items():
    cmake = RL / "deploy" / "robots" / directory / "CMakeLists.txt"
    cmake_text = read(cmake)
    if not cmake_text:
        continue
    require("set(CMAKE_CXX_STANDARD 17)" in cmake_text, f"{directory}: C++17 is not enabled")
    require(
        "set(CMAKE_CXX_STANDARD_REQUIRED ON)" in cmake_text,
        f"{directory}: C++17 is not marked required",
    )
    require(
        re.search(rf"add_executable\(\s*{re.escape(target)}(?:\s|\))", cmake_text) is not None,
        f"{directory}: expected controller target {target} not found",
    )

# 4) Headless simulator generated source.
headless = RL / "simulate" / "src" / "rwl_headless_main.cc"
if headless.is_file():
    h = read(headless)
    literal_decl = r"void reset_to_initial_pose(mjModel* m, mjData* d);\n\n"
    require(literal_decl not in h, "rwl_headless_main.cc contains literal \\n declaration text")
    helper = "void reset_to_initial_pose(mjModel* m, mjData* d) {"
    poll = "void poll_runtime(mjModel* m, mjData* d, ElasticBand& band) {"
    hp = h.find(helper)
    pp = h.find(poll)
    require(0 <= hp < pp, "headless reset_to_initial_pose() must be defined before poll_runtime()")
    require(
        "mj_resetDataKeyframe(m,d,home_key)" in h,
        "headless simulator is missing MJCF home-keyframe reset support",
    )
    require(
        h.count("reset_to_initial_pose(m,d);") >= 2,
        "headless simulator must use initial-pose reset at startup and browser Reset",
    )

# 5) Robot registry + model/controller structure.
sys.path.insert(0, str(PROJECT))
try:
    from backend.registry import RobotRegistry
except Exception as exc:
    errors.append(f"could not import RobotRegistry: {exc}")
else:
    registry = RobotRegistry.default()
    expected_hl = {
        "unitree_g1": ("g1", "deploy/robots/g1"),
        "unitree_g1_23dof": ("g1_23dof", "deploy/robots/g1_23dof"),
        "unitree_go2": ("go2", "deploy/robots/go2"),
        "unitree_h1": ("h1_2", "deploy/robots/h1_2"),
        "unitree_a2": ("a2", "deploy/robots/a2"),
        "unitree_r1": ("r1", "deploy/robots/r1"),
    }

    for robot_id, (native_robot, controller_dir) in expected_hl.items():
        robot = registry.get(robot_id)
        require(robot.supports_web_high_level, f"{robot_id}: web high-level unexpectedly disabled")
        require(robot.native_robot == native_robot, f"{robot_id}: native_robot mismatch")
        require(robot.controller_dir == controller_dir, f"{robot_id}: controller_dir mismatch")
        require((RL / controller_dir).is_dir(), f"{robot_id}: controller directory missing")

        if robot.model_xml:
            repo_root = RL if robot.model_repo == "unitree_rl_mjlab" else PROJECT / "third_party" / robot.model_repo
            require((repo_root / robot.model_xml).is_file(), f"{robot_id}: model XML missing: {robot.model_xml}")

        for label, rel in (
            ("velocity", robot.velocity_policy_rel),
            ("mimic", robot.mimic_policy_rel),
            ("mimic motion", robot.mimic_motion_rel),
        ):
            if rel and not (RL / rel).is_file():
                warnings.append(f"{robot.display_name}: {label} asset not bundled: {rel}")

    h2 = registry.get("unitree_h2")
    require(not h2.supports_web_high_level, "Unitree H2 should not advertise web high-level control")
    require(h2.controller_dir is None, "Unitree H2 should not have an rl_mjlab controller directory")
    if h2.model_xml:
        repo_root = PROJECT / "third_party" / h2.model_repo
        require((repo_root / h2.model_xml).is_file(), f"Unitree H2 model XML missing: {h2.model_xml}")

if errors:
    print("Robot Web Lab runtime validation FAILED:", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)

print("Robot Web Lab runtime validation passed.")
print("  HL controller structure: G1, G1 23DoF, Go2, H1-2, A2, R1")
print("  H2: model/low-level only (no pinned rl_mjlab HL controller)")
if warnings:
    print("Known upstream asset limitations:")
    for item in warnings:
        print(f"  - {item}")
