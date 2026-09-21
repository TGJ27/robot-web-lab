from pathlib import Path
from backend.runner import LowLevelRunner
from backend.build_profiles import BuildProfileStore


def test_cpp_runner_prefers_preinstalled_sdk_prefix(tmp_path: Path):
    workspace = tmp_path / "workspace"
    sdk = tmp_path / "sdk"
    prefix = tmp_path / "prefix"
    (workspace / "g1").mkdir(parents=True)
    sdk.mkdir()
    config = prefix / "lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake"
    config.parent.mkdir(parents=True)
    config.write_text("# fake config")
    source = workspace / "g1/test.cpp"
    source.write_text("int main(){return 0;}")
    runner = LowLevelRunner(workspace, sdk, lambda: "low", sdk_prefix=prefix)
    # Build generation is isolated from actual cmake invocation.
    cmake_text = runner.cmake_project_for(source)
    assert "find_package(unitree_sdk2 REQUIRED)" in cmake_text
    assert str(prefix) in cmake_text
    assert "add_subdirectory" not in cmake_text


def test_cpp_runner_adds_robot_low_level_include_directory(tmp_path: Path):
    workspace = tmp_path / "workspace"
    sdk = tmp_path / "sdk"
    source = workspace / "unitree_r1/r1_ankle_swing_example.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("#include \"gamepad.hpp\"\nint main(){return 0;}\n")
    (sdk / "example/r1/low_level").mkdir(parents=True)
    runner = LowLevelRunner(workspace, sdk, lambda: "low")
    cmake_text = runner.cmake_project_for(source)
    assert f'target_include_directories(rwl_r1_ankle_swing_example PRIVATE "{(sdk / "example/r1/low_level").as_posix()}")' in cmake_text


def test_cpp_runner_adds_yaml_metadata_for_g1_dual_arm(tmp_path: Path):
    workspace = tmp_path / "workspace"
    sdk = tmp_path / "sdk"
    source = workspace / "unitree_g1/g1_dual_arm_example.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main(){return 0;}\n")
    low = sdk / "example/g1/low_level"
    low.mkdir(parents=True)
    profiles = BuildProfileStore(tmp_path / "build_profiles.yaml")
    profiles.assign_workspace("unitree_g1", "g1_dual_arm_example.cpp", source_path=source, profile="g1_dual_arm")
    runner = LowLevelRunner(workspace, sdk, lambda: "low", profile_store=profiles)
    cmake_text = runner.cmake_project_for(source, robot_id="unitree_g1", relative_path="g1_dual_arm_example.cpp", builtin=False)
    assert "find_package(yaml-cpp REQUIRED)" in cmake_text
    assert "unitree_sdk2 yaml-cpp" in cmake_text
    assert f'BLIB_DIR=\\\"{(low / "behavior_lib").as_posix()}/\\\"' in cmake_text


def test_cpp_runner_adds_yaml_metadata_for_h2_dual_arm(tmp_path: Path):
    workspace = tmp_path / "workspace"
    sdk = tmp_path / "sdk"
    source = workspace / "unitree_h2/h2_dual_arm_example.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main(){return 0;}\n")
    low = sdk / "example/h2/low_level"
    low.mkdir(parents=True)
    profiles = BuildProfileStore(tmp_path / "build_profiles.yaml")
    profiles.assign_workspace("unitree_h2", "h2_dual_arm_example.cpp", source_path=source, profile="h2_dual_arm")
    runner = LowLevelRunner(workspace, sdk, lambda: "low", profile_store=profiles)
    cmake_text = runner.cmake_project_for(source, robot_id="unitree_h2", relative_path="h2_dual_arm_example.cpp", builtin=False)
    assert "find_package(yaml-cpp REQUIRED)" in cmake_text
    assert "unitree_sdk2 yaml-cpp" in cmake_text
    assert f'H2_DUAL_ARM_BEHAVIOR_DIR=\\\"{(low / "behavior_lib").as_posix()}/\\\"' in cmake_text


def test_cpp_runner_adds_boost_for_termination_examples(tmp_path: Path):
    workspace = tmp_path / "workspace"
    sdk = tmp_path / "sdk"
    source = workspace / "unitree_g1/terminations.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main(){return 0;}\n")
    (sdk / "example/g1/low_level").mkdir(parents=True)
    profiles = BuildProfileStore(tmp_path / "build_profiles.yaml")
    profiles.assign_workspace("unitree_g1", "terminations.cpp", source_path=source, profile="terminations")
    runner = LowLevelRunner(workspace, sdk, lambda: "low", profile_store=profiles)
    cmake_text = runner.cmake_project_for(source, robot_id="unitree_g1", relative_path="terminations.cpp", builtin=False)
    assert "find_package(Boost REQUIRED COMPONENTS program_options)" in cmake_text
    assert "unitree_sdk2 Boost::program_options" in cmake_text


def test_python_runner_uses_current_conda_interpreter(tmp_path):
    import sys
    from backend.runner import LowLevelRunner
    root=tmp_path/'workspace'
    src=root/'g1'/'hello.py'
    src.parent.mkdir(parents=True)
    src.write_text('print("ok")\n')
    runner=LowLevelRunner(root,tmp_path/'sdk',owner=lambda:'low')
    cmd=runner.command_for(src,'lo')
    assert cmd[0] == sys.executable
