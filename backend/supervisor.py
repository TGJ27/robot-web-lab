from __future__ import annotations

from collections import deque
from pathlib import Path
import os
import math
import signal
import subprocess
import threading
import time

from .builds import BuildManager
from .registry import RobotRegistry


class SimulationError(RuntimeError):
    pass


class NativeSupervisor:
    def __init__(self, project_root: Path, registry: RobotRegistry, builds: BuildManager):
        self.root=Path(project_root).resolve(); self.registry=registry; self.builds=builds
        self.rl=self.root/'third_party/unitree_rl_mjlab'; self.prefix=self.root/'build/native/prefix'; self.runtime=self.root/'run/native'
        self.runtime.mkdir(parents=True,exist_ok=True)
        self._sim: subprocess.Popen[str] | None=None; self._ctrl: subprocess.Popen[str] | None=None; self._robot_id: str | None=None
        self._logs: deque[str]=deque(maxlen=1000); self._lock=threading.RLock(); self._seq=0
    def commands_for(self, robot_id: str) -> tuple[list[str], list[str] | None]:
        robot=self.registry.get(robot_id); info=self.builds.status()['robots'][robot_id]
        sim_bin=self.rl/'simulate/build/rwl_mujoco_headless'
        model_root=self.root/'third_party'/robot.model_repo
        scene=(model_root/robot.model_xml).resolve()
        sim=[str(sim_bin),'-r',str(robot.native_robot),'-s',str(scene),'-n','lo','-i','0']
        ctrl=None
        if info.get('high_level') and robot.supports_web_high_level and robot.controller_dir:
            ctrl_bin=self.rl/robot.controller_dir/'build/g1_ctrl'
            ctrl=[str(ctrl_bin),'--network=lo']
        return sim,ctrl
    def _env(self)->dict[str,str]:
        env=os.environ.copy(); libs=[self.prefix/'lib',self.rl/'simulate/mujoco/lib']
        third=self.rl/'deploy/thirdparty'
        if third.exists():
            for p in third.glob('onnxruntime*/lib'): libs.append(p)
        env['LD_LIBRARY_PATH']=':'.join(str(x) for x in libs if x.exists())+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        env['G1_SIM_RUNTIME_DIR']=str(self.runtime)
        return env
    def _collect(self,proc:subprocess.Popen[str],tag:str)->None:
        if proc.stdout is None:return
        for line in proc.stdout:self._logs.append(f'[{tag}] {line.rstrip()}')
    def start(self,robot_id:str)->dict:
        with self._lock:
            if self.running(): raise SimulationError('Simulation is already running')
            info=self.builds.status()['robots'].get(robot_id)
            if not info or not info.get('installed'): raise SimulationError('Build this robot before starting simulation')
            sim,ctrl=self.commands_for(robot_id)
            if not Path(sim[0]).is_file(): raise SimulationError('headless MuJoCo binary is missing; rebuild the robot pack')
            if ctrl and not Path(ctrl[0]).is_file(): raise SimulationError('high-level controller binary is missing; rebuild the G1 HL pack')
            self.runtime.mkdir(parents=True,exist_ok=True)
            (self.runtime/'control_mode').write_text('HL\n' if ctrl else 'DEBUG\n')
            for name in ('request','fsm_state','web_control'):
                try:(self.runtime/name).unlink()
                except FileNotFoundError:pass
            self._sim=subprocess.Popen(sim,cwd=str(self.rl),env=self._env(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True,bufsize=1)
            (self.runtime/'sim.pid').write_text(f'{self._sim.pid}\n')
            threading.Thread(target=self._collect,args=(self._sim,'SIM'),daemon=True).start(); self._robot_id=robot_id
            time.sleep(.35)
            if self._sim.poll() is not None: raise SimulationError('MuJoCo simulator exited during startup. Check native logs.')
            if ctrl: self._start_controller(ctrl)
            threading.Thread(target=self._watch_runtime_requests,daemon=True).start()
            return self.status()
    def _start_controller(self,cmd:list[str]|None=None)->None:
        if cmd is None:
            if not self._robot_id:return
            _,cmd=self.commands_for(self._robot_id)
        if not cmd:return
        self._ctrl=subprocess.Popen(cmd,cwd=str(Path(cmd[0]).parent),env=self._env(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True,bufsize=1)
        (self.runtime/'controller.pid').write_text(f'{self._ctrl.pid}\n')
        threading.Thread(target=self._collect,args=(self._ctrl,'CTRL'),daemon=True).start()
    def _terminate(self,proc:subprocess.Popen[str]|None)->None:
        if proc is None:
            return
        try:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=3)
                    return
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            # Always wait once more. This reaps a child that exited between
            # poll/signal and prevents <defunct> children on backend shutdown.
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        except (ChildProcessError, OSError):
            pass
    def _clear_runtime_files(self)->None:
        for name in ("control_mode","fsm_state","web_control","web_hanger","web_runtime","request","native_state","sim.pid","controller.pid"):
            try:
                (self.runtime/name).unlink()
            except FileNotFoundError:
                pass
    def stop(self)->dict:
        with self._lock:
            self._terminate(self._ctrl); self._ctrl=None
            self._terminate(self._sim); self._sim=None
            self._robot_id=None
            self._clear_runtime_files()
            return self.status()
    def running(self)->bool:
        return self._sim is not None and self._sim.poll() is None
    def enter_low_level(self)->None:
        with self._lock:
            self._terminate(self._ctrl);self._ctrl=None;(self.runtime/'control_mode').write_text('DEBUG\n')
    def return_high_level(self)->None:
        with self._lock:
            if not self._robot_id:return
            (self.runtime/'control_mode').write_text('HL\n');_,ctrl=self.commands_for(self._robot_id);self._start_controller(ctrl)
    def write_web_control(self,action:str='-',vx:float=0,vy:float=0,yaw:float=0)->None:
        self._seq+=1; tmp=self.runtime/'web_control.tmp'; target=self.runtime/'web_control'; tmp.write_text(f'{self._seq} {action} {vx:.6f} {vy:.6f} {yaw:.6f}\n');tmp.replace(target)
    def write_hanger(self,action:str)->None:
        if action not in {'attach','release','raise','lower'}: raise ValueError('Unsupported hanger action')
        self._seq+=1; tmp=self.runtime/'web_hanger.tmp'; target=self.runtime/'web_hanger'; tmp.write_text(f'{self._seq} {action}\n'); tmp.replace(target)
    def write_runtime_action(self,action:str)->None:
        if action not in {'reset'}: raise ValueError('Unsupported runtime action')
        self._seq+=1; tmp=self.runtime/'web_runtime.tmp'; target=self.runtime/'web_runtime'; tmp.write_text(f'{self._seq} {action}\n'); tmp.replace(target)
    def _watch_runtime_requests(self)->None:
        while self.running():
            path=self.runtime/'request'
            try: request=path.read_text().strip(); path.unlink(missing_ok=True)
            except (FileNotFoundError,OSError): request=''
            if request=='DEBUG': self.enter_low_level()
            elif request=='HL_PASSIVE': self.return_high_level()
            time.sleep(0.05)

    def read_control_state(self)->dict:
        try: mode=(self.runtime/'control_mode').read_text().strip()
        except (FileNotFoundError,OSError): mode=''
        try: fsm=(self.runtime/'fsm_state').read_text().strip()
        except (FileNotFoundError,OSError): fsm=''
        if mode=='DEBUG': return {'control_owner':'low','fsm_mode':'LL Debug'}
        if mode=='HL': return {'control_owner':'high','fsm_mode':fsm or 'Unknown'}
        return {}

    def read_native_state(self)->dict | None:
        path=self.runtime/'native_state'
        try: parts=path.read_text().strip().split()
        except (FileNotFoundError,OSError): return None
        if len(parts)<2: return None
        try:
            sim_time=float(parts[0]); nq=int(parts[1]); qpos=[float(x) for x in parts[2:2+nq]]
        except (ValueError,TypeError): return None
        if len(qpos)!=nq: return None
        base=qpos[:3] if nq>=3 else [0.0,0.0,0.0]
        quat=qpos[3:7] if nq>=7 else [1.0,0.0,0.0,0.0]
        joints=qpos[7:] if nq>=7 else qpos
        w,x,y,z=quat
        sinr_cosp=2.0*(w*x+y*z); cosr_cosp=1.0-2.0*(x*x+y*y)
        roll=math.atan2(sinr_cosp,cosr_cosp)
        sinp=2.0*(w*y-z*x); pitch=math.copysign(math.pi/2.0,sinp) if abs(sinp)>=1.0 else math.asin(sinp)
        siny_cosp=2.0*(w*z+x*y); cosy_cosp=1.0-2.0*(y*y+z*z)
        yaw=math.atan2(siny_cosp,cosy_cosp)
        return {'sim_time':sim_time,'base_position':base,'base_quaternion':quat,'rpy':[roll,pitch,yaw],'joint_positions':joints}
    def status(self)->dict:
        return {'running':self.running(),'robot_id':self._robot_id,'sim_pid':self._sim.pid if self._sim is not None and self._sim.poll() is None else None,'controller_running':self._ctrl is not None and self._ctrl.poll() is None,'controller_pid':self._ctrl.pid if self._ctrl is not None and self._ctrl.poll() is None else None,'logs':list(self._logs)}
