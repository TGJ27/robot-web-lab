from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'frontend' / 'build_selection.js'


def test_build_selection_survives_rerender_seed():
    script = f"""
      import {{ BuildSelectionStore }} from {json.dumps(MODULE.as_uri())};
      const store = new BuildSelectionStore();
      store.ensure('g1', {{ highLevel: true, lowLevel: true }});
      store.setSelected('g1', true);
      store.setPack('g1', 'highLevel', true);
      store.setPack('g1', 'lowLevel', false);
      store.ensure('g1', {{ highLevel: true, lowLevel: true }});
      process.stdout.write(JSON.stringify(store.get('g1')));
    """
    result = subprocess.run(
        ['node', '--input-type=module', '-e', script],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state == {'selected': True, 'highLevel': True, 'lowLevel': False}


def test_build_selection_can_be_read_for_request_payload():
    script = f"""
      import {{ BuildSelectionStore }} from {json.dumps(MODULE.as_uri())};
      const store = new BuildSelectionStore();
      store.ensure('g1', {{ highLevel: true, lowLevel: true }});
      store.ensure('r1', {{ highLevel: true, lowLevel: true }});
      store.setSelected('g1', true);
      store.setSelected('r1', false);
      process.stdout.write(JSON.stringify(store.selectedItems()));
    """
    result = subprocess.run(
        ['node', '--input-type=module', '-e', script],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {'robot_id': 'g1', 'high_level': True, 'low_level': True},
    ]
