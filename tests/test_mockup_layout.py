from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'frontend' / 'index.html').read_text()
CSS = (ROOT / 'frontend' / 'styles.css').read_text()
JS = (ROOT / 'frontend' / 'app.js').read_text()


def test_workspace_uses_approved_page_specific_layouts():
    assert 'id="workspace"' in HTML
    assert 'class="first-run-main"' in HTML
    assert 'class="first-run-overview"' in HTML
    assert 'id="ll-examples-panel"' in HTML
    assert 'id="ll-editor-panel"' in HTML
    assert 'id="ll-workflow-panel"' in HTML
    assert 'id="console-panel"' in HTML
    assert '.workspace.mode-first' in CSS
    assert '.workspace.mode-high' in CSS
    assert '.workspace.mode-low' in CSS
    assert 'grid-template-areas' in CSS


def test_viewport_is_the_only_primary_non_collapsible_panel():
    assert '<section id="simulation-viewport"' in HTML
    assert '<details id="ll-examples-panel"' in HTML
    assert '<details id="ll-editor-panel"' in HTML
    assert '<details id="ll-workflow-panel"' in HTML
    assert '<details id="console-panel"' in HTML
    assert 'data-collapsible' in HTML


def test_frontend_switches_workspace_layout_mode():
    assert 'function setWorkspaceMode(' in JS
    assert "setWorkspaceMode('first')" in JS
    assert "setWorkspaceMode(level==='low'?'low':'high')" in JS
    assert "setWorkspaceMode(level==='low'?'low':'high')" in JS

def test_first_run_matches_approved_setup_composition():
    assert '<html lang="en" data-theme="light">' in HTML
    assert 'Welcome / First Run Setup' in HTML
    assert 'Available Robots' in HTML
    assert 'Installation Options' in HTML
    assert 'id="global-pack-high"' in HTML
    assert 'id="global-pack-low"' in HTML
    assert 'robot-card-photo' in JS and 'robot-photo-fallback robot-card-visual' in JS
    # Package choices live in the dedicated Installation Options area, not repeated in every card.
    assert 'class="pack-hl"' not in JS
    assert 'class="pack-ll"' not in JS


def test_layout_storage_is_versioned_for_current_release():
    assert 'rwl-v010-panel:' in JS
