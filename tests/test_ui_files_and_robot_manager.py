from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT/'frontend/index.html').read_text(encoding='utf-8')
CSS = (ROOT/'frontend/styles.css').read_text(encoding='utf-8')
JS = (ROOT/'frontend/app.js').read_text(encoding='utf-8')


def test_scripts_files_is_full_page_not_low_level_shortcut():
    assert 'data-page="scripts"' in HTML
    assert '>Scripts / Files<' in HTML
    assert 'id="scripts-view"' in HTML
    assert "page==='scripts'" in JS


def test_example_items_keep_icon_and_name_on_one_line():
    compact = CSS.replace(' ', '')
    assert '.example-item{display:flex' in compact
    assert 'white-space:nowrap' in compact
    assert 'text-overflow:ellipsis' in compact


def test_low_level_viewport_and_editor_are_balanced_with_wider_examples():
    compact = CSS.replace(' ', '')
    assert '--ll-examples-width:240px' in compact
    assert '--ll-editor-width:minmax(0,1fr)' in compact
    assert 'grid-template-columns:var(--ll-examples-width)6pxminmax(0,1fr)6pxvar(--ll-editor-width)' in compact


def test_robots_page_is_full_workspace_with_preview_cards_and_overview():
    assert 'robots-view-full' in HTML
    assert 'id="robot-manager-preview-image"' in HTML
    assert 'id="robot-manager-grid"' in HTML
    assert 'id="manager-build-selected"' in HTML
    assert 'Build Overview' in HTML
    assert 'Environment Details' in HTML
    assert '/static/assets/robots/g1.png' in JS


def test_builtin_examples_are_buildable_and_workspace_files_have_rename_delete():
    assert 'builtin:activeExample.builtin' in JS
    assert 'renameWorkspaceFile' in JS
    assert 'deleteWorkspaceFile' in JS
