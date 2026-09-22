#!/usr/bin/env python3
"""Normalize pinned unitree_rl_mjlab deploy sources for deterministic C++17 builds.

The pinned upstream revision contains deploy controller projects that rely on
C++17 features (std::clamp, structured bindings, inline variables), while some
robot CMakeLists do not explicitly request C++17.  It also has two different
headers named param.h (simulate/src/param.h and deploy/include/param.h).  This
patch makes controller builds select the deploy header unambiguously.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).expanduser().resolve()

required = [
    root / "deploy/include/FSM/FSMState.h",
    root / "deploy/include/param.h",
    root / "deploy/include/isaaclab/envs/mdp/actions/joint_actions.h",
    root / "deploy/include/isaaclab/envs/mdp/observations/observations.h",
]
controller_dirs = ("g1", "g1_23dof", "go2", "h1_2", "a2", "r1")
required += [root / "deploy/robots" / name / "CMakeLists.txt" for name in controller_dirs]
missing = [p for p in required if not p.is_file()]
if missing:
    raise SystemExit("Not a compatible pinned unitree_rl_mjlab checkout; missing:\n  " + "\n  ".join(map(str, missing)))

changed: list[str] = []

def write(path: Path, text: str) -> None:
    old = path.read_text(encoding="utf-8")
    if old != text:
        path.write_text(text, encoding="utf-8")
        changed.append(path.relative_to(root).as_posix())

# There is another simulate/src/param.h in this repository.  FSMState.h is in
# deploy/include/FSM, so a relative include makes the intended deploy header
# deterministic regardless of CPATH/CMake include ordering.
fsm = root / "deploy/include/FSM/FSMState.h"
s = fsm.read_text(encoding="utf-8")
if '#include "../param.h"' not in s:
    s2, n = re.subn(r'^#include\s+["<]param\.h[">]\s*$', '#include "../param.h"', s, count=1, flags=re.MULTILINE)
    if n != 1:
        raise RuntimeError("FSMState.h param.h include layout changed upstream")
    s = s2
write(fsm, s)

# Upstream uses std::sort / std::clamp but currently relies on transitive
# includes. Add the standard header explicitly so the build is self-contained.
for path in [
    root / "deploy/include/param.h",
    root / "deploy/include/isaaclab/envs/mdp/actions/joint_actions.h",
    root / "deploy/include/isaaclab/envs/mdp/observations/observations.h",
]:
    s = path.read_text(encoding="utf-8")
    if "#include <algorithm>" not in s:
        if "#pragma once\n" not in s:
            raise RuntimeError(f"{path.name}: pragma once layout changed upstream")
        s = s.replace("#pragma once\n", "#pragma once\n\n#include <algorithm>\n", 1)
    write(path, s)

# All deploy controllers use C++17 features. Some upstream CMakeLists omit the
# language standard, which lets GCC fall back to gnu++14 on Ubuntu.
for name in controller_dirs:
    cmake = root / "deploy/robots" / name / "CMakeLists.txt"
    s = cmake.read_text(encoding="utf-8")
    if "set(CMAKE_CXX_STANDARD 17)" not in s:
        m = re.search(r'^project\([^\n]+\)\s*$', s, flags=re.MULTILINE)
        if not m:
            raise RuntimeError(f"{name}/CMakeLists.txt project() layout changed upstream")
        pos = m.end()
        s = s[:pos] + "\n\nset(CMAKE_CXX_STANDARD 17)" + s[pos:]
    if "set(CMAKE_CXX_STANDARD_REQUIRED ON)" not in s:
        s = s.replace("set(CMAKE_CXX_STANDARD 17)", "set(CMAKE_CXX_STANDARD 17)\nset(CMAKE_CXX_STANDARD_REQUIRED ON)", 1)
    write(cmake, s)

# Validate the two root causes directly.
assert '#include "../param.h"' in fsm.read_text(encoding="utf-8")
assert "parser_policy_dir" in (root / "deploy/include/param.h").read_text(encoding="utf-8")
for name in controller_dirs:
    cmake_text = (root / "deploy/robots" / name / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "set(CMAKE_CXX_STANDARD 17)" in cmake_text
    assert "set(CMAKE_CXX_STANDARD_REQUIRED ON)" in cmake_text

if changed:
    print("Patched rl_mjlab deploy compatibility:")
    for item in changed:
        print("  -", item)
else:
    print("rl_mjlab deploy compatibility already normalized.")
