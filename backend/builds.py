from __future__ import annotations

import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

from .registry import RobotRegistry


class BuildBusyError(RuntimeError):
    pass


class BuildManager:
    """Persist and supervise selective native robot builds.

    The Unitree sources stay intact. Selectivity is achieved by building the shared
    SDK/simulator once, compiling only selected controller targets, and compiling
    low-level SDK examples on demand from the LL editor.
    """
    def __init__(self, path: Path, registry: RobotRegistry, *, project_root: Path):
        self.path=Path(path); self.registry=registry; self.project_root=Path(project_root).resolve()
        self._lock=threading.RLock(); self._process: subprocess.Popen[str] | None=None
        self.runtime_dir=self.project_root/'run/native'; self.runtime_dir.mkdir(parents=True,exist_ok=True)
        self._state=self._load()

    def _empty_robot(self)->dict[str,Any]:
        return {"installed":False,"high_level":False,"low_level":False,"status":"not_built","progress":0,"stage":"Not built","error":None}
    def _default(self)->dict[str,Any]:
        return {"building":False,"current":None,"log":[],"robots":{r.id:self._empty_robot() for r in self.registry.list()}}
    def _load(self)->dict[str,Any]:
        if not self.path.exists(): return self._default()
        try: raw=json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError,OSError): return self._default()
        base=self._default(); base.update({k:v for k,v in raw.items() if k!="robots"})
        for rid,val in raw.get("robots",{}).items():
            if rid in base["robots"]: base["robots"][rid].update(val)
        # A crashed server cannot still own an in-memory builder.
        base["building"]=False; base["current"]=None
        return base
    def _save(self)->None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(self._state,indent=2,sort_keys=True),encoding="utf-8"); tmp.replace(self.path)
    def status(self)->dict[str,Any]:
        with self._lock:
            payload=json.loads(json.dumps(self._state))
            payload["installed_robots"]=[rid for rid,info in payload["robots"].items() if info["installed"]]
            return payload
    def mark_installed(self,robot_id:str,*,high_level:bool,low_level:bool)->None:
        self.registry.get(robot_id)
        with self._lock:
            info=self._state["robots"][robot_id]; info.update(installed=True,high_level=bool(high_level),low_level=bool(low_level),status="installed",progress=100,stage="Ready",error=None); self._save()
    def validate_request(self,items:list[dict[str,Any]])->list[dict[str,Any]]:
        if not items: raise ValueError("Select at least one robot")
        clean=[]; seen=set()
        for item in items:
            rid=str(item.get("robot_id",""))
            try: robot=self.registry.get(rid)
            except KeyError as exc: raise ValueError(str(exc)) from exc
            if rid in seen: continue
            seen.add(rid); high=bool(item.get("high_level",False)); low=bool(item.get("low_level",False))
            if not high and not low: raise ValueError(f"Select at least one package for {robot.display_name}")
            if high and not robot.supports_web_high_level: raise ValueError(f"{robot.display_name} High-Level web control is not enabled in this release")
            if low and not robot.supports_low_level: raise ValueError(f"{robot.display_name} has no compatible low-level SDK pack in this pinned revision")
            if not robot.model_xml: raise ValueError(f"{robot.display_name} has no supported simulation model in this pinned revision")
            clean.append({"robot_id":rid,"high_level":high,"low_level":low})
        return clean
    def start(self,items:list[dict[str,Any]])->dict[str,Any]:
        items=self.validate_request(items)
        with self._lock:
            if self._process is not None and self._process.poll() is None: raise BuildBusyError("A native build is already running")
            for item in items:
                info=self._state["robots"][item["robot_id"]]; info.update(status="queued",progress=0,stage="Queued",error=None)
            self._state["building"]=True; self._state["current"]=[i["robot_id"] for i in items]; self._state["log"]=[]; self._save()
            request_path=self.path.parent/"build_request.json"; request_path.write_text(json.dumps(items,indent=2),encoding="utf-8")
            cmd=[sys.executable,str(self.project_root/"scripts/native_build.py"),"--project-root",str(self.project_root),"--request",str(request_path)]
            self._process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
            (self.runtime_dir/'build.pid').write_text(f'{self._process.pid}\n')
            threading.Thread(target=self._collect,args=(self._process,items),daemon=True).start()
        return self.status()
    def _collect(self,process:subprocess.Popen[str],items:list[dict[str,Any]])->None:
        if process.stdout:
            for raw in process.stdout:
                line=raw.rstrip("\n")
                with self._lock:
                    self._state["log"].append(line); self._state["log"]=self._state["log"][-600:]
                    if line.startswith("RWL_EVENT "):
                        try:
                            ev=json.loads(line[len("RWL_EVENT "):]); rid=ev.get("robot_id")
                            if rid in self._state["robots"]:
                                self._state["robots"][rid].update({k:v for k,v in ev.items() if k in {"status","progress","stage","error"}})
                        except json.JSONDecodeError: pass
                    self._save()
        code=process.wait()
        with self._lock:
            if code==0:
                for item in items:
                    info=self._state["robots"][item["robot_id"]]
                    info.update(installed=True,high_level=item["high_level"],low_level=item["low_level"],status="installed",progress=100,stage="Ready",error=None)
            else:
                for item in items:
                    info=self._state["robots"][item["robot_id"]]
                    if info["status"] != "installed": info.update(status="failed",stage="Build failed",error=f"native builder exited {code}")
            self._state["building"]=False; self._state["current"]=None; self._save(); self._process=None
            try: (self.runtime_dir/'build.pid').unlink()
            except FileNotFoundError: pass
    def cancel(self)->bool:
        with self._lock:
            process=self._process
            if process is None:
                try: (self.runtime_dir/'build.pid').unlink()
                except FileNotFoundError: pass
                return False
            if process.poll() is not None:
                try: process.wait(timeout=0)
                except Exception: pass
                self._process=None
                try: (self.runtime_dir/'build.pid').unlink()
                except FileNotFoundError: pass
                return False
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
        with self._lock:
            if self._process is process: self._process=None
            self._state["building"]=False; self._state["current"]=None; self._save()
        try: (self.runtime_dir/'build.pid').unlink()
        except FileNotFoundError: pass
        return True
