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
    assert 'class="profile-button"' in html
    assert 'control-panel-heading' in html
    assert 'class="mockup-clean-shell"' in html
    assert '.mockup-clean-shell' in css
    assert '.control-panel-heading' in css
    assert '.profile-button' in css


def test_release_has_visible_version_marker():
    html = text('frontend/index.html')
    assert 'v0.1.0' in html

def test_launcher_repairs_missing_python_requirements_for_patch_updates():
    launcher = text('Robot-Web-Lab')
    assert 'import fastapi, uvicorn, pydantic, yaml' in launcher
    assert 'python -m pip install -r requirements.txt' in launcher
