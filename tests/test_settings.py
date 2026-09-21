from pathlib import Path

import pytest

from backend.registry import RobotRegistry
from backend.settings import SettingsStore, KeyConflictError


def test_robot_registry_contains_g1_and_multiple_future_robots():
    registry = RobotRegistry.default()
    ids = {robot.id for robot in registry.list()}
    assert {"unitree_g1", "unitree_r1", "unitree_go2", "unitree_h1", "unitree_h2", "unitree_a2"} <= ids
    assert registry.get("unitree_g1").joint_count == 29
    assert registry.get("unitree_r1").sdk_example_path == "example/r1/low_level"
    assert registry.get("unitree_r1").supports_low_level is True
    assert registry.get("unitree_r1").joint_count == 26


def test_settings_defaults_and_persist(tmp_path: Path):
    store = SettingsStore(tmp_path / "settings.json", RobotRegistry.default())
    settings = store.load()
    assert settings.theme == "light"
    assert settings.active_robot is None
    assert settings.ui_level == "high"
    assert settings.keymap["passive"] == "1"

    settings.theme = "light"
    store.save(settings)

    loaded = store.load()
    assert loaded.theme == "light"
    assert loaded.active_robot is None


def test_key_remap_rejects_duplicate_without_resolution(tmp_path: Path):
    store = SettingsStore(tmp_path / "settings.json", RobotRegistry.default())
    settings = store.load()
    with pytest.raises(KeyConflictError) as exc:
        store.remap_key(settings, "hanger_raise", "1", resolution="reject")
    assert exc.value.existing_action == "passive"


def test_key_remap_replace_and_swap(tmp_path: Path):
    store = SettingsStore(tmp_path / "settings.json", RobotRegistry.default())
    settings = store.load()

    store.remap_key(settings, "hanger_raise", "1", resolution="replace")
    assert settings.keymap["hanger_raise"] == "1"
    assert "passive" not in settings.keymap

    settings = store.default_settings()
    passive_key = settings.keymap["passive"]
    raise_key = settings.keymap["hanger_raise"]
    store.remap_key(settings, "hanger_raise", passive_key, resolution="swap")
    assert settings.keymap["hanger_raise"] == passive_key
    assert settings.keymap["passive"] == raise_key

def test_default_theme_is_light_for_mockup_release(tmp_path):
    from backend.settings import SettingsStore
    from backend.registry import RobotRegistry
    store = SettingsStore(tmp_path / 'settings.json', RobotRegistry.default())
    assert store.default_settings().theme == 'light'


def test_legacy_mimic_key_is_migrated_to_default_dance(tmp_path: Path):
    import json
    store = SettingsStore(tmp_path / 'settings.json', RobotRegistry.default())
    payload = {
        'theme': 'light',
        'active_robot': None,
        'ui_level': 'high',
        'installed_robots': [],
        'keymap': {
            'passive': '1', 'fix_stand': '2', 'velocity': '3', 'mimic': 'U',
            'enter_ll_debug': '0', 'forward': 'W', 'backward': 'S', 'left': 'A',
            'right': 'D', 'yaw_left': 'Q', 'yaw_right': 'E',
            'hanger_attach': 'ArrowLeft', 'hanger_release': 'ArrowRight',
            'hanger_raise': 'ArrowUp', 'hanger_lower': 'ArrowDown', 'reset': 'R',
        },
    }
    store.path.write_text(json.dumps(payload), encoding='utf-8')
    loaded = store.load()
    assert loaded.keymap['dance_default'] == 'U'
    assert 'mimic' not in loaded.keymap


def test_keymap_replace_stays_removed_after_reload(tmp_path: Path):
    store = SettingsStore(tmp_path / 'settings.json', RobotRegistry.default())
    settings = store.load()
    store.remap_key(settings, 'hanger_raise', '1', resolution='replace')
    store.save(settings)
    loaded = store.load()
    assert loaded.keymap['hanger_raise'] == '1'
    assert 'passive' not in loaded.keymap
