from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_index_has_required_high_and_low_level_surfaces():
    html = text("frontend/index.html")
    for required in [
        'id="robot-select"', 'id="level-high"', 'id="level-low"',
        'id="high-level-view"', 'id="low-level-view"',
        'id="mimic-drop-zone"', 'id="keymap-list"', 'id="examples-tree"',
        'id="code-editor"', 'id="terminal-output"', 'id="theme-toggle"',
        'id="first-run-view"', 'id="robots-view"', 'id="simulation-viewport"',
    ]:
        assert required in html


def test_every_menu_is_collapsible_except_3d_viewport_and_themes_exist():
    html = text("frontend/index.html")
    css = text("frontend/styles.css")
    assert html.count('data-collapsible') >= 10
    viewport_tag = html.split('id="simulation-viewport"', 1)[1].split('>', 1)[0]
    assert 'data-collapsible' not in viewport_tag
    assert '[data-theme="light"]' in css
    assert '[data-theme="dark"]' in css or ':root' in css
    assert '.duplicate-modal' in css


def test_frontend_js_uses_api_and_duplicate_resolution_workflow():
    js = text("frontend/app.js")
    for token in [
        '/api/robots', '/api/settings/keymap', '/api/mimic/', '/api/examples/',
        'captureKeyForAction', 'resolveKeyConflict', 'copyExampleToWorkspace', 'switchLevel',
        '/api/build/start', '/api/simulation/start/', '/api/simulation/stop',
    ]:
        assert token in js


def test_viewport_module_loads_local_threejs_and_real_unitree_stl_assets():
    renderer = text("frontend/robot_view.js")
    assert './vendor/three.module.js' in renderer
    assert './vendor/STLLoader.js' in renderer
    assert 'UnitreeModelView' in renderer
    assert '/api/model/' in renderer


def test_dance_policy_replaces_generic_mimic_mode_button():
    js = text("frontend/app.js")
    html = text("frontend/index.html")
    assert "runPolicy('dance1_subject2')" in js
    assert 'data-run-policy="dance1_subject2"' in html
    assert "setFsm('Mimic')" not in js

def test_frontend_wires_reset_key_to_native_reset_api():
    app=(ROOT/'frontend/app.js').read_text()
    assert "action==='reset'" in app
    assert "'/api/control/reset'" in app

def test_frontend_periodically_refreshes_native_simulation_status():
    app=(ROOT/'frontend/app.js').read_text()
    assert 'pollSimulationStatus' in app
    assert "api('/api/simulation/status')" in app
    assert 'setInterval(pollSimulationStatus' in app

def test_build_card_selection_is_kept_outside_polled_dom_renders():
    app = text('frontend/app.js')
    assert 'new BuildSelectionStore()' in app
    assert 'buildSelections.setSelected' in app
    assert 'buildSelections.setPack' in app
    assert 'return buildSelections.selectedItems()' in app
