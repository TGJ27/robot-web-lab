from pathlib import Path
from backend.builds import BuildManager
from backend.registry import RobotRegistry
from backend.supervisor import NativeSupervisor


def test_supervisor_builds_robot_specific_sim_command(tmp_path: Path):
    registry=RobotRegistry.default(); manager=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    manager.mark_installed('unitree_g1',high_level=True,low_level=True)
    sup=NativeSupervisor(tmp_path,registry,manager)
    sim,ctrl=sup.commands_for('unitree_g1')
    assert '-r' in sim and sim[sim.index('-r')+1]=='g1'
    assert '-s' in sim and sim[sim.index('-s')+1].endswith('scene_g1.xml')
    assert ctrl[-1]=='--network=lo'



def test_supervisor_uses_robot_specific_high_level_controller_binary(tmp_path: Path):
    registry=RobotRegistry.default(); manager=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    expected={
        'unitree_g1':'g1_ctrl',
        'unitree_g1_23dof':'g1_ctrl',
        'unitree_go2':'go2_ctrl',
        'unitree_h1':'h1_2_ctrl',
        'unitree_a2':'a2_ctrl',
        'unitree_r1':'r1_ctrl',
    }
    sup=NativeSupervisor(tmp_path,registry,manager)
    for rid,target in expected.items():
        manager.mark_installed(rid,high_level=True,low_level=registry.get(rid).supports_low_level)
        _,ctrl=sup.commands_for(rid)
        assert ctrl is not None
        assert Path(ctrl[0]).name == target

def test_ll_only_robot_has_no_controller_command(tmp_path: Path):
    registry=RobotRegistry.default(); manager=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    manager.mark_installed('unitree_go2',high_level=False,low_level=True)
    sup=NativeSupervisor(tmp_path,registry,manager)
    _,ctrl=sup.commands_for('unitree_go2')
    assert ctrl is None

def test_supervisor_writes_atomic_hanger_request(tmp_path):
    registry = RobotRegistry.default()
    builds = BuildManager(tmp_path/'workspace/build_state.json', registry, project_root=tmp_path)
    sup = NativeSupervisor(tmp_path, registry, builds)
    sup.write_hanger('raise')
    payload = (tmp_path/'run/native/web_hanger').read_text().strip().split()
    assert payload[1] == 'raise'

def test_supervisor_reads_native_qpos_state(tmp_path):
    registry = RobotRegistry.default()
    builds = BuildManager(tmp_path/'workspace/build_state.json', registry, project_root=tmp_path)
    sup = NativeSupervisor(tmp_path, registry, builds)
    state_file=tmp_path/'run/native/native_state'
    state_file.parent.mkdir(parents=True, exist_ok=True)
    qpos=[1.0,2.0,0.9,1.0,0.0,0.0,0.0,0.11,0.22]
    state_file.write_text('12.5 9 ' + ' '.join(map(str,qpos)) + '\n')
    state=sup.read_native_state()
    assert state['sim_time']==12.5
    assert state['base_position']==[1.0,2.0,0.9]
    assert state['base_quaternion']==[1.0,0.0,0.0,0.0]
    assert state['joint_positions']==[0.11,0.22]

def test_supervisor_reads_runtime_fsm_and_owner_files(tmp_path):
    registry=RobotRegistry.default(); builds=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    sup=NativeSupervisor(tmp_path,registry,builds)
    (tmp_path/'run/native/control_mode').write_text('DEBUG\n')
    (tmp_path/'run/native/fsm_state').write_text('Velocity\n')
    state=sup.read_control_state()
    assert state['control_owner']=='low'
    assert state['fsm_mode']=='LL Debug'

def test_supervisor_writes_atomic_reset_request(tmp_path):
    registry = RobotRegistry.default()
    builds = BuildManager(tmp_path/'workspace/build_state.json', registry, project_root=tmp_path)
    sup = NativeSupervisor(tmp_path, registry, builds)
    sup.write_runtime_action('reset')
    payload = (tmp_path/'run/native/web_runtime').read_text().strip().split()
    assert payload[1] == 'reset'

def test_supervisor_derives_rpy_from_native_free_joint_quaternion(tmp_path):
    import math
    registry=RobotRegistry.default(); builds=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    sup=NativeSupervisor(tmp_path,registry,builds)
    state_file=tmp_path/'run/native/native_state'; state_file.parent.mkdir(parents=True,exist_ok=True)
    # 90 degree yaw quaternion in MuJoCo w,x,y,z order.
    c=math.sqrt(0.5); qpos=[0.0,0.0,0.8,c,0.0,0.0,c,0.1]
    state_file.write_text('1.0 8 ' + ' '.join(map(str,qpos)) + '\n')
    state=sup.read_native_state()
    assert abs(state['rpy'][2] - math.pi/2) < 1e-5


def test_supervisor_uses_headless_mujoco_binary(tmp_path: Path):
    registry=RobotRegistry.default(); manager=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    manager.mark_installed('unitree_g1',high_level=True,low_level=True)
    sup=NativeSupervisor(tmp_path,registry,manager)
    sim,_=sup.commands_for('unitree_g1')
    assert sim[0].endswith('/simulate/build/rwl_mujoco_headless')
    assert 'unitree_mujoco' not in Path(sim[0]).name


def test_high_level_control_state_does_not_assume_passive_before_fsm_is_published(tmp_path: Path):
    registry=RobotRegistry.default(); builds=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    sup=NativeSupervisor(tmp_path,registry,builds)
    runtime=tmp_path/'run/native'; runtime.mkdir(parents=True,exist_ok=True)
    (runtime/'control_mode').write_text('HL\n')
    state=sup.read_control_state()
    assert state == {'control_owner':'high','fsm_mode':'Unknown'}


def test_terminate_waits_and_reaps_child_after_signal(tmp_path, monkeypatch):
    registry=RobotRegistry.default(); builds=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    sup=NativeSupervisor(tmp_path,registry,builds)
    calls=[]
    class FakeProc:
        pid=321
        def __init__(self): self.running=True
        def poll(self): return None if self.running else 0
        def wait(self, timeout=None):
            calls.append(('wait', timeout)); self.running=False; return 0
    proc=FakeProc()
    monkeypatch.setattr('backend.supervisor.os.killpg', lambda pid, sig: calls.append(('killpg', pid, sig)))
    sup._terminate(proc)
    assert any(c[0]=='killpg' for c in calls)
    assert any(c[0]=='wait' for c in calls)


def test_stop_clears_native_runtime_control_files(tmp_path):
    registry=RobotRegistry.default(); builds=BuildManager(tmp_path/'workspace/build_state.json',registry,project_root=tmp_path)
    sup=NativeSupervisor(tmp_path,registry,builds)
    for name in ('control_mode','fsm_state','web_control','web_hanger','web_runtime','request','native_state'):
        (sup.runtime/name).write_text('stale\n')
    sup.stop()
    for name in ('control_mode','fsm_state','web_control','web_hanger','web_runtime','request','native_state'):
        assert not (sup.runtime/name).exists()
