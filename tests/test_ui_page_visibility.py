from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')
JS = (ROOT / 'frontend' / 'app.js').read_text(encoding='utf-8')
README = (ROOT / 'README.md').read_text(encoding='utf-8')


def test_release_version_is_current():
    assert 'v0.1.0' in HTML
    assert 'v0.1.0' in README


def test_hidden_page_views_always_win_over_layout_display_rules():
    # Full-page workspaces must never leak into another workspace simply because
    # their layout rule sets display:grid/flex.
    assert '.page-view[hidden]{display:none!important}' in CSS.replace(' ', '')


def test_settings_is_only_unhidden_from_show_page_settings_branch():
    branch = JS.split("else if(page==='settings')", 1)[1].split("else if(page==='examples')", 1)[0]
    assert "$('#settings-view').hidden=false" in branch
    assert "$$('.page-view').forEach(x=>x.hidden=true)" in JS
