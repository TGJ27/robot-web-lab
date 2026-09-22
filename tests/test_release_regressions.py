from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_install_wait_for_apt_cannot_return_failure_when_no_lock_exists():
    sh = text('install.sh')
    block = sh.split('wait_for_apt() {',1)[1].split('\n}',1)[0]
    assert 'return 0' in block
    assert '(( waited > 0 )) && echo' not in block


def test_launcher_refuses_to_start_with_missing_browser_vendor_files():
    sh = text('Robot-Web-Lab')
    assert 'ensure_frontend_vendor' in sh
    assert 'three.module.js' in sh
    assert 'STLLoader.js' in sh


def test_installer_fetches_browser_vendor_before_native_dependency_step():
    sh = text('install.sh')
    main = sh.split('say "Robot Web Lab setup"',1)[1]
    assert main.index('scripts/fetch_three.py') < main.index('install_native_dependencies')


def test_ui_matches_approved_clean_mockup_contract():
    html = text('frontend/index.html')
    css = text('frontend/styles.css')
    assert 'id="save-layout-top"' in html
    assert 'class="profile-button"' not in html
    assert 'control-panel-heading' in html
    assert 'class="mockup-clean-shell"' in html
    assert '.mockup-clean-shell' in css
    assert '.control-panel-heading' in css
    assert '.profile-button' not in css


def test_release_has_visible_version_marker():
    html = text('frontend/index.html')
    assert 'v0.1.0' in html

def test_launcher_repairs_missing_python_requirements_for_patch_updates():
    launcher = text('Robot-Web-Lab')
    assert 'import fastapi, uvicorn, pydantic, yaml' in launcher
    assert 'python -m pip install -r requirements.txt' in launcher


def test_installer_runs_submodule_bootstrap_via_bash_without_init_repo_helper():
    sh=text('install.sh')
    assert 'bash "$ROOT/scripts/bootstrap_submodules.sh"' in sh
    assert 'init_git_repo.sh' not in sh


def test_multirobot_high_level_build_applies_generic_web_keyboard_bridge():
    root = Path(__file__).resolve().parents[1]
    native = (root / "scripts" / "native_build.py").read_text(encoding="utf-8")
    patch = (root / "scripts" / "apply_web_hl_patch.py").read_text(encoding="utf-8")
    assert "apply_web_hl_patch.py" in native
    assert "rwl_web_control::apply(lowstate->joystick);" in patch
    assert 'std::getenv("RWL_SIM_RUNTIME_DIR")' in patch
    for action in ("Passive", "FixStand", "Velocity"):
        assert action in patch


def test_supervisor_exports_generic_runtime_dir_for_all_controllers():
    root = Path(__file__).resolve().parents[1]
    supervisor = (root / "backend" / "supervisor.py").read_text(encoding="utf-8")
    assert "RWL_SIM_RUNTIME_DIR" in supervisor

def test_g1_23dof_mimic_web_pack_is_enabled():
    from backend.registry import RobotRegistry
    robot = RobotRegistry.default().get('unitree_g1_23dof')
    assert robot.supports_web_high_level is True
    assert robot.supports_mimic is True
    native = (ROOT / 'scripts' / 'native_build.py').read_text(encoding='utf-8')
    bridge = (ROOT / 'scripts' / 'apply_web_hl_patch.py').read_text(encoding='utf-8')
    assert 'apply_g1_23dof_mimic_patch.py' in native
    assert 'action == "Mimic"' in bridge
    assert 'joystick.RB(true)' in bridge and 'joystick.A(true)' in bridge
