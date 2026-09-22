from pathlib import Path
from backend.models import ModelService
from backend.registry import RobotDefinition, RobotRegistry


def test_mjcf_manifest_preserves_body_joint_and_mesh(tmp_path: Path):
    project=tmp_path/'project'; repo=project/'third_party/unitree_rl_mjlab'; model=repo/'models/robot.xml'; assets=repo/'models/assets'; assets.mkdir(parents=True)
    (assets/'leg.STL').write_bytes(b'stl')
    model.write_text('''<mujoco><compiler meshdir="assets"/><asset><mesh name="leg" file="leg.STL"/></asset><worldbody><body name="base" pos="0 0 1"><body name="leg_body" pos="0 0 -0.2"><joint name="hip" axis="0 1 0"/><geom type="mesh" mesh="leg" rgba="0.7 0.7 0.7 1"/></body></body></worldbody></mujoco>''')
    registry=RobotRegistry([RobotDefinition('r','Robot','humanoid','example',1,False,native_robot='r',model_xml='models/robot.xml')])
    svc=ModelService(project,registry)
    mf=svc.manifest('r')
    leg=mf['bodies'][0]['children'][0]
    assert leg['name']=='leg_body'
    assert leg['joint']['name']=='hip'
    assert leg['geoms'][0]['asset']=='assets/leg.STL'
    assert svc.asset_path('r','assets/leg.STL').read_bytes()==b'stl'

def test_scene_include_uses_included_robot_model_for_browser_manifest(tmp_path: Path):
    project=tmp_path/'project'; repo=project/'third_party/unitree_mujoco'; robot_dir=repo/'unitree_robots/r1'; meshes=robot_dir/'meshes'; meshes.mkdir(parents=True)
    (robot_dir/'scene.xml').write_text('<mujoco><include file="R1.xml"/><worldbody><geom type="plane"/></worldbody></mujoco>')
    (meshes/'body.STL').write_bytes(b'stl')
    (robot_dir/'R1.xml').write_text('<mujoco><compiler meshdir="meshes"/><asset><mesh name="body" file="body.STL"/></asset><worldbody><body name="base"><geom type="mesh" mesh="body"/></body></worldbody></mujoco>')
    registry=RobotRegistry([RobotDefinition('r','R1','humanoid','example',1,False,native_robot='r1',model_xml='unitree_robots/r1/scene.xml',model_repo='unitree_mujoco')])
    svc=ModelService(project,registry)
    mf=svc.manifest('r')
    assert mf['bodies'][0]['name']=='base'
    assert svc.asset_path('r','meshes/body.STL').is_file()


def test_unnamed_obj_mesh_uses_filename_stem_and_material_color(tmp_path: Path):
    project=tmp_path/'project'; repo=project/'third_party/unitree_rl_mjlab'; model=repo/'models/go2.xml'; assets=repo/'models/assets'; assets.mkdir(parents=True)
    (assets/'base_0.obj').write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    model.write_text('''<mujoco><compiler meshdir="assets"/><asset><material name="black" rgba="0 0 0 1"/><mesh file="base_0.obj"/></asset><worldbody><body name="base"><geom mesh="base_0" material="black"/></body></worldbody></mujoco>''')
    registry=RobotRegistry([RobotDefinition('go2','Go2','quadruped','example',12,True,native_robot='go2',model_xml='models/go2.xml')])
    svc=ModelService(project,registry)
    mf=svc.manifest('go2')
    geom=mf['bodies'][0]['geoms'][0]
    assert geom['asset']=='assets/base_0.obj'
    assert geom['rgba']==[0.0,0.0,0.0,1.0]
    assert svc.asset_path('go2','assets/base_0.obj').is_file()


def test_g1_23dof_only_exposes_ankle_swing_low_level_example():
    robot = RobotRegistry.default().get("unitree_g1_23dof")
    assert robot.supports_low_level is True
    assert robot.sdk_example_path == "example/g1/low_level"
    assert robot.sdk_example_files == ("g1_ankle_swing_example.cpp",)
