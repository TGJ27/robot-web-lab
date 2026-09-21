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


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--project-root",required=True); ap.add_argument("--request",required=True); ns=ap.parse_args()
    root=Path(ns.project_root).resolve(); items=json.loads(Path(ns.request).read_text()); ids=[i["robot_id"] for i in items]
    sdk=root/"third_party/unitree_sdk2"; rl=root/"third_party/unitree_rl_mjlab"; mujoco_models=root/"third_party/unitree_mujoco"; native=root/"build/native"; prefix=native/"prefix"
    jobs=str(max(1,min(16,os.cpu_count() or 1)))
    if not (sdk/"CMakeLists.txt").exists() or not (rl/"simulate/CMakeLists.txt").exists() or not (mujoco_models/"unitree_robots").exists():
        raise SystemExit("Pinned Unitree submodules are missing. Run ./scripts/bootstrap_submodules.sh")
    for rid in ids: event(rid,status="building",progress=4,stage="Checking native dependencies")

    # Build/install SDK2 core only. BUILD_EXAMPLES=OFF is deliberate: LL examples compile on demand in the web IDE.
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
    env["CPATH"]=inc+(":"+env["CPATH"] if env.get("CPATH") else "")
    env["LIBRARY_PATH"]=lib+(":"+env["LIBRARY_PATH"] if env.get("LIBRARY_PATH") else "")
    env["LD_LIBRARY_PATH"]=lib+(":"+env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")

    # Apply the proven G1 keyboard/LL/Mimic/hanger patch only when the G1 HL pack is requested.
    g1_hl=any(i["robot_id"]=="unitree_g1" and i.get("high_level") for i in items)
    if g1_hl:
        event("unitree_g1",status="building",progress=20,stage="Applying validated G1 HL/LL + Mimic fixes")
        run([sys.executable,str(root/"scripts/apply_g1_patch.py"),str(rl)])

    # Robot-agnostic qpos bridge for the browser viewport.
    run([sys.executable,str(root/"scripts/apply_web_state_patch.py"),str(rl)])

    # One shared simulator binary supports the selected robot models. Never build the optional jstest target.
    sim_build=rl/"simulate/build"; sim_bin=sim_build/"rwl_mujoco_headless"
    for rid in ids: event(rid,status="building",progress=35,stage="Building/updating shared MuJoCo simulator")
    run(["cmake","-S",str(rl/"simulate"),"-B",str(sim_build),"-DCMAKE_BUILD_TYPE=Release",f"-DCMAKE_PREFIX_PATH={prefix};{prefix/'lib/cmake'}"],env=env)
    run(["cmake","--build",str(sim_build),"--target","rwl_mujoco_headless","-j",jobs],env=env)

    # Build only web-enabled selected HL controllers. That is intentionally G1 only in the current integration.
    for item in items:
        rid=item["robot_id"]
        if item.get("high_level"):
            if rid!="unitree_g1": raise RuntimeError(f"Web HL controller is not enabled for {rid}")
            ctrl=rl/"deploy/robots/g1"; build=ctrl/"build"
            event(rid,status="building",progress=58,stage="Configuring G1 high-level controller")
            cxx=f"-I{prefix/'include'}"
            link=f"-L{prefix/'lib'} -Wl,-rpath,{prefix/'lib'}"
            run(["cmake","-S",str(ctrl),"-B",str(build),"-DCMAKE_BUILD_TYPE=Release",f"-DCMAKE_CXX_FLAGS={cxx}",f"-DCMAKE_EXE_LINKER_FLAGS={link}"],env=env)
            event(rid,status="building",progress=72,stage="Building G1 high-level controller")
            run(["cmake","--build",str(build),"--target","g1_ctrl","-j",jobs],env=env)
            if not (build/"g1_ctrl").exists(): raise RuntimeError("g1_ctrl binary was not produced")
        if item.get("low_level"):
            event(rid,status="building",progress=86,stage="Registering low-level SDK pack (examples build on demand)")
        event(rid,status="installed",progress=100,stage="Ready")
    print("Selective native build complete.",flush=True); return 0


if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr,flush=True); raise SystemExit(1)
