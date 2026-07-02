import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_server import build_state_snapshot, create_app
from imp_runner import _is_loopback_web_host, _make_start_run_once, _validate_web_host
from imp_state import CurrentStep, create_initial_state


def test_build_state_snapshot_includes_current_tmux_session():
    state = create_initial_state({"agent_provider": "codex"}, "all")
    state.set_current(CurrentStep(
        story_id="1-1-example",
        step="dev",
        attempt=1,
        max_attempts=0,
        step_chain="spec.dev.---",
        start_time=123.0,
        log_path="_imp/logs/1-1-example/dev-attempt-1.log",
        tmux_session="imp-run-1-1-example-dev",
    ))

    snapshot = build_state_snapshot(state)

    assert snapshot["epic_id"] == "all"
    assert snapshot["provider"] == "codex"
    assert snapshot["current"]["tmux_session"] == "imp-run-1-1-example-dev"


def test_build_state_snapshot_includes_required_fields_and_last_200_output_lines():
    state = create_initial_state({"agent_provider": "claude"}, "epic-1")
    state.app_phase = "running"
    state.set_pending_stories(["1-1-example"], {"1-1-example": "dev"})
    state.set_roadmap([("epic", "epic-1", "pending", "Example", None)])
    state.update_full_usage(
        usage_5h=11,
        usage_7d=22,
        usage_sonnet=33,
        usage_extra_pct=44,
        usage_extra_spent="1.25",
        usage_extra_account_cap="10.00",
        usage_decision="PROCEED",
        five_h_resets_at="2026-07-02T10:00:00Z",
        seven_d_resets_at="2026-07-03T10:00:00Z",
        updated_at=123456.0,
    )
    for index in range(205):
        state.append_output(f"line-{index}")

    snapshot = build_state_snapshot(state)

    assert snapshot["app_phase"] == "running"
    assert snapshot["halted"] is False
    assert snapshot["halt_reason"] is None
    assert snapshot["should_exit"] is False
    assert snapshot["exit_code"] == 0
    assert snapshot["usage"]["five_hour_pct"] == 11
    assert snapshot["usage"]["seven_day_pct"] == 22
    assert snapshot["usage"]["sonnet_pct"] == 33
    assert snapshot["usage"]["extra_pct"] == 44
    assert snapshot["usage"]["extra_spent_eur"] == "1.25"
    assert snapshot["usage"]["extra_account_cap_eur"] == "10.00"
    assert snapshot["usage"]["decision"] == "PROCEED"
    assert snapshot["pending_stories"] == ["1-1-example"]
    assert snapshot["roadmap_rows"] == [("epic", "epic-1", "pending", "Example", None)]
    assert snapshot["output_lines"][0] == "line-5"
    assert snapshot["output_lines"][-1] == "line-204"
    assert len(snapshot["output_lines"]) == 200


def test_create_app_routes_call_callbacks_when_fastapi_is_installed():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI is not installed")

    state = create_initial_state({"agent_provider": "codex"}, "all")
    calls = []
    app = create_app(
        state,
        start_run=lambda: calls.append("run"),
        pause=lambda: calls.append("pause"),
        resume=lambda: calls.append("resume"),
        quit_now=lambda: calls.append("quit"),
        reload_config=lambda: calls.append("reload"),
    )
    client = TestClient(app)

    assert client.get("/api/state").json()["provider"] == "codex"
    for route, name in [
        ("/api/run", "run"),
        ("/api/pause", "pause"),
        ("/api/resume", "resume"),
        ("/api/quit", "quit"),
        ("/api/reload-config", "reload"),
    ]:
        response = client.post(route)
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert calls[-1] == name


def test_api_quit_calls_quit_and_shutdown_when_fastapi_is_installed():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI is not installed")

    state = create_initial_state({"agent_provider": "codex"}, "all")
    calls = []
    app = create_app(
        state,
        start_run=lambda: calls.append("run"),
        pause=lambda: calls.append("pause"),
        resume=lambda: calls.append("resume"),
        quit_now=lambda: calls.append("quit"),
        reload_config=lambda: calls.append("reload"),
        shutdown_server=lambda: calls.append("shutdown"),
    )

    response = TestClient(app).post("/api/quit")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == ["quit", "shutdown"]


def test_make_start_run_once_ignores_repeated_requests():
    state = create_initial_state({"agent_provider": "codex"}, "all")
    calls = []

    class Session:
        def log(self, message):
            calls.append(("log", message))

    start_run = _make_start_run_once(
        state,
        Session(),
        lambda: calls.append(("start", "pipeline")),
    )

    start_run()
    start_run()

    assert state.app_phase == "running"
    assert calls.count(("start", "pipeline")) == 1
    assert ("log", "Web run requested while pipeline already started") in calls


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_loopback_web_host_allows_safe_defaults(host):
    assert _is_loopback_web_host(host) is True
    assert _validate_web_host(host, allow_remote_web=False) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "example.com"])
def test_web_host_guard_requires_explicit_remote_opt_in(host):
    assert _is_loopback_web_host(host) is False
    message = _validate_web_host(host, allow_remote_web=False)
    assert message is not None
    assert "--allow-remote-web" in message
    assert _validate_web_host(host, allow_remote_web=True) is None
