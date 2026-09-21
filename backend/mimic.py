from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


ALLOWED_EXTENSIONS = {".onnx", ".npz", ".yaml", ".yml", ".json"}


class UnsupportedPolicyFile(ValueError):
    pass


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem).strip("._") or "policy"
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UnsupportedPolicyFile(f"Unsupported mimic policy file type: {suffix or '<none>'}")
    return stem + suffix


@dataclass(frozen=True)
class MimicPolicy:
    id: str
    name: str
    files: list[str]
    ready: bool


class MimicPolicyStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def robot_root(self, robot_id: str) -> Path:
        safe_robot = re.sub(r"[^A-Za-z0-9_.-]+", "_", robot_id)
        path = self.root / safe_robot
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_bytes(self, robot_id: str, filename: str, data: bytes) -> Path:
        safe_name = _safe_filename(filename)
        path = self.robot_root(robot_id) / safe_name
        path.write_bytes(data)
        return path

    def list(self, robot_id: str) -> list[MimicPolicy]:
        root = self.robot_root(robot_id)
        groups: dict[str, list[Path]] = {}
        for path in sorted(root.iterdir()):
            if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS:
                groups.setdefault(path.stem, []).append(path)
        result: list[MimicPolicy] = []
        for stem, paths in sorted(groups.items()):
            display = stem.replace("_", " ")
            display = " ".join(word.capitalize() if word.islower() else word for word in display.split())
            result.append(
                MimicPolicy(
                    id=stem,
                    name=display,
                    files=[path.name for path in paths],
                    ready=any(path.suffix.lower() == ".onnx" for path in paths),
                )
            )
        return result

    def delete(self, robot_id: str, policy_id: str) -> bool:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", policy_id)
        removed = False
        for path in list(self.robot_root(robot_id).iterdir()):
            if path.is_file() and path.stem == safe_id and path.suffix.lower() in ALLOWED_EXTENSIONS:
                path.unlink()
                removed = True
        return removed
