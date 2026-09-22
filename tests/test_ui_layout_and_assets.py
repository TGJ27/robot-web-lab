from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'frontend' / 'index.html').read_text()
CSS = (ROOT / 'frontend' / 'styles.css').read_text()
JS = (ROOT / 'frontend' / 'app.js').read_text()


def test_release_version_is_current():
    assert 'v0.1.0' in HTML
    assert 'v0.1.0' in (ROOT / 'README.md').read_text()


def test_low_level_workspace_is_code_first_and_terminal_is_roomy():
    assert '--ll-editor-width:56%' in CSS
    assert '--ll-terminal-height:300px' in CSS
    assert 'minmax(560px,var(--ll-editor-width))' in CSS
    assert '#code-editor{width:100%;height:100%;min-height:0' in CSS
    assert '.ll-editor-panel[open]>.collapse-body' in CSS and 'height:calc(100% - 44px)' in CSS
    assert 'font:14px/1.5 ui-monospace' in CSS


def test_scrollable_panels_are_never_clipped():
    assert 'scrollbar-gutter:stable' in CSS
    assert '.high-level-view{' in CSS and 'overflow-y:auto' in CSS
    assert '.collapse-card[open]>.collapse-body' in CSS
    assert 'overflow:auto' in CSS
    assert '.console-panel .collapse-body' in CSS
    assert '.terminal{margin:0;min-height:0;flex:1;overflow:auto' in CSS


def test_light_theme_uses_neutral_surfaces_not_pure_white_shell():
    assert '--bg:#e7ecf2' in CSS
    assert '--panel:#f7f9fc' in CSS
    assert '--panel2:#f0f3f7' in CSS
    assert '--panel3:#e8edf3' in CSS
    assert '[data-theme="light"] .topbar{background:#f8fafc' in CSS


def test_robot_cards_use_local_robot_assets_with_fallback():
    assert 'ROBOT_PHOTOS' in JS
    for robot in ('unitree_g1', 'unitree_g1_23dof', 'unitree_go2', 'unitree_h1', 'unitree_r1', 'unitree_a2', 'unitree_h2'):
        assert f"{robot}:" in JS
    assert '/static/assets/robots/' in JS
    assert 'unitree.com' not in JS
    assert 'robot-card-photo' in JS
    assert 'robot-photo-fallback' in JS


def test_terminal_tabs_are_real_and_have_named_buffers():
    for tab in ('logs', 'build', 'lowstate', 'dds'):
        assert f'data-terminal-tab="{tab}"' in HTML
    assert 'terminalBuffers' in JS
    assert 'selectTerminalTab' in JS
    assert 'appendTerminal' in JS
    assert "terminalBuffers.build" in JS


def test_terminal_toolbar_wraps_instead_of_clipping_controls():
    assert '.terminal-tabs{flex:0 0 auto;display:flex;align-items:center;gap:6px' in CSS
    assert 'flex-wrap:wrap' in CSS
    assert '.terminal-tabs-spacer{flex:1 1 18px' in CSS
    assert '.terminal-autoscroll{' in CSS and 'margin-left:auto' in CSS


def test_high_level_console_has_more_default_space():
    assert '--high-console-height:250px' in CSS
    assert 'grid-template-rows:minmax(0,1fr) var(--high-console-height)' in CSS


def test_panel_state_storage_migrates_to_current_release():
    assert 'rwl-v010-panel:' in JS
    assert 'rwl-v010-ll-examples-width' in JS
    assert 'rwl-v010-ll-editor-width' in JS
    assert 'rwl-v010-ll-terminal-height' in JS


def test_browser_model_view_supports_obj_assets_for_go2():
    js=(ROOT / 'frontend' / 'robot_view.js').read_text(encoding='utf-8')
    assert 'parseObjGeometry' in js
    assert "endsWith('.obj')" in js


def test_follow_camera_targets_robot_body_center():
    js=(ROOT / 'frontend' / 'robot_view.js').read_text(encoding='utf-8')
    assert 'worldTarget.y+=.82' not in js
    assert "floating base is the robot's body center" in js
