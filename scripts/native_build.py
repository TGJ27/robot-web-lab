#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def event(robot_id: str, *, status: str, progress: int, stage: str, error: str | None = None) -> None:
    payload={"robot_id":robot_id,"status":status,"progress":int(progress),"stage":stage}
    if error: payload["error"]=error
    print("RWL_EVENT "+json.dumps(payload),flush=True)


def run(cmd:list[str], *, cwd:Path|None=None, env:dict[str,str]|None=None) -> None:
    print("$ "+" ".join(map(str,cmd)),flush=True)
    proc=subprocess.Popen(cmd,cwd=str(cwd) if cwd else None,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    assert proc.stdout is not None
    for line in proc.stdout: print(line.rstrip(),flush=True)
    code=proc.wait()
    if code: raise RuntimeError(f"command failed ({code}): {' '.join(cmd)}")



def build_low_level_examples(root: Path, sdk: Path, prefix: Path, robot_id: str) -> int:
    # Pre-build every simulator-compatible built-in LL example exposed for a robot.
    # SDK2 itself still uses BUILD_EXAMPLES=OFF; only Robot Web Lab's approved
    # per-robot examples are compiled here using the same path as the web IDE.
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

    from backend.build_profiles import BuildProfileStore
    from backend.examples import ExampleService
    from backend.registry import RobotRegistry
    from backend.runner import LowLevelRunner

    registry = RobotRegistry.default()
    robot = registry.get(robot_id)
    if not robot.supports_low_level:
        return 0

    workspace = root / "workspace" / "examples"
    profiles = BuildProfileStore(root / "workspace" / "build_profiles.yaml")
    examples = ExampleService(sdk, workspace, registry)
    runner = LowLevelRunner(
        workspace,
        sdk,
        owner=lambda: "low",
        sdk_prefix=prefix,
        registry=registry,
        profile_store=profiles,
    )

    entries = examples.list_examples(robot_id)
    if not entries:
        print(
            f"No simulator-compatible Low-Level examples exposed for {robot.display_name}.",
            flush=True,
        )
        return 0

    built = 0
    for entry in entries:
        source = examples.builtin_path(robot_id, entry.relative_path)
        print(f"[LL example] {robot.display_name}: {entry.relative_path}", flush=True)
        ok, output = runner.build(
            source,
            robot_id=robot_id,
            relative_path=entry.relative_path,
            builtin=True,
        )
        if output.strip():
            print(output.rstrip(), flush=True)
        if not ok:
            raise RuntimeError(
                f"Low-Level example failed to build for {robot.display_name}: "
                f"{entry.relative_path}"
            )
        built += 1

    print(f"Built {built} Low-Level example(s) for {robot.display_name}.", flush=True)
    return built

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--project-root",required=True); ap.add_argument("--request",required=True); ns=ap.parse_args()
    root=Path(ns.project_root).resolve(); items=json.loads(Path(ns.request).read_text()); ids=[i["robot_id"] for i in items]
    sdk=root/"third_party/unitree_sdk2"; rl=root/"third_party/unitree_rl_mjlab"; mujoco_models=root/"third_party/unitree_mujoco"; native=root/"build/native"; prefix=native/"prefix"
    jobs=str(max(1,min(16,os.cpu_count() or 1)))
    if not (sdk/"CMakeLists.txt").exists() or not (rl/"simulate/CMakeLists.txt").exists() or not (mujoco_models/"unitree_robots").exists():
        raise SystemExit("Pinned Unitree submodules are missing. Run ./scripts/bootstrap_submodules.sh")
    for rid in ids: event(rid,status="building",progress=4,stage="Checking native dependencies")

    # Build/install SDK2 core only. BUILD_EXAMPLES=OFF avoids the entire upstream example tree; selected Robot Web Lab LL examples are compiled per robot later.
    sdk_build=native/"sdk2-build"; sdk_config=prefix/"lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake"
    if not sdk_config.exists():
        for rid in ids: event(rid,status="building",progress=10,stage="Preparing Unitree SDK2 core (examples disabled)")
        run(["cmake","-S",str(sdk),"-B",str(sdk_build),"-DCMAKE_BUILD_TYPE=Release","-DBUILD_EXAMPLES=OFF",f"-DCMAKE_INSTALL_PREFIX={prefix}"])
        run(["cmake","--build",str(sdk_build),"-j",jobs])
        run(["cmake","--install",str(sdk_build)])
    else:
        print("Unitree SDK2 core already prepared; skipping.",flush=True)

    env=os.environ.copy(); lib=str(prefix/"lib"); inc=str(prefix/"include")
    env["CMAKE_PREFIX_PATH"]=f"{prefix}:{prefix/'lib/cmake'}:"+env.get("CMAKE_PREFIX_PATH","")
    # Keep native controller builds deterministic. In particular, rl_mjlab has
    # both simulate/src/param.h and deploy/include/param.h; inherited CPATH or
    # CPLUS_INCLUDE_PATH entries can make a controller pick the simulator header.
    env["CPATH"]=inc
    env.pop("CPLUS_INCLUDE_PATH",None)
    env.pop("C_INCLUDE_PATH",None)
    env["LIBRARY_PATH"]=lib+(":"+env["LIBRARY_PATH"] if env.get("LIBRARY_PATH") else "")
    env["LD_LIBRARY_PATH"]=lib+(":"+env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")

    # Normalize upstream deploy controller sources before any High-Level build.
    # The pinned revision uses C++17 features but some robot CMakeLists do not
    # request C++17, and it contains two different headers named param.h.
    if any(i.get("high_level") for i in items):
        run([sys.executable,str(root/"scripts/apply_rl_mjlab_compat_patch.py"),str(rl)])

    # G1 keeps its simulator keyboard/Mimic/hanger integration.  Other robots
    # do not need the G1-specific source edits.
    g1_hl=any(i["robot_id"]=="unitree_g1" and i.get("high_level") for i in items)
    if g1_hl:
        event("unitree_g1",status="building",progress=18,stage="Applying G1 simulator/Mimic integration")
        run([sys.executable,str(root/"scripts/apply_g1_patch.py"),str(rl)])

    g1_23_mimic=any(i["robot_id"]=="unitree_g1_23dof" and i.get("high_level") for i in items)
    if g1_23_mimic:
        event("unitree_g1_23dof",status="building",progress=19,stage="Applying G1 23DoF Mimic stability fixes")
        run([sys.executable,str(root/"scripts/apply_g1_23dof_mimic_patch.py"),str(rl)])

    # Every rl_mjlab High-Level controller gets the same controller-side web
    # joystick overlay.  This is what makes 1/2/3 + WASDQE from the browser
    # work for G1-23DoF, Go2, H1-2, A2 and R1 as well as G1.
    if any(i.get("high_level") for i in items):
        for item in items:
            if item.get("high_level"):
                event(item["robot_id"],status="building",progress=22,stage="Applying multi-robot web keyboard control")
        run([sys.executable,str(root/"scripts/apply_web_hl_patch.py"),str(rl)])

    # Robot-agnostic qpos bridge for the browser viewport.
    run([sys.executable,str(root/"scripts/apply_web_state_patch.py"),str(rl)])

    # One shared simulator binary supports the selected robot models. Never build the optional jstest target.
    sim_build=rl/"simulate/build"; sim_bin=sim_build/"rwl_mujoco_headless"
    for rid in ids: event(rid,status="building",progress=35,stage="Building/updating shared MuJoCo simulator")
    run(["cmake","-S",str(rl/"simulate"),"-B",str(sim_build),"-DCMAKE_BUILD_TYPE=Release",f"-DCMAKE_PREFIX_PATH={prefix};{prefix/'lib/cmake'}"],env=env)
    run(["cmake","--build",str(sim_build),"--target","rwl_mujoco_headless","-j",jobs],env=env)

    # Sanity-check the pinned deploy header before controller compilation. The
    # upstream State_RLBase.cpp files require param::parser_policy_dir().
    deploy_param=rl/"deploy/include/param.h"
    try:
        deploy_param_text=deploy_param.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Missing rl_mjlab deploy header: {deploy_param}") from exc
    if "parser_policy_dir" not in deploy_param_text:
        raise RuntimeError(
            "unitree_rl_mjlab tracked sources are stale/modified: deploy/include/param.h "
            "does not contain parser_policy_dir. Run: bash scripts/bootstrap_submodules.sh"
        )

    # Refuse to advertise/build a runnable HL pack when upstream did not ship
    # the trained policy assets required by that controller.  The upstream
    # CtrlFSM constructs every enabled state at startup, so a missing Velocity
    # or Mimic policy prevents the controller from reaching Passive at all.
    required_hl_assets={
        "unitree_g1": [
            "deploy/robots/g1/config/policy/velocity/v0/exported/policy.onnx",
            "deploy/robots/g1/config/policy/mimic/dance1_subject2/exported/policy.onnx",
            "deploy/robots/g1/config/policy/mimic/dance1_subject2/params/dance1_subject2.npz",
        ],
        "unitree_g1_23dof": [
            "deploy/robots/g1_23dof/config/policy/velocity/v0/exported/policy.onnx",
            "deploy/robots/g1_23dof/config/policy/mimic/dance1_subject2/exported/policy.onnx",
            "deploy/robots/g1_23dof/config/policy/mimic/dance1_subject2/params/dance1_subject2.npz",
        ],
        "unitree_go2": ["deploy/robots/go2/config/policy/velocity/v0/exported/policy.onnx"],
        "unitree_h1": ["deploy/robots/h1_2/config/policy/velocity/v0/exported/policy.onnx"],
        "unitree_a2": ["deploy/robots/a2/config/policy/velocity/v0/exported/policy.onnx"],
        "unitree_r1": ["deploy/robots/r1/config/policy/velocity/v0/exported/policy.onnx"],
    }
    for item in items:
        if not item.get("high_level"):
            continue
        missing=[rel for rel in required_hl_assets.get(item["robot_id"],[]) if not (rl/rel).is_file()]
        if missing:
            raise RuntimeError(
                f"{item['robot_id']} has an upstream HL controller/config, but no runnable trained policy bundle. Missing: "
                + ", ".join(missing)
            )

    # Build the selected upstream rl_mjlab controller target for each robot.
    # H2 is intentionally absent: the pinned rl_mjlab revision has no deploy/robots/h2 controller.
    controller_targets={
        "unitree_g1": ("g1", "g1_ctrl", "G1"),
        "unitree_g1_23dof": ("g1_23dof", "g1_ctrl", "G1 23DoF"),
        "unitree_go2": ("go2", "go2_ctrl", "Go2"),
        "unitree_h1": ("h1_2", "h1_2_ctrl", "H1-2"),
        "unitree_a2": ("a2", "a2_ctrl", "A2"),
        "unitree_r1": ("r1", "r1_ctrl", "R1"),
    }
    for item in items:
        rid=item["robot_id"]
        if item.get("high_level"):
            try:
                ctrl_dir,target,label=controller_targets[rid]
            except KeyError as exc:
                raise RuntimeError(f"No web High-Level controller target is configured for {rid}") from exc
            ctrl=rl/"deploy/robots"/ctrl_dir; build=ctrl/"build"
            event(rid,status="building",progress=58,stage=f"Configuring {label} high-level controller")
            # Explicitly put deploy/include first so "param.h" cannot resolve to
            # simulate/src/param.h or another environment-provided header.
            cxx=f"-I{rl/'deploy/include'} -I{prefix/'include'}"
            link=f"-L{prefix/'lib'} -Wl,-rpath,{prefix/'lib'}"
            run(["cmake","-S",str(ctrl),"-B",str(build),"-DCMAKE_BUILD_TYPE=Release","-DCMAKE_CXX_STANDARD=17","-DCMAKE_CXX_STANDARD_REQUIRED=ON",f"-DCMAKE_CXX_FLAGS={cxx}",f"-DCMAKE_EXE_LINKER_FLAGS={link}"],env=env)
            event(rid,status="building",progress=72,stage=f"Building {label} high-level controller")
            run(["cmake","--build",str(build),"--target",target,"-j",jobs],env=env)
            if not (build/target).exists(): raise RuntimeError(f"{target} binary was not produced")
        if item.get("low_level"):
            event(rid,status="building",progress=84,stage="Building Low-Level SDK examples")
            count=build_low_level_examples(root,sdk,prefix,rid)
            event(rid,status="building",progress=96,stage=f"Low-Level examples ready ({count} built)")
        event(rid,status="installed",progress=100,stage="Ready")
    print("Selective native build complete.",flush=True); return 0


if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr,flush=True); raise SystemExit(1)
