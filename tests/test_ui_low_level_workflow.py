from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_low_level_workspace_is_code_first_and_terminal_is_resizable():
    html=(ROOT/'frontend/index.html').read_text()
    css=(ROOT/'frontend/styles.css').read_text()
    js=(ROOT/'frontend/app.js').read_text()
    assert 'id="ll-terminal-splitter"' in html
    assert '--ll-terminal-height:300px' in css.replace(' ','')
    assert '--ll-editor-width:56%' in css.replace(' ','')
    assert 'font:14px/1.5' in css.replace(' ','')
    assert "rwl-v010-ll-terminal-height" in js
    assert "bindHorizontal('#ll-terminal-splitter')" in js


def test_low_level_workflow_is_collapsed_by_default_and_viewport_survives_max_code():
    html=(ROOT/'frontend/index.html').read_text()
    css=(ROOT/'frontend/styles.css').read_text()
    workflow=html.split('id="ll-workflow-panel"',1)[1].split('>',1)[0]
    assert ' open' not in workflow
    max_block=css.split('.workspace.mode-low.editor-maximized',1)[1]
    assert '#simulation-viewport' not in max_block.split('@media',1)[0] or 'display:none' not in max_block.split('@media',1)[0]


def test_editor_focus_keeps_global_ll_shortcuts_and_exposes_focus_hint():
    html=(ROOT/'frontend/index.html').read_text()
    js=(ROOT/'frontend/app.js').read_text()
    assert 'id="keyboard-focus-state"' in html
    assert "e.ctrlKey&&(e.key==='0'||e.key==='1')" in js.replace(' ','')
    assert "e.target.matches('textarea,input,select')" in js
    assert 'Ctrl+0' in html and 'Ctrl+1' in html


def test_run_rebuild_confirmations_and_busy_button_states_exist():
    html=(ROOT/'frontend/index.html').read_text()
    js=(ROOT/'frontend/app.js').read_text()
    assert 'id="action-confirm-modal"' in html
    assert 'confirmAction' in js
    assert "status.built?'Rebuild':'Build'" in js.replace(' ','')
    assert "setLlBusy('building')" in js
    assert "setLlBusy('switching')" in js
    assert "setLlBusy('running')" in js
    assert "/api/control/ll-prepare" in js
    assert '/status?path=' in js


def test_websocket_close_stops_continuous_velocity_loop_before_reconnect():
    js=(ROOT/'frontend/app.js').read_text().replace(' ','')
    block=js.split('ws.onclose=()=>{',1)[1].split('}',1)[0]
    assert 'stopVelocityKeyboardLoop(true)' in block
    assert 'setTimeout(connectWs,1800)' in block
    assert block.index('stopVelocityKeyboardLoop(true)') < block.index('setTimeout(connectWs,1800)')


def test_stop_button_is_greyed_out_until_a_low_level_process_runs():
    html=(ROOT/'frontend/index.html').read_text()
    assert 'id="stop-source" class="danger" disabled' in html


def test_low_level_run_is_disabled_without_native_simulation():
    js=(ROOT/'frontend/app.js').read_text().replace(' ','')
    assert "run.disabled=!runnable||!status.built||!simulationStatus?.running" in js
