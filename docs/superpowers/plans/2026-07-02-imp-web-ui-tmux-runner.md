# IMP Web UI And Tmux Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web dashboard for IMP while moving child Claude/Codex execution into one sequential tmux session per active step.

**Architecture:** Keep the deterministic Python runner as the control plane and keep `_imp/ledger.json` as the source of workflow state. Add step definitions, a tmux runtime, and a local server/UI around the existing loop without introducing the future Mermaid workflow compiler yet.

**Tech Stack:** Python 3.10+, pytest, tmux, FastAPI or Starlette, React, Vite, Tailwind, shadcn/Origin-style components, xterm.js.

---

## File Structure

- Create `engine/imp_steps.py`: maps step ids to provider command prompts, model/effort config keys, and verifier policy.
- Create `engine/imp_tmux.py`: owns tmux session names, command scripts, status files, spawn, monitor, capture, and kill.
- Modify `engine/imp_state.py`: add tmux session metadata to `CurrentStep`.
- Modify `engine/imp_runner.py`: route `_run_spec`, `_run_dev`, and `_run_review` through step definitions and tmux runtime.
- Create `engine/imp_server.py`: local API and event stream around `RunnerState`.
- Create `web/`: React UI for dashboard, roadmap, current step, logs, controls, and terminal tab.
- Modify `install.py`: install new engine files and optionally web assets.
- Add tests under `tests/`: step definitions, tmux runtime, runner integration seams, and server state endpoints.

The first working milestone is "tmux runner still works from CLI." The second is "local API exposes state." The third is "web UI controls the same loop."

---

### Task 1: Step Definitions

**Files:**
- Create: `engine/imp_steps.py`
- Test: `tests/test_imp_steps.py`
- Modify: `engine/imp_runner.py`

- [ ] **Step 1: Write failing tests for current BMAD step definitions**

Create `tests/test_imp_steps.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_steps import (
    PIPELINE_STEP_IDS,
    StepDefinition,
    build_step_prompt,
    get_step_definition,
    resolve_step_runtime,
)


def test_pipeline_steps_match_current_bmad_flow():
    assert PIPELINE_STEP_IDS == ["spec", "dev", "review"]


def test_get_step_definition_returns_bmad_skill_mapping():
    spec = get_step_definition("spec")

    assert isinstance(spec, StepDefinition)
    assert spec.step_id == "spec"
    assert spec.skill == "bmad-create-story"
    assert spec.model_key == "model_spec"
    assert spec.effort_key == "effort_spec"
    assert spec.verifier == "story_file_exists"


def test_build_step_prompt_keeps_current_spec_contract():
    prompt = build_step_prompt(
        "spec",
        story_id="1-1-example",
        story_file="_bmad-output/implementation-artifacts/1-1-example.md",
    )

    assert "/bmad-create-story 1-1-example" in prompt
    assert "MUST be written to exactly this path" in prompt
    assert "_bmad-output/implementation-artifacts/1-1-example.md" in prompt


def test_build_step_prompt_keeps_current_dev_and_review_contracts():
    story_file = "_bmad-output/implementation-artifacts/1-1-example.md"

    assert build_step_prompt("dev", story_id="1-1-example", story_file=story_file).startswith(
        f"/bmad-dev-story {story_file}"
    )
    assert build_step_prompt("review", story_id="1-1-example", story_file=story_file).startswith(
        f"/bmad-code-review {story_file}"
    )


def test_resolve_step_runtime_uses_configured_model_and_effort():
    runtime = resolve_step_runtime(
        "dev",
        {
            "agent_provider": "codex",
            "model_dev": "gpt-5.5",
            "effort_dev": "high",
        },
    )

    assert runtime.provider == "codex"
    assert runtime.model == "gpt-5.5"
    assert runtime.effort == "high"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_imp_steps.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'imp_steps'`.

- [ ] **Step 3: Implement step definitions**

Create `engine/imp_steps.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


PIPELINE_STEP_IDS = ["spec", "dev", "review"]


@dataclass(frozen=True)
class StepDefinition:
    step_id: str
    skill: str
    model_key: str
    effort_key: str
    verifier: str
    max_attempts_key: str | None = None


@dataclass(frozen=True)
class StepRuntime:
    provider: str
    model: str
    effort: str


STEP_DEFINITIONS = {
    "spec": StepDefinition(
        step_id="spec",
        skill="bmad-create-story",
        model_key="model_spec",
        effort_key="effort_spec",
        verifier="story_file_exists",
    ),
    "dev": StepDefinition(
        step_id="dev",
        skill="bmad-dev-story",
        model_key="model_dev",
        effort_key="effort_dev",
        verifier="exit_code_zero",
    ),
    "review": StepDefinition(
        step_id="review",
        skill="bmad-code-review",
        model_key="model_review",
        effort_key="effort_review",
        verifier="sprint_status_done",
        max_attempts_key="max_review_attempts",
    ),
}


PREAMBLE_SPEC = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the story spec without halting for user input:\n"
    "- Do NOT use HALT or ask for clarification - make reasonable assumptions\n"
    "- Do NOT present menus or wait for responses\n"
    "- Complete the full spec and write the story file as per your normal workflow\n"
    "\n## Halt signal\n"
    "If you discover a structural flaw that makes the story impossible to implement,\n"
    "write a short explanation to the file _imp/HALT and then exit."
)


PREAMBLE_DEV = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the full implementation without halting for user input:\n"
    "- Do NOT use HALT, do NOT ask for manual verification, do NOT wait for responses\n"
    "- Make all decisions autonomously - prefer the safest reasonable choice\n"
    "- Complete all tasks and update the story file status as per your normal workflow\n"
    "\n## Halt signal\n"
    "If you discover a structural flaw that makes the story impossible to implement,\n"
    "write a short explanation to the file _imp/HALT and then exit."
)


PREAMBLE_REVIEW = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the full code review without halting for user input:\n"
    "- Run all adversarial review layers\n"
    "- Auto-apply all patch fixes directly to source files\n"
    "- Defer all decision-needed findings in the story file with [Review][Defer]\n"
    "- Do NOT present menus, ask for choices, or wait for responses\n"
    "- Update the story file status and sprint-status.yaml as per your normal workflow\n"
    "\n## Halt signal\n"
    "If you discover a structural flaw that makes the story impossible to implement,\n"
    "write a short explanation to the file _imp/HALT and then exit."
)


DEFAULT_MODELS = {
    "model_spec": "claude-sonnet-4-6",
    "model_dev": "claude-sonnet-4-6",
    "model_review": "claude-opus-4-6",
    "effort_spec": "medium",
    "effort_dev": "high",
    "effort_review": "high",
}


def get_step_definition(step_id: str) -> StepDefinition:
    try:
        return STEP_DEFINITIONS[step_id]
    except KeyError as exc:
        raise ValueError(f"unknown step: {step_id}") from exc


def build_step_prompt(step_id: str, *, story_id: str, story_file: str) -> str:
    definition = get_step_definition(step_id)
    if definition.step_id == "spec":
        return (
            f"/{definition.skill} {story_id}\n\n"
            f"IMPORTANT: The story file MUST be written to exactly this path: `{story_file}`\n"
            f"{PREAMBLE_SPEC}"
        )
    if definition.step_id == "dev":
        return f"/{definition.skill} {story_file}\n{PREAMBLE_DEV}"
    if definition.step_id == "review":
        return f"/{definition.skill} {story_file}\n{PREAMBLE_REVIEW}"
    raise ValueError(f"unknown step: {step_id}")


def resolve_step_runtime(step_id: str, config: dict) -> StepRuntime:
    definition = get_step_definition(step_id)
    return StepRuntime(
        provider=str(config.get("agent_provider", "claude")).strip().lower(),
        model=str(config.get(definition.model_key, DEFAULT_MODELS[definition.model_key])),
        effort=str(config.get(definition.effort_key, DEFAULT_MODELS[definition.effort_key])),
    )
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python3 -m pytest tests/test_imp_steps.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add engine/imp_steps.py tests/test_imp_steps.py
git commit -m "feat: add imp step definitions"
```

---

### Task 2: Tmux Runtime

**Files:**
- Create: `engine/imp_tmux.py`
- Test: `tests/test_imp_tmux.py`

- [ ] **Step 1: Write unit tests for tmux session naming and state files**

Create `tests/test_imp_tmux.py`:

```python
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_tmux import (
    TmuxPaths,
    build_session_name,
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


def test_spawn_session_writes_state_and_command_without_tmux(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
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
    assert load_state(paths.state)["lifecycle"] == "running"
    assert stat.S_IMODE(paths.command.stat().st_mode) == 0o700
    assert calls[0][:3] == ["tmux", "new-session", "-d"]


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
        assert "hello" in Path(status["output_path"]).read_text(encoding="utf-8")
    finally:
        kill_session(session, tmp_path)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_imp_tmux.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'imp_tmux'`.

- [ ] **Step 3: Implement tmux runtime**

Create `engine/imp_tmux.py`:

```python
from __future__ import annotations

import json
import os
import re
import shlex
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class TmuxPaths:
    state: Path
    command: Path
    output: Path


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def command_exists(name: str) -> bool:
    return subprocess.run(
        ["sh", "-lc", f"command -v {shlex.quote(name)} >/dev/null 2>&1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _safe_part(value: str) -> str:
    part = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    part = re.sub(r"-+", "-", part).strip("-")
    return part or "unknown"


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
    )


def _write_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)


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

    _write_state(paths.state, {
        "schemaVersion": 1,
        "session": session,
        "provider": provider,
        "projectRoot": str(root),
        "commandFile": str(paths.command),
        "outputPath": str(paths.output),
        "createdAt": iso_now(),
        "updatedAt": iso_now(),
        "lifecycle": "running",
        "result": "",
        "exitCode": "",
        "failureReason": "",
    })

    runner = (
        "set -o pipefail\n"
        f"cd {shlex.quote(str(root))}\n"
        f"bash {shlex.quote(str(paths.command))} > {shlex.quote(str(paths.output))} 2>&1\n"
        "code=$?\n"
        "python3 - <<'PY'\n"
        "import json, os\n"
        f"path = {str(paths.state)!r}\n"
        "with open(path, 'r', encoding='utf-8') as f:\n"
        "    data = json.load(f)\n"
        "data['lifecycle'] = 'finished'\n"
        "data['exitCode'] = code = int(os.environ['IMP_EXIT_CODE'])\n"
        "data['result'] = 'success' if code == 0 else 'failure'\n"
        "data['updatedAt'] = data.get('updatedAt')\n"
        "with open(path, 'w', encoding='utf-8') as f:\n"
        "    json.dump(data, f, indent=2)\n"
        "PY\n"
        "exit $code\n"
    )
    wrapper = f"IMP_EXIT_CODE=0 bash -lc {shlex.quote(runner)}"
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, wrapper],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return session


def _tmux_has_session(session: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def session_status(session: str, project_root: str | Path) -> dict:
    paths = session_paths(session, project_root)
    state = load_state(paths.state)
    exists = command_exists("tmux") and _tmux_has_session(session)
    lifecycle = state.get("lifecycle", "")
    exit_code = state.get("exitCode", "")

    if lifecycle == "finished":
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
    paths = session_paths(session, project_root)
    if paths.output.exists():
        return paths.output.read_text(encoding="utf-8", errors="replace")
    return ""


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
        state["failureReason"] = "killed by operator"
        state["updatedAt"] = iso_now()
        _write_state(paths.state, state)
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m pytest tests/test_imp_tmux.py -v
```

Expected: unit tests pass; real tmux test passes when tmux is installed and skips otherwise.

- [ ] **Step 5: Fix the runner wrapper exit-code bug if test catches it**

If the real tmux test fails because exit codes are not written correctly, replace the runner script generation in `spawn_session` with a temp runner file that writes `$code` directly:

```python
runner_path = paths.command.with_suffix(".runner.sh")
runner_path.write_text(
    "#!/usr/bin/env bash\n"
    "set -o pipefail\n"
    f"cd {shlex.quote(str(root))}\n"
    f"bash {shlex.quote(str(paths.command))} > {shlex.quote(str(paths.output))} 2>&1\n"
    "code=$?\n"
    "python3 - \"$code\" <<'PY'\n"
    "import json, sys\n"
    f"path = {str(paths.state)!r}\n"
    "code = int(sys.argv[1])\n"
    "with open(path, 'r', encoding='utf-8') as f:\n"
    "    data = json.load(f)\n"
    "data['lifecycle'] = 'finished'\n"
    "data['exitCode'] = code\n"
    "data['result'] = 'success' if code == 0 else 'failure'\n"
    "with open(path, 'w', encoding='utf-8') as f:\n"
    "    json.dump(data, f, indent=2)\n"
    "PY\n"
    "exit $code\n",
    encoding="utf-8",
)
os.chmod(runner_path, 0o700)
subprocess.run(["tmux", "new-session", "-d", "-s", session, str(runner_path)], ...)
```

- [ ] **Step 6: Commit**

```bash
git add engine/imp_tmux.py tests/test_imp_tmux.py
git commit -m "feat: add tmux runtime"
```

---

### Task 3: Run Agent Steps Through Tmux

**Files:**
- Modify: `engine/imp_state.py`
- Modify: `engine/imp_runner.py`
- Test: `tests/test_install.py`
- Test: `tests/test_imp_runner_tmux.py`

- [ ] **Step 1: Add tmux metadata tests for current state**

Create `tests/test_imp_runner_tmux.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_state import CurrentStep


def test_current_step_can_store_tmux_session_id():
    current = CurrentStep(
        story_id="1-1-example",
        step="dev",
        attempt=1,
        max_attempts=0,
        step_chain="spec.dev.---",
        start_time=123.0,
        log_path="_imp/logs/1-1-example/dev-attempt-1.log",
        tmux_session="imp-run-1-1-example-dev",
    )

    assert current.tmux_session == "imp-run-1-1-example-dev"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
python3 -m pytest tests/test_imp_runner_tmux.py -v
```

Expected: fail because `CurrentStep` has no `tmux_session` argument.

- [ ] **Step 3: Add optional tmux session metadata**

Modify `engine/imp_state.py`:

```python
@dataclass
class CurrentStep:
    """Currently running step, live-updating."""

    story_id: str
    step: str
    attempt: int
    max_attempts: int
    step_chain: str
    start_time: float
    log_path: str
    tmux_session: Optional[str] = None
```

- [ ] **Step 4: Run state test**

Run:

```bash
python3 -m pytest tests/test_imp_runner_tmux.py -v
```

Expected: pass.

- [ ] **Step 5: Add a tmux-backed agent runner seam**

Modify `engine/imp_runner.py` to import:

```python
from imp_steps import build_step_prompt, resolve_step_runtime
from imp_tmux import build_session_name, capture_output, session_status, spawn_session
```

Add a new async function near `run_agent_subprocess`:

```python
async def run_agent_tmux(
    *,
    provider: str,
    args: list[str],
    story_id: str,
    step: str,
    attempt: int,
    readable_log_path: str,
    state: RunnerState,
) -> int:
    """Run one agent step in tmux and mirror captured output into RunnerState."""
    session_name = build_session_name(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        story_id,
        f"{step}-{attempt}",
    )
    command = " ".join(shlex.quote(part) for part in args)
    spawn_session(session_name, command, provider, PROJECT_ROOT)

    if state.current is not None:
        state.set_current(CurrentStep(
            story_id=state.current.story_id,
            step=state.current.step,
            attempt=state.current.attempt,
            max_attempts=state.current.max_attempts,
            step_chain=state.current.step_chain,
            start_time=state.current.start_time,
            log_path=state.current.log_path,
            tmux_session=session_name,
        ))

    last_text = ""
    while not state.should_exit:
        status = session_status(session_name, PROJECT_ROOT)
        text = capture_output(session_name, PROJECT_ROOT)
        if text != last_text:
            new_text = text[len(last_text):]
            with open(readable_log_path, "a", encoding="utf-8") as readable:
                readable.write(new_text)
            for line in new_text.splitlines():
                if line.strip():
                    state.append_output(line)
            last_text = text

        if status["session_state"] == "completed":
            return 0
        if status["session_state"] == "crashed":
            return int(status.get("exit_code") or 1)
        await asyncio.sleep(0.5)

    return 130
```

Also import `shlex`.

- [ ] **Step 6: Route `_run_spec`, `_run_dev`, `_run_review` through `run_agent_tmux`**

In each step runner, replace:

```python
await run_agent_subprocess(...)
```

or:

```python
exit_code = await run_agent_subprocess(...)
```

with:

```python
exit_code = await run_agent_tmux(
    provider=provider,
    args=_build_agent_args(provider, prompt, model, effort),
    story_id=story_id,
    step="dev",
    attempt=attempt_num,
    readable_log_path=readable_path,
    state=state,
)
```

Use the actual step id for each runner. For spec, assign the return value even if the current verifier remains story-file based:

```python
exit_code = await run_agent_tmux(...)
```

- [ ] **Step 7: Keep subprocess helper tests passing**

Do not delete `run_agent_subprocess`, `run_claude_subprocess`, `ClaudeStreamParser`, or `CodexStreamParser`. Existing parser and subprocess tests in `tests/test_install.py` must still pass.

- [ ] **Step 8: Run focused tests**

Run:

```bash
python3 -m pytest tests/test_imp_steps.py tests/test_imp_tmux.py tests/test_imp_runner_tmux.py tests/test_install.py -v
```

Expected: pass, except real tmux test skips if tmux is unavailable.

- [ ] **Step 9: Commit**

```bash
git add engine/imp_state.py engine/imp_runner.py tests/test_imp_runner_tmux.py tests/test_install.py
git commit -m "feat: run imp steps through tmux"
```

---

### Task 4: Local API Server

**Files:**
- Create: `engine/imp_server.py`
- Modify: `engine/imp_runner.py`
- Test: `tests/test_imp_server.py`

- [ ] **Step 1: Write server snapshot tests**

Create `tests/test_imp_server.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_server import build_state_snapshot
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_imp_server.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'imp_server'`.

- [ ] **Step 3: Implement state snapshot builder and API factory**

Create `engine/imp_server.py`:

```python
from __future__ import annotations

import asyncio
import json
import time
from typing import Callable

try:
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
except ImportError:  # tests can still import pure helpers
    FastAPI = None
    StreamingResponse = None

from imp_state import RunnerState


def build_state_snapshot(state: RunnerState) -> dict:
    current = state.current
    return {
        "epic_id": state.epic_id,
        "provider": str(state.config.get("agent_provider", "claude")),
        "app_phase": state.app_phase,
        "halted": state.halted,
        "halt_reason": state.halt_reason,
        "should_exit": state.should_exit,
        "exit_code": state.exit_code,
        "usage": {
            "five_hour_pct": state.usage_5h,
            "seven_day_pct": state.usage_7d,
            "sonnet_pct": state.usage_sonnet,
            "updated_at": state.usage_updated_at,
        },
        "current": None if current is None else {
            "story_id": current.story_id,
            "step": current.step,
            "attempt": current.attempt,
            "max_attempts": current.max_attempts,
            "step_chain": current.step_chain,
            "start_time": current.start_time,
            "elapsed_s": max(0, time.time() - current.start_time),
            "log_path": current.log_path,
            "tmux_session": current.tmux_session,
        },
        "pending_stories": list(state.pending_stories),
        "roadmap_rows": list(state.roadmap_rows),
        "output_lines": [line for _, line in list(state.output_lines)[-200:]],
    }


def create_app(
    state: RunnerState,
    *,
    start_run: Callable[[], None],
    pause: Callable[[], None],
    resume: Callable[[], None],
    quit_now: Callable[[], None],
    reload_config: Callable[[], None],
):
    if FastAPI is None:
        raise RuntimeError("FastAPI is required for imp_server")

    app = FastAPI(title="IMP Agent")

    @app.get("/api/state")
    def api_state():
        return build_state_snapshot(state)

    @app.post("/api/run")
    def api_run():
        start_run()
        return {"ok": True}

    @app.post("/api/pause")
    def api_pause():
        pause()
        return {"ok": True}

    @app.post("/api/resume")
    def api_resume():
        resume()
        return {"ok": True}

    @app.post("/api/quit")
    def api_quit():
        quit_now()
        return {"ok": True}

    @app.post("/api/reload-config")
    def api_reload_config():
        reload_config()
        return {"ok": True}

    @app.get("/api/events")
    async def api_events():
        async def stream():
            while not state.display_exit:
                payload = json.dumps(build_state_snapshot(state))
                yield f"data: {payload}\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream")

    return app
```

- [ ] **Step 4: Run server tests**

Run:

```bash
python3 -m pytest tests/test_imp_server.py -v
```

Expected: pass without requiring FastAPI installed.

- [ ] **Step 5: Add CLI mode to start server**

Modify `engine/imp_runner.py` argument parser:

```python
parser.add_argument(
    "--web",
    action="store_true",
    help="Start local web API instead of Rich TUI",
)
parser.add_argument(
    "--host",
    default="127.0.0.1",
    help="Web API bind host",
)
parser.add_argument(
    "--port",
    type=int,
    default=8765,
    help="Web API bind port",
)
```

In `main()`, after state/session callbacks are created, if `args.web` is true:

```python
from imp_server import create_app
import uvicorn

def start_run_once() -> None:
    state.confirm_launch()
    threading.Thread(
        target=_pipeline_thread,
        args=(state, session),
        daemon=True,
        name="pipeline",
    ).start()

app = create_app(
    state,
    start_run=start_run_once,
    pause=state.set_paused,
    resume=state.clear_paused,
    quit_now=quit_now,
    reload_config=reload_config_now,
)
uvicorn.run(app, host=args.host, port=args.port)
return
```

- [ ] **Step 6: Add dependency note**

Update `README.md` prerequisites with:

```markdown
- Optional web UI/API: `fastapi` and `uvicorn`
```

- [ ] **Step 7: Run tests**

Run:

```bash
python3 -m pytest tests/test_imp_server.py tests/test_install.py -v
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add engine/imp_server.py engine/imp_runner.py tests/test_imp_server.py README.md
git commit -m "feat: add local imp api server"
```

---

### Task 5: Web UI Scaffold

**Files:**
- Create: `web/package.json`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/styles.css`
- Create: `web/src/api.ts`
- Create: `web/src/types.ts`
- Create: `web/src/components/Dashboard.tsx`
- Create: `web/src/components/Controls.tsx`
- Create: `web/src/components/OutputPanel.tsx`
- Create: `web/src/components/Roadmap.tsx`
- Create: `web/src/components/TerminalPanel.tsx`

- [ ] **Step 1: Create Vite React app files**

Create `web/package.json`:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port 5173",
    "build": "vite build",
    "preview": "vite preview --host 127.0.0.1 --port 5173"
  },
  "dependencies": {
    "@vitejs/plugin-react": "latest",
    "vite": "latest",
    "typescript": "latest",
    "react": "latest",
    "react-dom": "latest",
    "lucide-react": "latest",
    "@xterm/xterm": "latest"
  },
  "devDependencies": {}
}
```

Create `web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>IMP Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Add UI types and API client**

Create `web/src/types.ts`:

```ts
export type CurrentStep = {
  story_id: string;
  step: string;
  attempt: number;
  max_attempts: number;
  step_chain: string;
  elapsed_s: number;
  log_path: string;
  tmux_session: string | null;
};

export type ImpState = {
  epic_id: string;
  provider: string;
  app_phase: string;
  halted: boolean;
  halt_reason: string | null;
  should_exit: boolean;
  exit_code: number;
  usage: {
    five_hour_pct: number | null;
    seven_day_pct: number | null;
    sonnet_pct: number | null;
    updated_at: number | null;
  };
  current: CurrentStep | null;
  pending_stories: string[];
  roadmap_rows: Array<[string, string, string, string, string | null]>;
  output_lines: string[];
};
```

Create `web/src/api.ts`:

```ts
import type { ImpState } from "./types";

const API_BASE = import.meta.env.VITE_IMP_API_BASE ?? "http://127.0.0.1:8765";

export async function fetchState(): Promise<ImpState> {
  const response = await fetch(`${API_BASE}/api/state`);
  if (!response.ok) throw new Error(`state request failed: ${response.status}`);
  return response.json();
}

export async function sendControl(action: "run" | "pause" | "resume" | "quit" | "reload-config") {
  const response = await fetch(`${API_BASE}/api/${action}`, { method: "POST" });
  if (!response.ok) throw new Error(`${action} failed: ${response.status}`);
}

export function subscribeState(onState: (state: ImpState) => void): () => void {
  const source = new EventSource(`${API_BASE}/api/events`);
  source.onmessage = (event) => onState(JSON.parse(event.data));
  return () => source.close();
}
```

- [ ] **Step 3: Add main React entry**

Create `web/src/main.tsx`:

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import "@xterm/xterm/css/xterm.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Create `web/src/App.tsx`:

```tsx
import { useEffect, useState } from "react";
import { fetchState, subscribeState } from "./api";
import { Dashboard } from "./components/Dashboard";
import type { ImpState } from "./types";

export default function App() {
  const [state, setState] = useState<ImpState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchState().then(setState).catch((err) => setError(String(err)));
    return subscribeState(setState);
  }, []);

  if (error) return <main className="app-shell error">{error}</main>;
  if (!state) return <main className="app-shell">Loading IMP...</main>;
  return <Dashboard state={state} />;
}
```

- [ ] **Step 4: Add dashboard components**

Create `web/src/components/Dashboard.tsx`:

```tsx
import impIcon from "../../../_board/icon/imp-agent.png";
import { Controls } from "./Controls";
import { OutputPanel } from "./OutputPanel";
import { Roadmap } from "./Roadmap";
import { TerminalPanel } from "./TerminalPanel";
import type { ImpState } from "../types";

export function Dashboard({ state }: { state: ImpState }) {
  const current = state.current;
  return (
    <main className="app-shell">
      <header className="topbar">
        <img src={impIcon} alt="" className="brand-icon" />
        <div>
          <h1>IMP Agent</h1>
          <p>{state.provider} / {state.epic_id}</p>
        </div>
        <div className="usage">
          <span>5h {state.usage.five_hour_pct ?? "?"}%</span>
          <span>7d {state.usage.seven_day_pct ?? "?"}%</span>
        </div>
      </header>

      <Controls running={Boolean(current)} paused={state.app_phase === "paused"} />

      <section className="grid">
        <Roadmap rows={state.roadmap_rows} />
        <section className="panel current">
          <h2>Current Step</h2>
          {current ? (
            <dl>
              <dt>Story</dt><dd>{current.story_id}</dd>
              <dt>Step</dt><dd>{current.step}</dd>
              <dt>Attempt</dt><dd>{current.attempt}/{current.max_attempts || "∞"}</dd>
              <dt>Tmux</dt><dd>{current.tmux_session ?? "starting"}</dd>
              <dt>Log</dt><dd>{current.log_path}</dd>
            </dl>
          ) : (
            <p className="muted">Idle</p>
          )}
        </section>
      </section>

      <OutputPanel lines={state.output_lines} />
      <TerminalPanel session={current?.tmux_session ?? null} />
    </main>
  );
}
```

Create the other component files with these minimal implementations:

```tsx
// web/src/components/Controls.tsx
import { Pause, Play, RotateCw, Square, Upload } from "lucide-react";
import { sendControl } from "../api";

export function Controls({ running, paused }: { running: boolean; paused: boolean }) {
  return (
    <nav className="controls">
      <button onClick={() => sendControl("run")} disabled={running}><Play size={16} /> Run</button>
      <button onClick={() => sendControl(paused ? "resume" : "pause")}><Pause size={16} /> {paused ? "Resume" : "Pause"}</button>
      <button onClick={() => sendControl("quit")}><Square size={16} /> Quit</button>
      <button onClick={() => sendControl("reload-config")}><RotateCw size={16} /> Reload</button>
      <button disabled><Upload size={16} /> Terminal</button>
    </nav>
  );
}
```

```tsx
// web/src/components/Roadmap.tsx
export function Roadmap({ rows }: { rows: Array<[string, string, string, string, string | null]> }) {
  return (
    <section className="panel roadmap">
      <h2>Roadmap</h2>
      <ol>
        {rows.map(([type, id, status, detail, blocked]) => (
          <li key={`${type}-${id}`} className={`row ${type} ${status}`}>
            <span>{id}</span>
            <small>{detail}</small>
            {blocked ? <em>{blocked}</em> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
```

```tsx
// web/src/components/OutputPanel.tsx
export function OutputPanel({ lines }: { lines: string[] }) {
  return (
    <section className="panel output">
      <h2>Agent Output</h2>
      <pre>{lines.length ? lines.join("\n") : "Waiting for output..."}</pre>
    </section>
  );
}
```

```tsx
// web/src/components/TerminalPanel.tsx
export function TerminalPanel({ session }: { session: string | null }) {
  return (
    <section className="panel terminal">
      <h2>Terminal</h2>
      <p className="muted">{session ? `Tmux session: ${session}` : "No active tmux session"}</p>
    </section>
  );
}
```

- [ ] **Step 5: Add styling**

Create `web/src/styles.css`:

```css
:root {
  color: #f7f7fb;
  background: #101114;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; }
button { font: inherit; }

.app-shell {
  min-height: 100vh;
  padding: 20px;
  background:
    radial-gradient(circle at 20% 0%, rgba(123, 92, 255, 0.18), transparent 32rem),
    linear-gradient(180deg, #17181d 0%, #0f1013 100%);
}

.topbar, .panel, .controls {
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.075);
  backdrop-filter: blur(18px);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.24);
}

.topbar {
  display: flex;
  align-items: center;
  gap: 14px;
  border-radius: 18px;
  padding: 12px 14px;
}

.brand-icon {
  width: 52px;
  height: 52px;
  object-fit: contain;
}

h1, h2, p { margin: 0; }
h1 { font-size: 20px; }
h2 { font-size: 15px; margin-bottom: 12px; }
.muted, .topbar p { color: #aeb4c0; }
.usage { margin-left: auto; display: flex; gap: 10px; color: #d9d6ff; }

.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0;
  padding: 10px;
  border-radius: 14px;
}

.controls button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  border: 0;
  border-radius: 10px;
  padding: 0 12px;
  color: #f7f7fb;
  background: rgba(255, 255, 255, 0.1);
}

.controls button:disabled { opacity: 0.45; }

.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.6fr);
  gap: 14px;
}

.panel {
  border-radius: 18px;
  padding: 14px;
  overflow: hidden;
}

.roadmap ol { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }
.row { display: grid; grid-template-columns: 160px 1fr; gap: 10px; color: #c9ced8; }
.row.epic { color: #fff; font-weight: 700; margin-top: 8px; }
.row.done, .row.done-session { color: #8be28b; }
.row.blocked { color: #ff8f8f; }
.row em { grid-column: 2; color: #ffb1b1; font-style: normal; }

dl { display: grid; grid-template-columns: 92px 1fr; gap: 8px; margin: 0; }
dt { color: #aeb4c0; }
dd { margin: 0; overflow-wrap: anywhere; }

.output, .terminal { margin-top: 14px; }
pre {
  min-height: 220px;
  max-height: 42vh;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  color: #d9dee8;
}

@media (max-width: 760px) {
  .app-shell { padding: 12px; }
  .grid { grid-template-columns: 1fr; }
  .usage { flex-direction: column; gap: 2px; }
  .row { grid-template-columns: 1fr; gap: 2px; }
}
```

- [ ] **Step 6: Install and build UI**

Run:

```bash
cd web
npm install
npm run build
```

Expected: Vite production build succeeds.

- [ ] **Step 7: Commit**

```bash
git add web/package.json web/package-lock.json web/index.html web/src
git commit -m "feat: add imp web dashboard"
```

---

### Task 6: UI Verification And Server Static Mount

**Files:**
- Modify: `engine/imp_server.py`
- Modify: `README.md`
- Create: `tests/test_web_static.py`

- [ ] **Step 1: Add static mount test**

Create `tests/test_web_static.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_server import web_dist_path


def test_web_dist_path_points_to_repo_web_dist():
    path = web_dist_path()

    assert path.name == "dist"
    assert path.parent.name == "web"
```

- [ ] **Step 2: Implement static web helper**

Modify `engine/imp_server.py`:

```python
from pathlib import Path


def web_dist_path() -> Path:
    return Path(__file__).resolve().parent.parent / "web" / "dist"
```

In `create_app`, after API routes:

```python
try:
    from fastapi.staticfiles import StaticFiles
    dist = web_dist_path()
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")
except ImportError:
    pass
```

- [ ] **Step 3: Update README web usage**

Add:

```markdown
## Local Web UI

```bash
python3 -m pip install fastapi uvicorn
cd web && npm install && npm run build && cd ..
python3 _imp/imp_runner.py all --web
```

Open `http://127.0.0.1:8765`.
```

- [ ] **Step 4: Run API/static tests**

Run:

```bash
python3 -m pytest tests/test_imp_server.py tests/test_web_static.py -v
```

Expected: pass.

- [ ] **Step 5: Run full test suite**

Run:

```bash
python3 -m pytest -v
```

Expected: pass.

- [ ] **Step 6: Run UI build**

Run:

```bash
cd web && npm run build
```

Expected: Vite build succeeds and creates `web/dist`.

- [ ] **Step 7: Launch local server**

Run:

```bash
python3 engine/imp_runner.py all --web --host 127.0.0.1 --port 8765
```

Expected: server starts and serves `http://127.0.0.1:8765`.

- [ ] **Step 8: Verify visually with browser**

Use Playwright or browser tooling to check:

- desktop viewport shows header, controls, roadmap, current step, output
- mobile viewport stacks panels without overlap
- IMP icon renders
- buttons do not overflow

- [ ] **Step 9: Commit**

```bash
git add engine/imp_server.py tests/test_web_static.py README.md web/dist
git commit -m "feat: serve imp web ui locally"
```

---

## Final Verification

- [ ] Run Python tests:

```bash
python3 -m pytest -v
```

- [ ] Run web build:

```bash
cd web && npm run build
```

- [ ] Run tmux smoke:

```bash
tmux -V
python3 -m pytest tests/test_imp_tmux.py -v
```

- [ ] Run local API smoke:

```bash
python3 engine/imp_runner.py all --web --host 127.0.0.1 --port 8765
```

- [ ] Open `http://127.0.0.1:8765` and capture desktop/mobile screenshots.

---

## Self-Review Notes

- Spec coverage: existing ledger flow, deterministic Python control loop, one sequential tmux child step, API, web UI, icon usage, failure handling, and testing are all covered.
- Deferred by design: Mermaid workflow compiler, custom node authoring, parallel execution, Tauri packaging, and remote/mobile access.
- Main implementation risk: tmux runner exit-code/state reconciliation. Keep Task 2 small and verify with real tmux before wiring the runner.

