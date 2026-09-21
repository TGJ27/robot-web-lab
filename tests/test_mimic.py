from pathlib import Path

import pytest

from backend.mimic import MimicPolicyStore, UnsupportedPolicyFile


def test_upload_sanitizes_filename_and_lists_policy(tmp_path: Path):
    store = MimicPolicyStore(tmp_path / "policies")
    saved = store.save_bytes("unitree_g1", "../../Dance One.onnx", b"onnx-data")
    assert saved.name == "Dance_One.onnx"
    policies = store.list("unitree_g1")
    assert len(policies) == 1
    assert policies[0].name == "Dance One"
    assert policies[0].files == ["Dance_One.onnx"]


def test_related_files_are_grouped_by_stem(tmp_path: Path):
    store = MimicPolicyStore(tmp_path / "policies")
    store.save_bytes("unitree_g1", "wave.onnx", b"a")
    store.save_bytes("unitree_g1", "wave.npz", b"b")
    store.save_bytes("unitree_g1", "wave.yaml", b"c")
    policies = store.list("unitree_g1")
    assert len(policies) == 1
    assert policies[0].id == "wave"
    assert set(policies[0].files) == {"wave.onnx", "wave.npz", "wave.yaml"}


def test_rejects_unsupported_extension(tmp_path: Path):
    store = MimicPolicyStore(tmp_path / "policies")
    with pytest.raises(UnsupportedPolicyFile):
        store.save_bytes("unitree_g1", "evil.sh", b"echo nope")


def test_delete_removes_policy_group_only(tmp_path: Path):
    store = MimicPolicyStore(tmp_path / "policies")
    store.save_bytes("unitree_g1", "wave.onnx", b"a")
    store.save_bytes("unitree_g1", "wave.npz", b"b")
    store.save_bytes("unitree_g1", "dance.onnx", b"c")
    assert store.delete("unitree_g1", "wave") is True
    assert [p.id for p in store.list("unitree_g1")] == ["dance"]
    assert store.delete("unitree_g1", "missing") is False
