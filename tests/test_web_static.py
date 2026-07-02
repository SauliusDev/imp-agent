import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

import imp_server
from imp_server import create_app, web_dist_path
from imp_state import create_initial_state


def test_web_dist_path_points_to_repo_web_dist():
    path = web_dist_path()

    assert path.name == "dist"
    assert path.parent.name == "web"
    assert path == Path(__file__).resolve().parent.parent / "web" / "dist"


def test_static_mount_serves_web_and_preserves_api_state_when_fastapi_is_installed(
    monkeypatch,
    tmp_path,
):
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI is not installed")

    (tmp_path / "index.html").write_text("<main>IMP Web</main>")
    monkeypatch.setattr(imp_server, "web_dist_path", lambda: tmp_path)

    state = create_initial_state({"agent_provider": "codex"}, "all")
    app = create_app(
        state,
        start_run=lambda: None,
        pause=lambda: None,
        resume=lambda: None,
        quit_now=lambda: None,
        reload_config=lambda: None,
    )

    client = TestClient(app)
    web_response = client.get("/")
    api_response = client.get("/api/state")

    assert web_response.status_code == 200
    assert "IMP Web" in web_response.text
    assert api_response.status_code == 200
    assert api_response.json()["provider"] == "codex"
