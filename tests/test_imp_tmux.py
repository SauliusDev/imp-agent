import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_tmux import (  # noqa: E402
    TmuxPaths,
    build_session_name,
    capture_output,
    command_exists,
    kill_session,
    load_state,
    session_paths,
    session_status,
    spawn_session,
)


def test_build_session_name_sanitizes_story_and_step():
    name = build_session_name("run-1", "1-1/my story", "dev")

    assert name == "imp-run-1-1-1-my-story-dev"
    assert "/" not in name
    assert " " not in name


def test_session_paths_rejects_escape_names(tmp_path):
    with pytest.raises(ValueError):
        session_paths("../bad", tmp_path)


def test_session_paths_stay_under_project_tmux_dir(tmp_path):
    paths = session_paths("imp-test", tmp_path)

    assert isinstance(paths, TmuxPaths)
    assert paths.state == tmp_path / "_imp" / "tmux" / "imp-test.state.json"
    assert paths.command == tmp_path / "_imp" / "tmux" / "imp-test.command.sh"
    assert paths.output == tmp_path / "_imp" / "tmux" / "imp-test.output.log"
    assert paths.runner == tmp_path / "_imp" / "tmux" / "imp-test.runner.sh"


def test_spawn_session_writes_state_command_output_and_runner(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("imp_tmux.command_exists", lambda name: True)
    monkeypatch.setattr("imp_tmux.subprocess.run", fake_run)

    result = spawn_session(
        session="imp-test",
        command="printf hello",
        provider="codex",
        project_root=tmp_path,
    )

    assert result == "imp-test"
    paths = session_paths("imp-test", tmp_path)
    assert paths.command.read_text(encoding="utf-8") == "printf hello\n"
    assert paths.output.read_text(encoding="utf-8") == ""
    assert load_state(paths.state)["lifecycle"] == "running"
    assert stat.S_IMODE(paths.command.stat().st_mode) == 0o700
    assert stat.S_IMODE(paths.runner.stat().st_mode) == 0o700
    assert stat.S_IMODE(paths.state.stat().st_mode) == 0o600
    assert calls[0][0][:3] == ["tmux", "new-session", "-d"]
    assert calls[0][0][-1] == str(paths.runner)


@pytest.mark.skipif(not command_exists("tmux"), reason="tmux not installed")
def test_spawn_session_completes_successfully_with_real_tmux(tmp_path):
    session = build_session_name("test", "story", f"ok-{int(time.time() * 1000)}")
    try:
        spawn_session(session, "printf hello", "codex", tmp_path)
        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = session_status(session, tmp_path)
            if status["session_state"] in {"completed", "crashed"}:
                break
            time.sleep(0.1)

        assert status["session_state"] == "completed"
        assert capture_output(session, tmp_path) == "hello"
        state = load_state(session_paths(session, tmp_path).state)
        assert state["lifecycle"] == "finished"
        assert state["result"] == "success"
        assert state["exitCode"] == 0
    finally:
        kill_session(session, tmp_path)
