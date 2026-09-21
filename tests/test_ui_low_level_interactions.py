from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')
JS = (ROOT / 'frontend' / 'app.js').read_text(encoding='utf-8')
VIEW = (ROOT / 'frontend' / 'robot_view.js').read_text(encoding='utf-8')


def test_low_level_layout_is_code_first_and_resizable():
    assert 'id="ll-left-splitter"' in HTML
    assert 'id="ll-right-splitter"' in HTML
    assert 'data-splitter="low-left"' in HTML
    assert 'data-splitter="low-right"' in HTML
    assert '--ll-examples-width' in CSS
    assert '--ll-editor-width' in CSS
    assert 'minmax(520px,var(--ll-editor-width))' in CSS
    assert 'initSplitters' in JS


def test_low_level_editor_has_focus_and_expand_controls():
    assert 'id="editor-focus"' in HTML
    assert 'id="editor-maximize"' in HTML
    assert 'toggleEditorFocus' in JS
    assert 'toggleEditorMaximize' in JS


def test_browser_keyboard_velocity_is_hold_to_drive_not_one_shot():
    for token in ['velocityKeys', 'startVelocityKeyboardLoop', 'stopVelocityKeyboardLoop', 'keydown', 'keyup']:
        assert token in JS
    for action in ['forward', 'backward', 'left', 'right', 'yaw_left', 'yaw_right']:
        assert action in JS
    assert 'settings?.keymap' in JS
    assert "state?.fsm_mode!=='Velocity'" in JS


def test_follow_camera_tracks_live_robot_base_pose():
    assert 'setFollowEnabled' in VIEW
    assert 'this.followEnabled' in VIEW
    assert 'this.target.copy' in VIEW
    assert "id=\"follow-camera\"" in HTML
    assert 'setFollowEnabled' in JS


def test_viewport_status_makes_native_state_source_clear():
    assert 'id="viewport-live-source"' in HTML
    assert 'Live MuJoCo' in HTML
