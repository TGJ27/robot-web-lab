from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_native_builder_disables_global_sdk_examples_and_only_builds_sim_target():
    source=(ROOT/'scripts/native_build.py').read_text()
    assert '-DBUILD_EXAMPLES=OFF' in source
    assert '"--target","rwl_mujoco_headless"' in source
    assert 'jstest' in source and 'Never build' in source
    assert 'g1_ctrl' in source

def test_g1_patch_contains_mimic_ub_and_real_hanger_fix():
    source=(ROOT/'scripts/apply_g1_patch.py').read_text()
    assert 'Eigen::Quaternionf::Identity()' in source
    assert 'const Eigen::Matrix3f rot' in source
    assert 'elastic_band.stiffness_ = 2500.0;' in source
    assert 'elastic_band.point_[2] += 0.10;' in source

def test_g1_patch_supports_browser_hanger_requests():
    source=(ROOT/'scripts/apply_g1_patch.py').read_text()
    assert 'web_hanger' in source
    assert 'poll_web_hanger' in source

def test_native_builder_applies_browser_state_bridge_before_simulator_build():
    source=(ROOT/'scripts/native_build.py').read_text()
    assert 'apply_web_state_patch.py' in source
    patch=(ROOT/'scripts/apply_web_state_patch.py').read_text()
    assert 'rwl_write_web_state' in patch
    assert 'native_state' in patch

def test_non_g1_build_disables_physical_joystick_and_g1_patch_reenables_virtual_keyboard():
    common=(ROOT/'scripts/apply_web_state_patch.py').read_text()
    g1=(ROOT/'scripts/apply_g1_patch.py').read_text()
    assert 'use_joystick: 0' in common
    assert 'use_joystick: 1' in g1

def test_browser_state_patch_supports_native_reset_request():
    patch=(ROOT/'scripts/apply_web_state_patch.py').read_text()
    assert 'web_runtime' in patch
    assert 'mj_resetData' in patch
    assert 'rwl_poll_runtime_action' in patch

def test_g1_hanger_poll_has_forward_declaration_before_physics_call():
    source=(ROOT/'scripts/apply_g1_patch.py').read_text()
    assert 'void poll_web_hanger();' in source
    # The patch must add a declaration before PhysicsLoop sees the call.
    decl_inject = "inline ElasticBand elastic_band;"
    assert decl_inject in source
    assert "band_singleton + '\\n\\nvoid poll_web_hanger();'" in source
    assert "assert main_text.index('void poll_web_hanger();') < main_text.index('poll_web_hanger();'" in source

def test_web_hanger_poll_is_in_outer_elastic_band_block_not_release_guard():
    source=(ROOT/'scripts/apply_g1_patch.py').read_text()
    assert 'physics_segment = re.sub' in source
    assert 'outer_band_needle' in source
    assert "outer_band_needle + '                  poll_web_hanger();\\n'" in source
    assert 'text = text[:physics_start] + physics_segment + text[physics_end:]' in source


def test_native_builder_builds_headless_mujoco_target_only():
    text = Path('scripts/native_build.py').read_text()
    assert 'rwl_mujoco_headless' in text
    assert '"--target","rwl_mujoco_headless"' in text.replace(' ', '')


def test_web_state_patch_generates_headless_source_without_render_loop():
    text = Path('scripts/apply_web_state_patch.py').read_text()
    assert 'rwl_headless_main.cc' in text
    assert 'rwl_mujoco_headless' in text
    assert 'RenderLoop' not in text


def test_headless_source_template_includes_math_and_algorithm_dependencies():
    text=(ROOT/'scripts/apply_web_state_patch.py').read_text()
    assert '#include <algorithm>' in text
    assert '#include <cmath>' in text


def test_headless_hanger_matches_validated_g1_hanger_semantics():
    text=(ROOT/'scripts/apply_web_state_patch.py').read_text()
    assert 'stiffness=2500.0' in text
    assert 'damping=300.0' in text
    assert 'point[2]=d->qpos[2]+0.50' in text.replace(' ','')
    assert 'length=0.50' in text

def test_headless_bridge_is_destroyed_before_mujoco_data(tmp_path):
    script=Path('scripts/apply_web_state_patch.py').read_text()
    assert 'bridge.reset();' in script
    assert script.index('bridge.reset();') < script.index('mj_deleteData(d)')
