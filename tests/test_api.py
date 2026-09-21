from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.runtime import MockRuntimeAdapter


def make_client(tmp_path: Path):
    root = tmp_path / "project"
    (root / "frontend").mkdir(parents=True)
    (root / "frontend/index.html").write_text("<html>Robot Web Lab</html>")
    runtime = MockRuntimeAdapter("unitree_g1")
    app = create_app(root, runtime=runtime)
    return TestClient(app), runtime, root


def test_settings_and_robot_endpoints(tmp_path: Path):
    client, _, _ = make_client(tmp_path)
    robots = client.get("/api/robots").json()
    assert any(r["id"] == "unitree_g1" for r in robots)
    settings = client.get("/api/settings").json()
    assert settings["theme"] == "light"
    response = client.put("/api/settings", json={**settings, "theme": "light"})
    assert response.status_code == 200
    assert client.get("/api/settings").json()["theme"] == "light"


def test_key_mapping_conflict_returns_409(tmp_path: Path):
    client, _, _ = make_client(tmp_path)
    response = client.post("/api/settings/keymap", json={"action": "hanger_raise", "key": "1", "resolution": "reject"})
    assert response.status_code == 409
    assert response.json()["detail"]["existing_action"] == "passive"


def test_runtime_control_endpoints(tmp_path: Path):
    client, runtime, _ = make_client(tmp_path)
    client.app.state.build_manager.mark_installed("unitree_g1", high_level=True, low_level=True)
    assert client.post("/api/control/fsm", json={"mode": "FixStand"}).status_code == 200
    assert client.post("/api/control/fsm", json={"mode": "Velocity"}).status_code == 200
    assert client.post("/api/control/velocity", json={"vx": 0.2, "vy": 0, "yaw": 0.1}).status_code == 200
    assert runtime.snapshot().velocity["vx"] == 0.2
    assert client.post("/api/control/ll-enter").status_code == 409
    client.post("/api/control/fsm", json={"mode": "Passive"})
    assert client.post("/api/control/ll-enter").status_code == 200
    assert client.post("/api/control/passive").status_code == 200


def test_examples_and_workspace_api(tmp_path: Path):
    client, _, root = make_client(tmp_path)
    source = root / "third_party/unitree_sdk2/example/g1/low_level/test.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main(){return 0;}\n")
    client.app.state.build_manager.mark_installed("unitree_g1", high_level=False, low_level=True)

    examples = client.get("/api/examples/unitree_g1").json()
    assert examples[0]["relative_path"] == "test.cpp"
    opened = client.get("/api/examples/unitree_g1/source", params={"path": "test.cpp"}).json()
    assert opened["readonly"] is True
    copy = client.post("/api/workspace/unitree_g1/copy", json={"source": "test.cpp", "destination": "my_test.cpp"})
    assert copy.status_code == 200
    workspace = client.get("/api/workspace/unitree_g1").json()
    assert workspace[0]["relative_path"] == "my_test.cpp"


def test_mimic_upload_api(tmp_path: Path):
    client, _, _ = make_client(tmp_path)
    response = client.post("/api/mimic/unitree_g1/upload", params={"filename": "dance.onnx"}, content=b"demo")
    assert response.status_code == 200
    items = client.get("/api/mimic/unitree_g1").json()
    assert items[0]["id"] == "dance"

def test_state_endpoint_merges_native_mujoco_qpos_when_available(tmp_path: Path):
    client, _, root = make_client(tmp_path)
    native = root / "run/native/native_state"
    native.parent.mkdir(parents=True, exist_ok=True)
    native.write_text("3.25 9 1 2 0.9 1 0 0 0 0.11 0.22\n")
    payload = client.get("/api/state").json()
    assert payload["sim_time"] == 3.25
    assert payload["base_position"] == [1.0, 2.0, 0.9]
    assert payload["base_quaternion"] == [1.0, 0.0, 0.0, 0.0]
    assert payload["joint_positions"] == [0.11, 0.22]

def test_ll_only_robot_cannot_return_to_high_level_without_hl_pack(tmp_path: Path):
    client, runtime, _ = make_client(tmp_path)
    client.app.state.build_manager.mark_installed('unitree_r1', high_level=False, low_level=True)
    runtime.set_robot('unitree_r1', 26)
    runtime.state.control_owner='low'; runtime.state.fsm_mode='LL Debug'
    response=client.post('/api/control/passive')
    assert response.status_code==409


def test_ll_prepare_moves_high_level_velocity_to_confirmed_low_owner(tmp_path: Path):
    client, runtime, _ = make_client(tmp_path)
    client.app.state.build_manager.mark_installed("unitree_g1", high_level=True, low_level=True)
    runtime.set_fsm_mode("FixStand")
    runtime.set_fsm_mode("Velocity")
    response = client.post("/api/control/ll-prepare")
    assert response.status_code == 200
    payload = response.json()
    assert payload["control_owner"] == "low"
    assert payload["fsm_mode"] == "LL Debug"


def test_ll_prepare_is_idempotent_when_low_already_owns_control(tmp_path: Path):
    client, runtime, _ = make_client(tmp_path)
    client.app.state.build_manager.mark_installed("unitree_g1", high_level=True, low_level=True)
    runtime.enter_low_level()
    response = client.post("/api/control/ll-prepare")
    assert response.status_code == 200
    assert response.json()["control_owner"] == "low"


def test_runner_uses_native_control_owner_when_simulation_is_running(tmp_path: Path):
    client, runtime, _ = make_client(tmp_path)
    runtime.state.control_owner = 'high'
    client.app.state.supervisor.running = lambda: True
    client.app.state.supervisor.read_control_state = lambda: {'control_owner':'low','fsm_mode':'LL Debug'}
    assert client.app.state.runner._owner() == 'low'


def test_passive_endpoint_stops_low_level_program_before_returning_high(tmp_path: Path):
    client, runtime, _ = make_client(tmp_path)
    client.app.state.build_manager.mark_installed('unitree_g1', high_level=True, low_level=True)
    runtime.enter_low_level()
    calls=[]
    client.app.state.runner.stop = lambda: calls.append('runner-stop') or True
    response=client.post('/api/control/passive')
    assert response.status_code==200
    assert calls == ['runner-stop']
    assert response.json()['control_owner']=='high'
    assert response.json()['fsm_mode']=='Passive'


def test_builtin_dance_policy_is_triggered_from_velocity(tmp_path: Path):
    client, runtime, _ = make_client(tmp_path)
    client.app.state.build_manager.mark_installed('unitree_g1', high_level=True, low_level=True)
    runtime.set_fsm_mode('FixStand')
    runtime.set_fsm_mode('Velocity')
    response=client.post('/api/control/policy/dance1_subject2')
    assert response.status_code==200
    assert runtime.snapshot().fsm_mode=='Mimic'


def test_builtin_dance_policy_requires_velocity(tmp_path: Path):
    client, _, _ = make_client(tmp_path)
    client.app.state.build_manager.mark_installed('unitree_g1', high_level=True, low_level=True)
    response=client.post('/api/control/policy/dance1_subject2')
    assert response.status_code==409


def test_application_shutdown_stops_runner_and_native_supervisor(tmp_path: Path):
    root = tmp_path / 'project'
    (root / 'frontend').mkdir(parents=True)
    (root / 'frontend/index.html').write_text('<html>Robot Web Lab</html>')
    app=create_app(root, runtime=MockRuntimeAdapter('unitree_g1'))
    calls=[]
    app.state.runner.stop=lambda: calls.append('runner') or True
    app.state.supervisor.stop=lambda: calls.append('supervisor') or {'running':False}
    with TestClient(app):
        pass
    assert calls[-2:] == ['runner','supervisor']


def test_passive_endpoint_uses_native_owner_to_restart_high_level_controller(tmp_path: Path):
    client, runtime, _ = make_client(tmp_path)
    client.app.state.build_manager.mark_installed('unitree_g1', high_level=True, low_level=True)
    runtime.state.control_owner='high'; runtime.state.fsm_mode='Passive'
    client.app.state.supervisor.running=lambda: True
    client.app.state.supervisor.read_control_state=lambda: {'control_owner':'low','fsm_mode':'LL Debug'}
    calls=[]
    client.app.state.supervisor.return_high_level=lambda: calls.append('return-hl')
    client.app.state.supervisor.write_web_control=lambda *args, **kwargs: calls.append('passive-command')
    response=client.post('/api/control/passive')
    assert response.status_code==200
    assert 'return-hl' in calls


def test_workspace_rename_delete_and_build_profile_api(tmp_path: Path):
    client, _, root = make_client(tmp_path)
    client.app.state.build_manager.mark_installed('unitree_g1', high_level=False, low_level=True)
    source = root / 'third_party/unitree_sdk2/example/g1/low_level/g1_dual_arm_example.cpp'
    source.parent.mkdir(parents=True)
    source.write_text('#include <yaml-cpp/yaml.h>\n#define BLIB_DIR "x"\nint main(){return 0;}\n')
    copied = client.post('/api/workspace/unitree_g1/copy', json={'source':'g1_dual_arm_example.cpp','destination':'my_arm.cpp'})
    assert copied.status_code == 200
    renamed = client.post('/api/workspace/unitree_g1/rename', json={'path':'my_arm.cpp','new_name':'arm_lab.cpp'})
    assert renamed.status_code == 200
    assert renamed.json()['path'] == 'arm_lab.cpp'
    profiles = client.get('/api/build-profiles')
    assert profiles.status_code == 200
    assert 'arm_lab.cpp' in profiles.json()['content']
    deleted = client.delete('/api/workspace/unitree_g1/source', params={'path':'arm_lab.cpp'})
    assert deleted.status_code == 200
    assert client.get('/api/workspace/unitree_g1').json() == []


def test_builtin_sdk_source_can_use_runner_status_without_copy(tmp_path: Path):
    client, _, root = make_client(tmp_path)
    client.app.state.build_manager.mark_installed('unitree_g1', high_level=False, low_level=True)
    source = root / 'third_party/unitree_sdk2/example/g1/low_level/demo.cpp'
    source.parent.mkdir(parents=True)
    source.write_text('int main(){return 0;}\n')
    status = client.get('/api/runner/unitree_g1/status', params={'path':'demo.cpp','builtin':'true'})
    assert status.status_code == 200
    assert status.json()['built'] is False


def test_startup_keeps_authoritative_built_g1_active(tmp_path: Path):
    root = tmp_path / 'project'
    (root / 'frontend').mkdir(parents=True)
    (root / 'frontend/index.html').write_text('<html>Robot Web Lab</html>')
    workspace = root / 'workspace'
    workspace.mkdir(parents=True)
    workspace.joinpath('build_state.json').write_text('''{
      "building": false,
      "current": null,
      "log": [],
      "robots": {
        "unitree_g1": {
          "installed": true,
          "high_level": true,
          "low_level": true,
          "status": "installed",
          "progress": 100,
          "stage": "Ready",
          "error": null
        }
      }
    }''')
    workspace.joinpath('settings.json').write_text('''{
      "theme": "light",
      "active_robot": null,
      "ui_level": "high",
      "installed_robots": [],
      "keymap": null
    }''')
    client = TestClient(create_app(root, runtime=MockRuntimeAdapter(None, 0)))
    status = client.get('/api/build/status').json()
    settings = client.get('/api/settings').json()
    assert status['installed_robots'] == ['unitree_g1']
    assert settings['installed_robots'] == ['unitree_g1']
    assert settings['active_robot'] == 'unitree_g1'


def test_startup_recovers_existing_g1_native_artifacts_if_metadata_is_missing(tmp_path: Path):
    root = tmp_path / 'project'
    (root / 'frontend').mkdir(parents=True)
    (root / 'frontend/index.html').write_text('<html>Robot Web Lab</html>')
    artifacts = [
        root / 'build/native/prefix/lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake',
        root / 'third_party/unitree_rl_mjlab/simulate/build/rwl_mujoco_headless',
        root / 'third_party/unitree_rl_mjlab/deploy/robots/g1/build/g1_ctrl',
    ]
    for artifact in artifacts:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text('existing build artifact')
    client = TestClient(create_app(root, runtime=MockRuntimeAdapter(None, 0)))
    assert client.get('/api/build/status').json()['installed_robots'] == ['unitree_g1']
    settings = client.get('/api/settings').json()
    assert settings['active_robot'] == 'unitree_g1'
    assert settings['installed_robots'] == ['unitree_g1']
