from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')
JS = (ROOT / 'frontend' / 'app.js').read_text(encoding='utf-8')


def test_robot_manager_matches_build_manager_composition():
    for token in (
        'Robots / Build Manager',
        'id="robot-manager-preview-image"',
        'id="robot-manager-grid"',
        'Build Overview',
        'Installed Robots',
        'Build Queue',
        'Environment Details',
        'id="manager-build-selected"',
        'id="manager-rebuild-selected"',
    ):
        assert token in HTML
    assert '.robots-manager-shell' in CSS
    assert '.robot-manager-grid' in CSS
    assert 'function robotManagerCard(' in JS
    assert 'function renderRobotManagerDetail(' in JS


def test_robot_images_are_local_and_complete():
    assets = ROOT / 'frontend' / 'assets' / 'robots'
    for name in ('g1.png', 'g1_23dof.png', 'go2.png', 'h1_2.png', 'r1.png', 'h2.png', 'a2.png'):
        p = assets / name
        assert p.is_file()
        assert p.stat().st_size > 10_000
    assert '/static/assets/robots/' in JS
    assert 'unitree.com' not in JS


def test_clicking_manager_cards_updates_preview_and_build_selection_is_independent():
    assert "card.addEventListener('click'" in JS
    assert 'activeRobotManagerId=robot.id' in JS
    assert "check.onchange" in JS
    assert 'buildSelections.setSelected(robot.id,check.checked)' in JS


def test_app_module_has_valid_javascript_syntax():
    import shutil
    import subprocess
    import pytest

    node = shutil.which('node')
    if not node:
        pytest.skip('node is not available')
    result = subprocess.run(
        [node, '--input-type=module', '--check'],
        input=JS,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
