from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class TmuxPaths:
    state: Path
    command: Path
    output: Path
    runner: Path


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def command_exists(name: str) -> bool:
    return subprocess.run(
        ["sh", "-lc", f"command -v {shlex.quote(name)} >/dev/null 2>&1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def build_session_name(run_id: str, story_id: str, step_id: str) -> str:
    raw = f"imp-{_safe_part(run_id)}-{_safe_part(story_id)}-{_safe_part(step_id)}"
    return raw[:80]


def session_paths(session: str, project_root: str | Path) -> TmuxPaths:
    if "/" in session or "\\" in session or ".." in session:
        raise ValueError(f"unsafe tmux session name: {session}")

    base = Path(project_root) / "_imp" / "tmux"
    return TmuxPaths(
        state=base / f"{session}.state.json",
        command=base / f"{session}.command.sh",
        output=base / f"{session}.output.log",
        runner=base / f"{session}.runner.sh",
    )


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def spawn_session(session: str, command: str, provider: str, project_root: str | Path) -> str:
    if not command_exists("tmux"):
        raise RuntimeError("tmux is required for IMP tmux runner")

    root = Path(project_root)
    paths = session_paths(session, root)
    paths.command.parent.mkdir(parents=True, exist_ok=True)

    paths.command.write_text(command.rstrip() + "\n", encoding="utf-8")
    os.chmod(paths.command, 0o700)
    paths.output.write_text("", encoding="utf-8")

    now = iso_now()
    _write_state(
        paths.state,
        {
            "schemaVersion": 1,
            "session": session,
            "provider": provider,
            "projectRoot": str(root),
            "commandFile": str(paths.command),
            "runnerFile": str(paths.runner),
            "outputPath": str(paths.output),
            "createdAt": now,
            "updatedAt": now,
            "lifecycle": "running",
            "result": "",
            "exitCode": "",
            "failureReason": "",
        },
    )
    _write_runner(paths, root)

    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, str(paths.runner)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return session


def session_status(session: str, project_root: str | Path) -> dict:
    paths = session_paths(session, project_root)
    state = load_state(paths.state)
    exists = command_exists("tmux") and _tmux_has_session(session)
    lifecycle = state.get("lifecycle", "")
    result = state.get("result", "")
    exit_code = state.get("exitCode", "")

    if lifecycle == "finished" and result == "killed":
        session_state = "killed"
    elif lifecycle == "finished":
        session_state = "completed" if exit_code == 0 else "crashed"
    elif exists:
        session_state = "running"
    elif state:
        session_state = "unknown"
    else:
        session_state = "not_found"

    return {
        "session": session,
        "session_state": session_state,
        "tmux_exists": exists,
        "exit_code": exit_code,
        "output_path": str(paths.output),
        "state_path": str(paths.state),
    }


def capture_output(session: str, project_root: str | Path) -> str:
    output = session_paths(session, project_root).output
    if not output.exists():
        return ""
    return output.read_text(encoding="utf-8", errors="replace")


def kill_session(session: str, project_root: str | Path) -> None:
    if command_exists("tmux"):
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    paths = session_paths(session, project_root)
    if paths.state.exists():
        state = load_state(paths.state)
        state["lifecycle"] = "finished"
        state["result"] = "killed"
        state["exitCode"] = 143
        state["failureReason"] = "killed by operator"
        state["updatedAt"] = iso_now()
        _write_state(paths.state, state)


def _safe_part(value: str) -> str:
    part = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    part = re.sub(r"-+", "-", part).strip("-")
    return part or "unknown"


def _write_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)


def _write_runner(paths: TmuxPaths, root: Path) -> None:
    paths.runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -o pipefail\n"
        f"cd {shlex.quote(str(root))}\n"
        f"bash {shlex.quote(str(paths.command))} > {shlex.quote(str(paths.output))} 2>&1\n"
        "code=$?\n"
        "python3 - \"$code\" <<'PY'\n"
        "from datetime import datetime, timezone\n"
        "import json\n"
        "import sys\n"
        f"path = {str(paths.state)!r}\n"
        "code = int(sys.argv[1])\n"
        "with open(path, 'r', encoding='utf-8') as f:\n"
        "    data = json.load(f)\n"
        "data['lifecycle'] = 'finished'\n"
        "data['exitCode'] = code\n"
        "data['result'] = 'success' if code == 0 else 'failure'\n"
        "data['updatedAt'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')\n"
        "with open(path, 'w', encoding='utf-8') as f:\n"
        "    json.dump(data, f, indent=2)\n"
        "PY\n"
        "chmod 600 "
        f"{shlex.quote(str(paths.state))}\n"
        "exit $code\n",
        encoding="utf-8",
    )
    os.chmod(paths.runner, 0o700)


def _tmux_has_session(session: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
