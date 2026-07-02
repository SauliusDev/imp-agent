import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_runner import _make_quit_now, run_agent_tmux
from imp_state import CurrentStep, create_initial_state


def test_current_step_can_store_tmux_session():
    current = CurrentStep(
        story_id="1-1-example",
        step="dev",
        attempt=1,
        max_attempts=0,
        step_chain="spec.dev.review",
        start_time=1.0,
        log_path="_imp/logs/1-1-example/dev-attempt-1.log",
        tmux_session="imp-run-1-1-example-dev",
    )

    assert current.tmux_session == "imp-run-1-1-example-dev"


def test_run_agent_tmux_spawns_quoted_command_and_mirrors_output(tmp_path, monkeypatch):
    calls = []
    statuses = [
        {"session_state": "running", "exit_code": ""},
        {"session_state": "completed", "exit_code": 0},
    ]
    outputs = ["hello\n", "hello\nworld with spaces\n"]

    def fake_spawn(session, command, provider, project_root):
        calls.append((session, command, provider, project_root))
        return session

    def fake_status(session, project_root):
        return statuses.pop(0)

    def fake_capture(session, project_root):
        return outputs.pop(0)

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("imp_runner.spawn_session", fake_spawn)
    monkeypatch.setattr("imp_runner.session_status", fake_status)
    monkeypatch.setattr("imp_runner.capture_output", fake_capture)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    state = create_initial_state(config={"agent_provider": "codex"}, epic_id="all")
    raw_log = tmp_path / "raw.log"
    readable_log = tmp_path / "readable.log"

    exit_code = asyncio.run(run_agent_tmux(
        ["codex", "exec", "--model", "gpt test", "prompt with 'quote'"],
        str(raw_log),
        str(readable_log),
        state,
        provider="codex",
        tmux_session="imp-test-session",
    ))

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0][0] == "imp-test-session"
    assert calls[0][2] == "codex"
    assert calls[0][1] == "codex exec --model 'gpt test' 'prompt with '\"'\"'quote'\"'\"''"
    assert readable_log.read_text(encoding="utf-8") == "hello\nworld with spaces\n"
    assert raw_log.read_text(encoding="utf-8") == "hello\nworld with spaces\n"
    assert [line for _, line in state.output_lines] == ["hello", "world with spaces"]


def test_run_agent_tmux_returns_crashed_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr("imp_runner.spawn_session", lambda *args: args[0])
    monkeypatch.setattr("imp_runner.session_status", lambda *_args: {
        "session_state": "crashed",
        "exit_code": 42,
    })
    monkeypatch.setattr("imp_runner.capture_output", lambda *_args: "boom\n")

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    state = create_initial_state(config={}, epic_id="all")

    exit_code = asyncio.run(run_agent_tmux(
        ["false"],
        str(tmp_path / "raw.log"),
        str(tmp_path / "readable.log"),
        state,
        provider="claude",
        tmux_session="imp-crash",
    ))

    assert exit_code == 42


def test_run_agent_tmux_returns_deterministic_code_for_killed(tmp_path, monkeypatch):
    monkeypatch.setattr("imp_runner.spawn_session", lambda *args: args[0])
    monkeypatch.setattr("imp_runner.session_status", lambda *_args: {
        "session_state": "killed",
        "exit_code": "",
    })
    monkeypatch.setattr("imp_runner.capture_output", lambda *_args: "stopped\n")

    state = create_initial_state(config={}, epic_id="all")

    exit_code = asyncio.run(run_agent_tmux(
        ["sleep", "100"],
        str(tmp_path / "raw.log"),
        str(tmp_path / "readable.log"),
        state,
        provider="claude",
        tmux_session="imp-killed",
    ))

    assert exit_code == 143


def test_quit_now_kills_current_tmux_session_before_subprocess_fallback(monkeypatch):
    killed = []
    interrupted = []

    class Session:
        def log(self, _msg):
            pass

    monkeypatch.setattr("imp_runner.kill_session", lambda session, project_root: killed.append(session))
    monkeypatch.setattr(
        "imp_runner.imp_ledger.cmd_step_interrupted",
        lambda story_id, step: interrupted.append((story_id, step)),
    )

    state = create_initial_state(config={}, epic_id="all")
    state.subprocess_pid = 123456
    state.set_current(CurrentStep(
        story_id="1-1-example",
        step="dev",
        attempt=1,
        max_attempts=0,
        step_chain="spec.dev.review",
        start_time=1.0,
        log_path="_imp/logs/1-1-example/dev-attempt-1.log",
        tmux_session="imp-active-dev",
    ))

    _make_quit_now(state, Session())()

    assert killed == ["imp-active-dev"]
    assert interrupted == [("1-1-example", "dev")]
    assert state.should_exit is True
    assert state.display_exit is True
