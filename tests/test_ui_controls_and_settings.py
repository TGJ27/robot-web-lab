from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')
JS = (ROOT / 'frontend' / 'app.js').read_text(encoding='utf-8')
README = (ROOT / 'README.md').read_text(encoding='utf-8')


def test_release_version_is_current():
    assert 'v0.1.0' in HTML
    assert 'v0.1.0' in README


def test_high_level_exposes_only_three_fsm_mode_buttons():
    block = HTML.split('id="high-level-view"', 1)[1].split('<!-- LOW LEVEL', 1)[0]
    assert block.count('data-fsm=') == 3
    assert 'data-fsm="Passive"' in block
    assert 'data-fsm="FixStand"' in block
    assert 'data-fsm="Velocity"' in block
    assert 'id="mimic-open"' not in block
    assert 'id="ll-debug-enter"' not in block


def test_dance1_is_presented_as_policy_with_u_shortcut():
    assert 'data-run-policy="dance1_subject2"' in HTML
    assert 'Dance1 Subject2' in HTML
    assert 'data-key-for="dance_default"' in HTML
    assert "runPolicy('dance1_subject2')" in JS or 'runPolicy(policyId)' in JS


def test_level_toggle_performs_control_transition_instead_of_view_only():
    assert "api('/api/control/ll-prepare'" in JS
    assert "api('/api/control/passive'" in JS
    assert "$('#level-high').onclick=()=>switchLevel('high')" in JS
    assert "$('#level-low').onclick=()=>switchLevel('low')" in JS
    assert 'async function switchLevel' in JS


def test_high_level_accordion_is_exclusive():
    assert 'data-exclusive-group="hl"' in HTML
    assert 'initExclusiveAccordion' in JS
    assert "details[data-exclusive-group=\"hl\"]" in JS
    assert 'Expand All' not in HTML.split('id="high-level-view"', 1)[1].split('<!-- LOW LEVEL', 1)[0]


def test_settings_is_full_workspace_with_left_navigation_and_right_panels():
    block = HTML.split('id="settings-view"', 1)[1].split('</section>', 1)[0]
    assert 'settings-layout' in block
    assert 'settings-sidebar' in block
    assert 'settings-content' in block
    for section in ('general', 'robots', 'simulation', 'keyboard', 'appearance', 'paths', 'safety', 'advanced'):
        assert f'data-settings-section="{section}"' in block
        assert f'data-settings-panel="{section}"' in block
    assert '.workspace.mode-settings' in CSS
    assert '.workspace.mode-settings #simulation-viewport{display:none}' in CSS
    assert '.settings-layout{' in CSS
    assert '.settings-sidebar{' in CSS


def test_settings_and_panel_storage_use_current_namespace():
    assert 'rwl-v010-panel:' in JS
    assert 'rwl-v010-layout-saved-at' in JS
