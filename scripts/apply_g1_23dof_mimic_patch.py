#!/usr/bin/env python3
"""Apply the validated G1 Mimic stability fixes to the G1 23DoF deploy controller."""
from __future__ import annotations

from pathlib import Path
import sys

root = Path(sys.argv[1]).expanduser().resolve()
mimic = root / "deploy/robots/g1_23dof/src/State_Mimic.cpp"
if not mimic.is_file():
    raise SystemExit(f"Missing G1 23DoF Mimic source: {mimic}")

text = mimic.read_text(encoding="utf-8")

# Initialize the alignment quaternion before any observation can consume it.
old = "static Eigen::Quaternionf init_quat;"
new = "static Eigen::Quaternionf init_quat = Eigen::Quaternionf::Identity();"
if new not in text:
    if old not in text:
        raise RuntimeError("G1 23DoF State_Mimic init_quat declaration changed upstream")
    text = text.replace(old, new, 1)

# Avoid holding an Eigen expression that references a temporary transpose.
old = (
    "    auto rot_ = (init_quat * ref_quat_w).conjugate() * real_quat_w;\n"
    "    auto rot = rot_.toRotationMatrix().transpose();\n"
)
new = (
    "    const Eigen::Quaternionf rot_ =\n"
    "        (init_quat * ref_quat_w).conjugate() * real_quat_w;\n"
    "    const Eigen::Matrix3f rot = rot_.toRotationMatrix().transpose();\n"
)
if new not in text:
    if old not in text:
        raise RuntimeError("G1 23DoF State_Mimic orientation block changed upstream")
    text = text.replace(old, new, 1)

# Establish the motion/robot yaw alignment before env->reset(), so the first
# observation sees a valid alignment instead of the default/uninitialized value.
align_marker = "init_quat = Eigen::Quaternionf(robot_yaw * ref_yaw.transpose());"
if align_marker not in text:
    old = "    motion = motion_; // set for specific motion\n    env->reset();\n"
    if old not in text:
        raise RuntimeError("G1 23DoF State_Mimic enter block changed upstream")
    new = (
        "    motion = motion_; // set for specific motion\n\n"
        "    env->robot->update();\n"
        "    motion->reset(env->robot->data, time_range_[0]);\n"
        "    {\n"
        "        const Eigen::Matrix3f ref_yaw =\n"
        "            isaaclab::yawQuaternion(motion->root_quaternion()).toRotationMatrix();\n"
        "        const Eigen::Matrix3f robot_yaw =\n"
        "            isaaclab::yawQuaternion(robot_quat_w(env.get())).toRotationMatrix();\n"
        "        init_quat = Eigen::Quaternionf(robot_yaw * ref_yaw.transpose());\n"
        "    }\n\n"
        "    env->reset();\n"
    )
    text = text.replace(old, new, 1)

old_thread = (
    "        motion->reset(env->robot->data, time_range_[0]);\n"
    "        auto ref_yaw = isaaclab::yawQuaternion(motion->root_quaternion()).toRotationMatrix();\n"
    "        auto robot_yaw = isaaclab::yawQuaternion(robot_quat_w(env.get())).toRotationMatrix();\n"
    "        init_quat = robot_yaw * ref_yaw.transpose();\n"
    "        env->reset();\n"
)
if old_thread in text:
    text = text.replace(old_thread, "        env->reset(); // init_quat is already valid\n", 1)

mimic.write_text(text, encoding="utf-8")

check = mimic.read_text(encoding="utf-8")
assert "static Eigen::Quaternionf init_quat = Eigen::Quaternionf::Identity();" in check
assert "const Eigen::Matrix3f rot = rot_.toRotationMatrix().transpose();" in check
assert align_marker in check
print("G1 23DoF Mimic stability patch ready.")
