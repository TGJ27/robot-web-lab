from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_first_run_setup_and_build_manager_surfaces_exist():
    html = text("frontend/index.html")
    for token in [
        'id="first-run-view"',
        'id="robot-build-grid"',
        'id="build-selected"',
        'id="build-progress"',
        'id="robots-view"',
        'id="installed-robots-list"',
    ]:
        assert token in html


def test_every_primary_menu_is_collapsible_except_viewport():
    html = text("frontend/index.html")
    assert 'id="simulation-viewport"' in html
    assert 'id="simulation-viewport"' in html and 'data-collapsible' not in html.split('id="simulation-viewport"',1)[1].split('>',1)[0]
    # HL sections, LL examples/editor/terminal/workflow, settings and asset panels use the common collapsible contract.
    assert html.count('data-collapsible') >= 10


def test_dark_and_light_theme_contract_remains():
    css = text("frontend/styles.css")
    assert ':root' in css
    assert '[data-theme="light"]' in css
    assert '[data-theme="dark"]' in css or 'html[data-theme="dark"]' in css
