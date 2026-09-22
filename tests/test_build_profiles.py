from pathlib import Path

from backend.build_profiles import BuildProfileStore
from backend.examples import ExampleService
from backend.registry import RobotRegistry
from backend.runner import LowLevelRunner


def test_copied_dual_arm_inherits_yaml_build_profile_across_rename(tmp_path: Path):
    sdk = tmp_path / 'sdk'
    builtin = sdk / 'example/g1/low_level/g1_dual_arm_example.cpp'
    builtin.parent.mkdir(parents=True)
    builtin.write_text('#include <yaml-cpp/yaml.h>\n#define DEMO 1\nint main(){return 0;}\n')
    workspace = tmp_path / 'workspace'
    profiles = BuildProfileStore(tmp_path / 'build_profiles.yaml')
    service = ExampleService(sdk, workspace, RobotRegistry.default())
    copied = service.copy_to_workspace('unitree_g1', 'g1_dual_arm_example.cpp', 'my_arm.cpp')
    profiles.inherit_copy('unitree_g1', 'g1_dual_arm_example.cpp', 'my_arm.cpp')
    renamed = service.rename_workspace('unitree_g1', 'my_arm.cpp', 'arm_lab.cpp')
    profiles.rename_workspace('unitree_g1', 'my_arm.cpp', 'arm_lab.cpp')

    runner = LowLevelRunner(workspace, sdk, owner=lambda:'low', registry=RobotRegistry.default(), profile_store=profiles)
    cmake = runner.cmake_project_for(renamed, robot_id='unitree_g1', relative_path='arm_lab.cpp', builtin=False)
    assert 'find_package(yaml-cpp REQUIRED)' in cmake
    assert 'yaml-cpp' in cmake
    assert 'BLIB_DIR' in cmake
    assert 'behavior_lib/' in cmake


def test_custom_yaml_include_is_detected_and_persisted(tmp_path: Path):
    store = BuildProfileStore(tmp_path / 'profiles.yaml')
    source = tmp_path / 'custom.cpp'
    source.write_text('#include <yaml-cpp/yaml.h>\n#define BLIB_DIR "x"\n')
    profile = store.resolve_profile('unitree_g1', 'custom.cpp', builtin=False, source_path=source)
    assert profile['name'] == 'g1_dual_arm'
    assert 'yaml-cpp' in profile['libraries']
    assert 'custom.cpp' in store.text()

def test_default_yaml_contains_builtin_profile_assignments(tmp_path: Path):
    store = BuildProfileStore(tmp_path / "build_profiles.yaml")
    text = store.text()
    assert "unitree_g1:builtin:g1_dual_arm_example.cpp: g1_dual_arm" in text
    assert "unitree_h2:builtin:h2_dual_arm_example.cpp: h2_dual_arm" in text
    assert "unitree_g1:builtin:terminations.cpp: terminations" in text
    assert store.assign_builtin("unitree_g1", "g1_dual_arm_example.cpp") == "g1_dual_arm"


def test_g1_23dof_shared_low_level_examples_get_special_profiles(tmp_path):
    store = BuildProfileStore(tmp_path / "profiles.yaml")
    dual = store.resolve_profile(
        "unitree_g1_23dof",
        "g1_dual_arm_example.cpp",
        builtin=True,
        source_path=tmp_path / "g1_dual_arm_example.cpp",
    )
    assert "unitree_sdk2" in dual["libraries"]
    assert "yaml-cpp" in dual["libraries"]
    assert dual["defines"]["BLIB_DIR"] == "${SDK_EXAMPLE_ROOT}/behavior_lib/"

    term = store.resolve_profile(
        "unitree_g1_23dof",
        "terminations.cpp",
        builtin=True,
        source_path=tmp_path / "terminations.cpp",
    )
    assert "Boost::program_options" in term["libraries"]
