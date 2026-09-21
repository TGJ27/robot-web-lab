from __future__ import annotations

from dataclasses import asdict
from contextlib import asynccontextmanager
import asyncio
import atexit
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .builds import BuildBusyError, BuildManager
from .build_profiles import BuildProfileError, BuildProfileStore
from .examples import ExampleService, UnsafePathError
from .mimic import MimicPolicyStore, UnsupportedPolicyFile
from .models import ModelService
from .registry import RobotRegistry
from .runner import ControlOwnershipError, LowLevelRunner, ProcessBusyError
from .runtime import EventHub, InvalidTransition, MockRuntimeAdapter
from .settings import AppSettings, KeyConflictError, SettingsStore
from .supervisor import NativeSupervisor, SimulationError


class KeyRemapRequest(BaseModel):
    action: str
    key: str = Field(min_length=1, max_length=64)
    resolution: Literal["reject", "replace", "swap"] = "reject"
class FsmRequest(BaseModel): mode: str
class VelocityRequest(BaseModel):
    vx: float = Field(ge=-1.0, le=1.0); vy: float = Field(ge=-1.0, le=1.0); yaw: float = Field(ge=-2.0, le=2.0)
class HangerRequest(BaseModel): action: Literal["attach", "release", "raise", "lower"]
class CopyRequest(BaseModel): source: str; destination: str
class NewExampleRequest(BaseModel): name: str; language: Literal["cpp", "python"]; template: str = "blank"
class SaveSourceRequest(BaseModel): path: str; content: str
class RunnerRequest(BaseModel): path: str; interface: str = "lo"; builtin: bool = False
class RenameSourceRequest(BaseModel): path: str; new_name: str
class BuildProfileTextRequest(BaseModel): content: str
class BuildItem(BaseModel): robot_id: str; high_level: bool = False; low_level: bool = True
class BuildRequest(BaseModel): robots: list[BuildItem]


def create_app(project_root: Path | None = None, *, runtime: MockRuntimeAdapter | None = None) -> FastAPI:
    root=Path(project_root or Path(__file__).resolve().parents[1]).resolve(); workspace=root/"workspace"; frontend=root/"frontend"
    registry=RobotRegistry.default(); build_manager=BuildManager(workspace/"build_state.json",registry,project_root=root)

    # Upgrade safety: preserve an already-built G1 when complete native
    # artifacts exist but local workspace metadata is missing.
    built=build_manager.status()["installed_robots"]
    if not built:
        g1_artifacts=(
            root/"build/native/prefix/lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake",
            root/"third_party/unitree_rl_mjlab/simulate/build/rwl_mujoco_headless",
            root/"third_party/unitree_rl_mjlab/deploy/robots/g1/build/g1_ctrl",
        )
        if all(path.exists() for path in g1_artifacts):
            build_manager.mark_installed("unitree_g1",high_level=True,low_level=True)
            built=build_manager.status()["installed_robots"]

    settings_store=SettingsStore(workspace/"settings.json",registry); settings=settings_store.load()
    # build_state.json is authoritative. Keep settings synchronized in both
    # directions so a preserved build immediately becomes active after patching.
    settings.installed_robots=list(built)
    if settings.active_robot not in settings.installed_robots:
        settings.active_robot=settings.installed_robots[0] if settings.installed_robots else None
    settings_store.save(settings)
    if runtime is None:
        if settings.active_robot:
            robot=registry.get(settings.active_robot); runtime=MockRuntimeAdapter(settings.active_robot,robot.joint_count or 0)
        else: runtime=MockRuntimeAdapter(None,0)
    examples=ExampleService(root/"third_party/unitree_sdk2",workspace/"examples",registry); mimic=MimicPolicyStore(workspace/"mimic")
    build_profiles=BuildProfileStore(workspace/"build_profiles.yaml")
    models=ModelService(root,registry)
    hub=EventHub(); supervisor=NativeSupervisor(root,registry,build_manager)
    def authoritative_control_owner() -> str:
        if supervisor.running():
            native_owner=supervisor.read_control_state().get("control_owner")
            if native_owner:
                return native_owner
        return runtime.snapshot().control_owner
    runner=LowLevelRunner(workspace/"examples",root/"third_party/unitree_sdk2",owner=authoritative_control_owner,sdk_prefix=root/"build/native/prefix",registry=registry,profile_store=build_profiles)
    def cleanup_children()->None:
        # Idempotent: graceful Uvicorn shutdown calls this via lifespan, while
        # atexit provides a second chance for interpreter-level exits.
        for stop in (runner.stop, supervisor.stop, build_manager.cancel):
            try:
                stop()
            except Exception:
                pass
        try:
            runtime.set_connected(False)
        except Exception:
            pass

    atexit.register(cleanup_children)

    @asynccontextmanager
    async def lifespan(_app:FastAPI):
        try:
            yield
        finally:
            cleanup_children()
    app=FastAPI(title="Robot Web Lab",version="0.1.0",lifespan=lifespan)
    @app.middleware("http")
    async def cache_robot_assets(request:Request,call_next):
        response=await call_next(request)
        if request.url.path.startswith("/static/assets/robots/"):
            response.headers["Cache-Control"]="public, max-age=31536000, immutable"
        return response
    for name,value in {"project_root":root,"registry":registry,"settings_store":settings_store,"runtime":runtime,"examples":examples,"mimic":mimic,"runner":runner,"hub":hub,"build_manager":build_manager,"models":models,"supervisor":supervisor,"build_profiles":build_profiles}.items(): setattr(app.state,name,value)
    if frontend.exists(): app.mount("/static",StaticFiles(directory=frontend),name="static")
    async def emit(kind:str,data:dict)->None: await hub.publish({"type":kind,"data":data})
    def state_payload()->dict:
        payload=runtime.snapshot().to_dict()
        native=supervisor.read_native_state()
        if native:
            payload.update(native)
            payload["connected"]=True
        if supervisor.running(): payload.update(supervisor.read_control_state())
        return payload

    @app.get("/")
    def index():
        p=frontend/"index.html"
        if not p.exists(): raise HTTPException(503,"Frontend is not installed")
        return FileResponse(p)
    @app.get("/api/health")
    def health(): return {"ok":True,"version":app.version,"runtime":"native-supervisor-ready","build":build_manager.status()}
    @app.get("/api/robots")
    def robots(): return [asdict(r) for r in registry.list()]
    @app.get("/api/build/status")
    def build_status(): return build_manager.status()
    @app.post("/api/build/start")
    async def build_start(payload:BuildRequest):
        try: result=build_manager.start([i.model_dump() for i in payload.robots])
        except (ValueError,KeyError) as exc: raise HTTPException(400,str(exc)) from exc
        except BuildBusyError as exc: raise HTTPException(409,str(exc)) from exc
        await emit("build",result); return result
    @app.post("/api/build/cancel")
    async def build_cancel():
        stopped=build_manager.cancel(); result=build_manager.status(); await emit("build",result); return {"cancelled":stopped,"status":result}

    @app.get("/api/simulation/status")
    def simulation_status(): return supervisor.status()
    @app.post("/api/simulation/start/{robot_id}")
    async def simulation_start(robot_id:str):
        try: result=supervisor.start(robot_id)
        except (SimulationError,KeyError) as exc: raise HTTPException(409,str(exc)) from exc
        robot=registry.get(robot_id); runtime.set_robot(robot_id,robot.joint_count or 0); runtime.set_connected(True)
        info=build_manager.status()["robots"][robot_id]
        desired_level=settings_store.load().ui_level
        if not info.get("high_level"):
            runtime.state.control_owner="low"; runtime.state.fsm_mode="LL Debug"
        elif desired_level=="low" and info.get("low_level"):
            runtime.return_to_passive(); supervisor.enter_low_level(); runtime.enter_low_level()
        await emit("state",state_payload()); return result
    @app.post("/api/simulation/stop")
    async def simulation_stop():
        runner.stop(); result=supervisor.stop(); runtime.set_connected(False); await emit("state",state_payload()); return result

    @app.get("/api/settings")
    def get_settings(): return asdict(settings_store.load())
    @app.put("/api/settings")
    async def put_settings(payload:AppSettings):
        built_now=set(build_manager.status()["installed_robots"]); requested=set(payload.installed_robots or [])
        if not requested.issubset(built_now): raise HTTPException(400,"installed_robots may only contain successfully built robots")
        if payload.active_robot is not None and payload.active_robot not in requested: raise HTTPException(400,"Active robot must be successfully built and installed")
        try:
            settings_store.save(payload)
            if payload.active_robot: robot=registry.get(payload.active_robot); runtime.set_robot(payload.active_robot,robot.joint_count or 0)
            else: runtime.set_robot(None,0)
        except (KeyError,ValueError) as exc: raise HTTPException(400,str(exc)) from exc
        await emit("settings",asdict(payload)); return asdict(payload)
    @app.post("/api/settings/sync-builds")
    async def sync_builds():
        current=settings_store.load(); built_now=build_manager.status()["installed_robots"]; current.installed_robots=built_now
        if current.active_robot not in built_now: current.active_robot=built_now[0] if built_now else None
        settings_store.save(current)
        if current.active_robot: robot=registry.get(current.active_robot); runtime.set_robot(current.active_robot,robot.joint_count or 0)
        else: runtime.set_robot(None,0)
        await emit("settings",asdict(current)); return asdict(current)
    @app.post("/api/settings/keymap")
    async def remap_key(payload:KeyRemapRequest):
        current=settings_store.load()
        try: settings_store.remap_key(current,payload.action,payload.key,resolution=payload.resolution)
        except KeyConflictError as exc: raise HTTPException(409,{"key":exc.key,"existing_action":exc.existing_action}) from exc
        settings_store.save(current); await emit("keymap",current.keymap); return {"keymap":current.keymap}


    @app.get("/api/model/{robot_id}")
    def model_manifest(robot_id:str):
        if robot_id not in build_manager.status()["installed_robots"]: raise HTTPException(409,"Build this robot before loading its model")
        try: return models.manifest(robot_id)
        except (KeyError,FileNotFoundError,ValueError) as exc: raise HTTPException(404,str(exc)) from exc
    @app.get("/api/model/{robot_id}/asset")
    def model_asset(robot_id:str,path:str):
        if robot_id not in build_manager.status()["installed_robots"]: raise HTTPException(409,"Build this robot before loading its model")
        try: return FileResponse(models.asset_path(robot_id,path))
        except (KeyError,FileNotFoundError,ValueError) as exc: raise HTTPException(404,str(exc)) from exc

    @app.get("/api/state")
    def state(): return state_payload()
    @app.post("/api/control/fsm")
    async def control_fsm(payload:FsmRequest):
        try:
            runtime.set_fsm_mode(payload.mode)
            if supervisor.running(): supervisor.write_web_control(payload.mode,**runtime.state.velocity)
        except InvalidTransition as exc: raise HTTPException(409,str(exc)) from exc
        result=state_payload(); await emit("state",result); return result
    @app.post("/api/control/policy/{policy_id}")
    async def control_policy(policy_id:str):
        if policy_id != "dance1_subject2":
            raise HTTPException(404,"Unknown runnable policy")
        current=state_payload()
        if current.get("control_owner") != "high" or current.get("fsm_mode") != "Velocity":
            raise HTTPException(409,"Dance1 Subject2 requires High-Level Velocity mode")
        try:
            if supervisor.running():
                supervisor.write_web_control("Mimic",**runtime.state.velocity)
            else:
                runtime.set_fsm_mode("Mimic")
        except InvalidTransition as exc:
            raise HTTPException(409,str(exc)) from exc
        result=state_payload(); await emit("state",result); return result
    @app.post("/api/control/velocity")
    async def control_velocity(payload:VelocityRequest):
        try:
            runtime.set_velocity(payload.vx,payload.vy,payload.yaw)
            if supervisor.running(): supervisor.write_web_control('-',payload.vx,payload.vy,payload.yaw)
        except InvalidTransition as exc: raise HTTPException(409,str(exc)) from exc
        result=state_payload(); await emit("state",result); return result
    @app.post("/api/control/hanger")
    async def control_hanger(payload:HangerRequest):
        try:
            runtime.hanger(payload.action)
            if supervisor.running(): supervisor.write_hanger(payload.action)
        except (InvalidTransition,ValueError) as exc: raise HTTPException(409,str(exc)) from exc
        result=state_payload(); await emit("state",result); return result
    async def wait_for_control(*, owner: str | None = None, fsm: str | None = None, timeout: float = 5.0) -> dict:
        loop=asyncio.get_running_loop(); deadline=loop.time()+timeout
        last=state_payload()
        while loop.time() < deadline:
            last=state_payload()
            if (owner is None or last.get("control_owner")==owner) and (fsm is None or last.get("fsm_mode")==fsm):
                return last
            await asyncio.sleep(0.05)
        wanted=", ".join(x for x in [f"owner={owner}" if owner else "", f"fsm={fsm}" if fsm else ""] if x)
        raise HTTPException(409,f"Timed out waiting for {wanted}; current owner={last.get('control_owner')}, fsm={last.get('fsm_mode')}")

    @app.post("/api/control/ll-prepare")
    async def prepare_low_level():
        current=state_payload()
        if current.get("control_owner")=="low":
            return current
        snap=runtime.snapshot(); rid=snap.robot_id
        if not rid:
            raise HTTPException(409,"Build and select a robot first")
        info=build_manager.status()["robots"].get(rid,{})
        if not info.get("low_level"):
            raise HTTPException(409,"Low-Level SDK pack is not installed for this robot")
        if current.get("fsm_mode")!="Passive" or current.get("control_owner")!="high":
            try: runtime.return_to_passive()
            except InvalidTransition as exc: raise HTTPException(409,str(exc)) from exc
            if supervisor.running(): supervisor.write_web_control("Passive",0,0,0)
            await wait_for_control(owner="high",fsm="Passive")
        try:
            runtime.enter_low_level()
            if supervisor.running(): supervisor.enter_low_level()
        except InvalidTransition as exc: raise HTTPException(409,str(exc)) from exc
        result=await wait_for_control(owner="low",fsm="LL Debug")
        await emit("state",result)
        return result

    @app.post("/api/control/ll-enter")
    async def enter_low_level():
        try:
            runtime.enter_low_level()
            if supervisor.running(): supervisor.enter_low_level()
        except InvalidTransition as exc: raise HTTPException(409,str(exc)) from exc
        result=state_payload(); await emit("state",result); return result
    @app.post("/api/control/passive")
    async def passive():
        runner.stop()
        try:
            snap=runtime.snapshot(); rid=snap.robot_id
            if rid and not build_manager.status()["robots"].get(rid,{}).get("high_level"):
                raise InvalidTransition("This robot was built as Low-Level only; no High-Level pack is installed")
            was_low=state_payload().get("control_owner")=="low"
            runtime.return_to_passive()
            if was_low and supervisor.running(): supervisor.return_high_level()
            if supervisor.running(): supervisor.write_web_control('Passive',0,0,0)
        except InvalidTransition as exc: raise HTTPException(409,str(exc)) from exc
        result=state_payload(); await emit("state",result); return result
    @app.post("/api/control/reset")
    async def reset():
        runner.stop()
        runtime.reset()
        if supervisor.running(): supervisor.write_runtime_action('reset')
        result=state_payload(); await emit("state",result); return result

    @app.get("/api/examples/{robot_id}")
    def list_examples(robot_id:str):
        if robot_id not in build_manager.status()["installed_robots"]: raise HTTPException(409,"Build this robot before opening SDK examples")
        try: return [asdict(i) for i in examples.list_examples(robot_id)]
        except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    @app.get("/api/examples/{robot_id}/source")
    def read_example(robot_id:str,path:str):
        if robot_id not in build_manager.status()["installed_robots"]: raise HTTPException(409,"Build this robot first")
        try: return {"path":path,"content":examples.read_builtin(robot_id,path),"readonly":True}
        except UnsafePathError as exc: raise HTTPException(400,str(exc)) from exc
        except FileNotFoundError as exc: raise HTTPException(404,str(exc)) from exc
    @app.get("/api/workspace/{robot_id}")
    def list_workspace(robot_id:str): return [asdict(i) for i in examples.list_workspace(robot_id)]
    @app.get("/api/workspace/{robot_id}/source")
    def read_workspace(robot_id:str,path:str):
        try:return {"path":path,"content":examples.read_workspace(robot_id,path),"readonly":False}
        except UnsafePathError as exc:raise HTTPException(400,str(exc)) from exc
        except FileNotFoundError as exc:raise HTTPException(404,str(exc)) from exc
    @app.put("/api/workspace/{robot_id}/source")
    def save_workspace(robot_id:str,payload:SaveSourceRequest):
        try:saved=examples.save_workspace(robot_id,payload.path,payload.content);return {"path":saved.relative_to(examples.robot_workspace(robot_id)).as_posix()}
        except UnsafePathError as exc:raise HTTPException(400,str(exc)) from exc
    @app.post("/api/workspace/{robot_id}/copy")
    def copy_workspace(robot_id:str,payload:CopyRequest):
        try:
            saved=examples.copy_to_workspace(robot_id,payload.source,payload.destination)
            rel=saved.relative_to(examples.robot_workspace(robot_id)).as_posix()
            build_profiles.inherit_copy(robot_id,payload.source,rel)
            return {"path":rel}
        except (UnsafePathError,FileNotFoundError,BuildProfileError) as exc:raise HTTPException(400,str(exc)) from exc
    @app.post("/api/workspace/{robot_id}/new")
    def new_workspace(robot_id:str,payload:NewExampleRequest):
        try:
            saved=examples.create_example(robot_id,payload.name,payload.language,payload.template)
            rel=saved.relative_to(examples.robot_workspace(robot_id)).as_posix()
            build_profiles.assign_workspace(robot_id,rel,saved)
            return {"path":rel}
        except (UnsafePathError,FileExistsError,ValueError,BuildProfileError) as exc:raise HTTPException(400,str(exc)) from exc

    @app.post("/api/workspace/{robot_id}/rename")
    def rename_workspace(robot_id:str,payload:RenameSourceRequest):
        try:
            saved=examples.rename_workspace(robot_id,payload.path,payload.new_name)
            rel=saved.relative_to(examples.robot_workspace(robot_id)).as_posix()
            build_profiles.rename_workspace(robot_id,payload.path,rel)
            return {"path":rel}
        except (UnsafePathError,FileNotFoundError,FileExistsError,BuildProfileError) as exc:raise HTTPException(400,str(exc)) from exc

    @app.delete("/api/workspace/{robot_id}/source")
    def delete_workspace(robot_id:str,path:str):
        try:
            deleted=examples.delete_workspace(robot_id,path)
            if not deleted: raise HTTPException(404,"Workspace file not found")
            build_profiles.delete_workspace(robot_id,path)
            return {"deleted":path}
        except UnsafePathError as exc: raise HTTPException(400,str(exc)) from exc

    @app.get("/api/build-profiles")
    def get_build_profiles(): return {"content":build_profiles.text()}

    @app.put("/api/build-profiles")
    def put_build_profiles(payload:BuildProfileTextRequest):
        try: build_profiles.save_text(payload.content); return {"content":build_profiles.text()}
        except BuildProfileError as exc: raise HTTPException(400,str(exc)) from exc

    @app.get("/api/mimic/{robot_id}")
    def list_mimic(robot_id:str): return [asdict(p) for p in mimic.list(robot_id)]
    @app.post("/api/mimic/{robot_id}/upload")
    async def upload_mimic(robot_id:str,request:Request,filename:str):
        if not registry.get(robot_id).supports_mimic: raise HTTPException(400,"Mimic web pack is not supported for this robot")
        try:path=mimic.save_bytes(robot_id,filename,await request.body())
        except UnsupportedPolicyFile as exc:raise HTTPException(400,str(exc)) from exc
        await emit("mimic",{"robot_id":robot_id,"filename":path.name});return {"filename":path.name}
    @app.delete("/api/mimic/{robot_id}/{policy_id}")
    async def delete_mimic(robot_id:str,policy_id:str):
        if not mimic.delete(robot_id,policy_id):raise HTTPException(404,"Policy not found")
        await emit("mimic",{"robot_id":robot_id,"deleted":policy_id});return {"deleted":policy_id}

    def managed_source(robot_id:str,relative_path:str,builtin:bool)->Path:
        try:
            if builtin: return examples.builtin_path(robot_id,relative_path)
            root_dir=examples.robot_workspace(robot_id); candidate=(root_dir/relative_path).resolve()
            if root_dir.resolve() not in candidate.parents: raise UnsafePathError("Path escapes workspace")
            if not candidate.is_file(): raise FileNotFoundError(relative_path)
            return candidate
        except (UnsafePathError,FileNotFoundError) as exc: raise HTTPException(400,str(exc)) from exc

    @app.post("/api/runner/{robot_id}/build")
    def build(robot_id:str,payload:RunnerRequest):
        try:
            source=managed_source(robot_id,payload.path,payload.builtin)
            ok,output=runner.build(source,robot_id=robot_id,relative_path=payload.path,builtin=payload.builtin)
        except (ControlOwnershipError,UnsafePathError,BuildProfileError) as exc:raise HTTPException(409,str(exc)) from exc
        return {"ok":ok,"output":output}
    @app.get("/api/runner/{robot_id}/status")
    def source_runner_status(robot_id:str,path:str,builtin:bool=False):
        try:return runner.status(managed_source(robot_id,path,builtin),robot_id=robot_id)
        except (UnsafePathError,FileNotFoundError) as exc:raise HTTPException(400,str(exc)) from exc
    @app.post("/api/runner/{robot_id}/run")
    def run(robot_id:str,payload:RunnerRequest):
        try:pid=runner.start(managed_source(robot_id,payload.path,payload.builtin),payload.interface,robot_id=robot_id)
        except ControlOwnershipError as exc:raise HTTPException(409,str(exc)) from exc
        except (ProcessBusyError,UnsafePathError,FileNotFoundError) as exc:raise HTTPException(400,str(exc)) from exc
        return {"pid":pid}
    @app.post("/api/runner/stop")
    def stop_runner():return {"stopped":runner.stop()}
    @app.get("/api/runner/status")
    def runner_status():return {"running":runner.running(),"logs":runner.logs()}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket:WebSocket):
        await websocket.accept(); queue=hub.subscribe()
        try:
            await websocket.send_json({"type":"state","data":state_payload()})
            while True: await websocket.send_json(await queue.get())
        except WebSocketDisconnect: pass
        finally: hub.unsubscribe(queue)
    return app

app=create_app()
