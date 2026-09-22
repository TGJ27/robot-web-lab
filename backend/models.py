from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from .registry import RobotRegistry


def _vec(text: str | None, n: int, default: list[float]) -> list[float]:
    if not text:
        return list(default)
    vals=[float(x) for x in text.split()]
    return (vals+default)[:n]


class ModelService:
    def __init__(self, project_root: Path, registry: RobotRegistry):
        self.project_root=Path(project_root).resolve(); self.registry=registry

    def model_path(self, robot_id: str) -> Path:
        robot=self.registry.get(robot_id)
        if not robot.model_xml: raise FileNotFoundError(f"No browser model configured for {robot.display_name}")
        repo=(self.project_root/"third_party"/robot.model_repo).resolve()
        path=(repo/robot.model_xml).resolve()
        if repo != path and repo not in path.parents: raise ValueError("Model path escapes Unitree repo")
        if not path.is_file(): raise FileNotFoundError(path)
        return path

    def visual_model_path(self, robot_id: str) -> Path:
        path=self.model_path(robot_id)
        root=ET.parse(path).getroot()
        if root.find("worldbody") is not None and root.find("worldbody").find("body") is not None:
            return path
        include=root.find("include")
        if include is not None and include.get("file"):
            included=(path.parent/include.get("file")).resolve()
            if path.parent != included and path.parent not in included.parents: raise ValueError("Included model escapes robot directory")
            if included.is_file(): return included
        return path

    def manifest(self, robot_id: str) -> dict:
        path=self.visual_model_path(robot_id); tree=ET.parse(path); root=tree.getroot()
        compiler=root.find("compiler"); meshdir=Path(compiler.get("meshdir","")) if compiler is not None else Path()
        meshes={}
        materials={}
        asset=root.find("asset")
        if asset is not None:
            for material in asset.findall("material"):
                name=material.get("name")
                if name:
                    materials[name]=_vec(material.get("rgba"),4,[0.72,0.74,0.78,1])
            for mesh in asset.findall("mesh"):
                filename=mesh.get("file")
                # MuJoCo defaults an unnamed mesh asset to the source filename stem.
                # Go2's pinned MJCF relies on that behavior (e.g. base_0.obj -> base_0).
                name=mesh.get("name") or (Path(filename).stem if filename else None)
                if name and filename:
                    rel=(meshdir/filename).as_posix(); meshes[name]={"asset":rel,"scale":_vec(mesh.get("scale"),3,[1,1,1])}

        def parse_body(node: ET.Element) -> dict:
            joints=node.findall("joint"); joint=None
            for j in joints:
                if j.get("type","hinge") != "free":
                    joint={"name":j.get("name",node.get("name","joint")),"type":j.get("type","hinge"),"axis":_vec(j.get("axis"),3,[0,0,1]),"pos":_vec(j.get("pos"),3,[0,0,0])}; break
            geoms=[]
            for g in node.findall("geom"):
                mesh_name=g.get("mesh")
                if not mesh_name or mesh_name not in meshes: continue
                m=meshes[mesh_name]
                geoms.append({"mesh":mesh_name,"asset":m["asset"],"scale":m["scale"],"pos":_vec(g.get("pos"),3,[0,0,0]),"quat":_vec(g.get("quat"),4,[1,0,0,0]),"rgba":_vec(g.get("rgba"),4,materials.get(g.get("material",""),[0.72,0.74,0.78,1]))})
            return {"name":node.get("name","body"),"pos":_vec(node.get("pos"),3,[0,0,0]),"quat":_vec(node.get("quat"),4,[1,0,0,0]),"joint":joint,"geoms":geoms,"children":[parse_body(b) for b in node.findall("body")]}

        world=root.find("worldbody")
        bodies=[] if world is None else [parse_body(b) for b in world.findall("body")]
        return {"robot_id":robot_id,"source":self.registry.get(robot_id).model_xml,"bodies":bodies}

    def asset_path(self, robot_id: str, relative: str) -> Path:
        model=self.visual_model_path(robot_id); candidate=(model.parent/relative).resolve()
        # Assets must stay below the robot model directory.
        if model.parent != candidate and model.parent not in candidate.parents: raise ValueError("Asset path escapes robot model directory")
        if not candidate.is_file(): raise FileNotFoundError(candidate)
        return candidate
