from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.runtime import MockRuntimeAdapter


def make_client(tmp_path: Path):
    root = tmp_path / "project"
    (root / "frontend").mkdir(parents=True)
    (root / "frontend/index.html").write_text("<html>Robot Web Lab</html>")
    return TestClient(create_app(root, runtime=MockRuntimeAdapter(None, 0)))


def test_fresh_install_has_no_active_or_installed_robot(tmp_path: Path):
    client = make_client(tmp_path)
    settings = client.get("/api/settings").json()
    assert settings["installed_robots"] == []
    assert settings["active_robot"] is None
    assert client.get("/api/build/status").json()["installed_robots"] == []


def test_robot_catalog_is_available_before_build(tmp_path: Path):
    client = make_client(tmp_path)
    robots = client.get("/api/robots").json()
    ids = {r["id"] for r in robots}
    assert {"unitree_g1", "unitree_r1", "unitree_go2", "unitree_h1", "unitree_h2", "unitree_a2"} <= ids


def test_unbuilt_robot_cannot_be_selected_active(tmp_path: Path):
    client = make_client(tmp_path)
    settings = client.get("/api/settings").json()
    settings["active_robot"] = "unitree_g1"
    response = client.put("/api/settings", json=settings)
    assert response.status_code == 400
