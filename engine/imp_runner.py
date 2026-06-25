#!/usr/bin/env python3
"""IMP Runner — main entry point for the IMP implementation pipeline TUI.

Usage: python3 _imp/imp_runner.py [epic-id|all] [--verbose]
"""
from __future__ import annotations

import argparse, asyncio, importlib.util, json, os, signal  # noqa: E401
import subprocess, sys, threading, time  # noqa: E401
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)

from imp_state import RunnerState, StepRecord, CurrentStep, create_initial_state  # noqa: E402
from imp_keys import start_keyreader  # noqa: E402
from imp_usage import read_usage_cache, check_threshold, is_stale, fetch_full_usage  # noqa: E402

try:
    from imp_display import build_layout  # noqa: E402
except ImportError:
    build_layout = None

# Import imp-ledger.py (hyphenated filename)
_spec = importlib.util.spec_from_file_location(
    "imp_ledger", os.path.join(SCRIPT_DIR, "imp-ledger.py")
)
imp_ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(imp_ledger)

HALT_FILE = os.path.join(SCRIPT_DIR, "HALT")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
CLAUDE_FLAGS = ["--dangerously-skip-permissions", "--verbose", "--include-partial-messages"]

_HALT_SIGNAL = (
    "\n## Halt signal\n"
    "If you discover a structural flaw that makes the story impossible to implement,\n"
    "write a short explanation to the file _imp/HALT and then exit."
)

PREAMBLE_SPEC = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the story spec without halting for user input:\n"
    "- Do NOT use HALT or ask for clarification — make reasonable assumptions\n"
    "- Do NOT present menus or wait for responses\n"
    "- Complete the full spec and write the story file as per your normal workflow"
    + _HALT_SIGNAL
)

PREAMBLE_DEV = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the full implementation without halting for user input:\n"
    "- Do NOT use HALT, do NOT ask for manual verification, do NOT wait for responses\n"
    "- If a task requires manual action (e.g. pressing F5, opening a browser), "
    "skip the verification and mark it as done with a note that manual verification is deferred\n"
    "- Make all decisions autonomously — prefer the safest reasonable choice\n"
    "- Complete all tasks and update the story file status as per your normal workflow"
    + _HALT_SIGNAL
)

PREAMBLE_REVIEW = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the full code review without halting for user input:\n"
    "- Run all adversarial review layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor)\n"
    "- Auto-apply all patch fixes directly to source files\n"
    "- Defer all decision-needed findings (log them in the story file with [Review][Defer])\n"
    "- Do NOT present menus, ask for choices, or wait for responses\n"
    "- Update the story file status and sprint-status.yaml as per your normal workflow"
    + _HALT_SIGNAL
)

class SessionLogger:
    """Appends timestamped lines to _imp/logs/sessions/session-{timestamp}.log."""

    def __init__(self) -> None:
        sessions_dir = os.path.join(LOG_DIR, "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._path = os.path.join(sessions_dir, f"session-{ts}.log")
        self._file = open(self._path, "a", encoding="utf-8")  # noqa: SIM115

    @property
    def path(self) -> str:
        return self._path

    @property
    def session_id(self) -> str:
        """Return the session timestamp ID, e.g. '20260406T120024Z'."""
        return os.path.basename(self._path).removeprefix("session-").removesuffix(".log")

    def log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._file.write(f"[{ts}] {msg}\n")
        self._file.flush()

    def close(self) -> None:
        try:
            self._file.close()
        except OSError:
            pass

def ledger_next_story(epic_id: str) -> tuple[str, dict | None]:
    """Return ("ok", story_dict), ("done", None), or ("blocked", info_dict).

    Sequential ordering: a blocked story or epic stops the search immediately
    rather than skipping to the next item. This ensures stories and epics are
    always processed in order and blocked work surfaces immediately.
    """
    ledger = imp_ledger.read_ledger()
    if not ledger:
        return ("done", None)

    epics = ledger["epics"]
    if epic_id != "all":
        epics = [e for e in epics if e["id"] == epic_id]

    for epic in epics:
        if epic["status"] == "done":
            continue
        if epic["status"] == "blocked":
            # Find the first blocked story to surface the specific reason
            for story in epic["stories"]:
                if story["status"] == "blocked":
                    return ("blocked", {
                        "story_id": story["id"],
                        "epic_id": epic["id"],
                        "reason": story.get("blocked_reason") or f"epic {epic['id']} blocked",
                    })
            return ("blocked", {
                "story_id": None,
                "epic_id": epic["id"],
                "reason": f"epic {epic['id']} is blocked",
            })

        for story in epic["stories"]:
            if story["status"] == "done":
                continue
            if story["status"] == "blocked":
                return ("blocked", {
                    "story_id": story["id"],
                    "epic_id": epic["id"],
                    "reason": story.get("blocked_reason") or f"{story['id']} blocked",
                })
            return ("ok", {
                "id": story["id"],
                "epic_id": epic["id"],
                "status": story["status"],
                "current_step": story["current_step"],
                "steps": story["steps"],
            })

    return ("done", None)


def ledger_get_attempts(story_id: str, step: str) -> int:
    """Return the attempts count for a story step."""
    ledger = imp_ledger.read_ledger()
    if not ledger:
        return 0
    _, story = imp_ledger._find_story(ledger, story_id)
    if not story:
        return 0
    return story["steps"].get(step, {}).get("attempts", 0)


def ledger_check_sprint_status(story_id: str) -> str:
    """Read sprint-status.yaml and return the status string for a story."""
    sprint_path = os.path.join(
        imp_ledger.PROJECT_ROOT,
        imp_ledger.CONFIG.get("sprint_status", ""),
    )
    if not os.path.exists(sprint_path):
        return "unknown"

    _, dev_status = imp_ledger.parse_sprint_status(sprint_path)

    if story_id in dev_status:
        return dev_status[story_id]

    for key, val in dev_status.items():
        if key.startswith(story_id):
            return val

    return "unknown"


def ledger_story_blocked(story_id: str, reason: str) -> None:
    """Mark a story as blocked WITHOUT printing to stdout."""
    ledger = imp_ledger.read_ledger()
    if not ledger:
        return
    epic, story = imp_ledger._find_story(ledger, story_id)
    if not story:
        return
    story["status"] = "blocked"
    story["blocked_reason"] = reason
    epic["status"] = "blocked"
    ledger["global_status"] = "blocked"
    imp_ledger.write_ledger(ledger)


def ledger_story_interrupted(story_id: str) -> None:
    """Mark story as interrupted (user cancellation).

    Unlike 'blocked', interrupted does NOT cascade to epic or global status —
    it is a temporary state that auto-resets to 'pending' on the next run start.
    """
    ledger = imp_ledger.read_ledger()
    if not ledger:
        return
    _, story = imp_ledger._find_story(ledger, story_id)
    if not story:
        return
    story["status"] = "interrupted"
    story["blocked_reason"] = None
    # Intentionally do NOT update epic["status"] or ledger["global_status"]
    imp_ledger.write_ledger(ledger)


def ledger_reset_interrupted(session) -> None:
    """Reset all interrupted stories back to pending at run start.

    Also resets the review attempt counter so that stories stopped by the
    review cap can retry with a freshly-configured max_review_attempts.
    """
    ledger = imp_ledger.read_ledger()
    if not ledger:
        return
    changed = False
    for epic in ledger["epics"]:
        for story in epic["stories"]:
            if story["status"] == "interrupted":
                story["status"] = "pending"
                story["blocked_reason"] = None
                # Reset review attempts so a bumped max_review_attempts takes effect
                if "review" in story.get("steps", {}):
                    story["steps"]["review"]["attempts"] = 0
                    story["steps"]["review"]["status"] = "pending"
                session.log(f"Auto-reset interrupted story: {story['id']}")
                changed = True
    if changed:
        imp_ledger.write_ledger(ledger)


def _build_roadmap_rows(epic_id: str, session_id: str = "") -> list:
    """Build display rows for the roadmap panel.

    Each row is a tuple: (type, id, status, detail, blocked_reason)
    where type is "epic" or "story".
    Stories completed in the current session use status "done-session".
    """
    ledger = imp_ledger.read_ledger()
    if not ledger:
        return []

    epics = ledger["epics"]
    if epic_id != "all":
        epics = [e for e in epics if e["id"] == epic_id]

    rows = []
    for epic in epics:
        epic_title = epic.get("title", epic["id"])
        rows.append(("epic", epic["id"], epic["status"], epic_title, None))
        for story in epic.get("stories", []):
            if story["status"] == "pending":
                step_chain = ""
            else:
                step_chain = format_step_chain(story.get("steps", {}))
            blocked_reason = story.get("blocked_reason") if story["status"] == "blocked" else None
            display_status = story["status"]
            if (display_status == "done" and session_id
                    and story.get("steps", {}).get("review", {}).get("session") == session_id):
                display_status = "done-session"
            rows.append(("story", story["id"], display_status, step_chain, blocked_reason))

    return rows


def ledger_get_pending_story_ids(epic_id: str) -> tuple[list[str], dict[str, str]]:
    """Get pending story IDs reachable under sequential ordering.

    Stops at the first blocked story or epic — stories after a block are
    unreachable until the block is resolved, so they are excluded from the
    pending display list.

    Returns (story_ids, next_steps) where next_steps maps story_id → first
    non-done step (spec/dev/review) so the Progress panel can show where
    each story will start.
    """
    ledger = imp_ledger.read_ledger()
    if not ledger:
        return [], {}

    epics = ledger["epics"]
    if epic_id != "all":
        epics = [e for e in epics if e["id"] == epic_id]

    result: list[str] = []
    next_steps: dict[str, str] = {}
    for epic in epics:
        if epic["status"] == "done":
            continue
        if epic["status"] == "blocked":
            break  # No reachable stories past a blocked epic
        for story in epic["stories"]:
            if story["status"] == "done":
                continue
            if story["status"] == "blocked":
                break  # No reachable stories past a blocked story
            result.append(story["id"])
            # Find first non-done step so the UI can show where it'll start
            steps = story.get("steps", {})
            first_step = next(
                (s for s in ["spec", "dev", "review"] if steps.get(s, {}).get("status") != "done"),
                "spec",
            )
            next_steps[story["id"]] = first_step
    return result, next_steps


def ledger_count_done_stories(epic_id: str) -> int:
    """Count stories already marked done in the ledger (pre-session baseline)."""
    ledger = imp_ledger.read_ledger()
    if not ledger:
        return 0
    epics = ledger["epics"]
    if epic_id != "all":
        epics = [e for e in epics if e["id"] == epic_id]
    return sum(1 for epic in epics for story in epic.get("stories", []) if story["status"] == "done")


def _parse_pause_after(config: dict) -> list[str]:
    """Return the pause_after story ID list from config, supporting both YAML list and CSV string."""
    raw = config.get("pause_after", [])
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if s]
    if isinstance(raw, str) and raw.strip():
        return [s.strip() for s in raw.split(",") if s.strip()]
    return []


# -- Stream-json parser (inlined from stream-filter.py) --

# Primary argument to display per tool (most human-readable)
_TOOL_PRIMARY_ARG: dict[str, str] = {
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "Glob": "pattern",
    "Grep": "pattern",
    "Bash": "command",
    "Agent": "description",
    "WebFetch": "url",
    "WebSearch": "query",
    "NotebookEdit": "notebook_path",
    "TaskCreate": "name",
    "TaskUpdate": "task_id",
}

_MAX_ARG_LEN = 100


def _tool_display_arg(name: str, inp: dict) -> str:
    """Return the most meaningful single-line argument for a tool call."""
    key = _TOOL_PRIMARY_ARG.get(name)
    val = inp.get(key) if key else None
    if val is None:
        # Fallback: first string value
        for v in inp.values():
            if isinstance(v, str):
                val = v
                break
    if val is None:
        return ""
    val = str(val).replace("\n", " ").strip()
    return val[:_MAX_ARG_LEN] + "…" if len(val) > _MAX_ARG_LEN else val


class StreamParser:
    """Stateful stream-json parser that accumulates tool input across lines.

    Emits complete lines only — text deltas are buffered until a newline,
    tool calls emit as a single line, no surrounding blank lines.
    """

    def __init__(self) -> None:
        self._tool_name: str | None = None
        self._tool_input_buf: str = ""
        self._text_buf: str = ""

    def feed(self, raw: str) -> list[str]:
        """Parse one stream-json line. Returns zero or more complete lines."""
        raw = raw.strip()
        if not raw:
            return []
        out: list[str] = []
        try:
            obj = json.loads(raw)
            evt = obj.get("event", {})
            etype = evt.get("type", "")

            if etype == "content_block_start":
                block = evt.get("content_block", {})
                if block.get("type") == "tool_use":
                    if self._text_buf.strip():
                        out.append(self._text_buf.rstrip())
                        self._text_buf = ""
                    self._tool_name = block.get("name", "?")
                    self._tool_input_buf = ""
                else:
                    self._tool_name = None

            elif etype == "content_block_delta":
                delta = evt.get("delta", {})
                dtype = delta.get("type", "")
                if dtype == "text_delta":
                    self._text_buf += delta.get("text", "")
                    while "\n" in self._text_buf:
                        line, self._text_buf = self._text_buf.split("\n", 1)
                        if line.strip():
                            out.append(line)
                elif dtype == "input_json_delta":
                    self._tool_input_buf += delta.get("partial_json", "")

            elif etype == "content_block_stop":
                if self._tool_name is not None:
                    try:
                        inp = json.loads(self._tool_input_buf) if self._tool_input_buf.strip() else {}
                    except json.JSONDecodeError:
                        inp = {}
                    arg = _tool_display_arg(self._tool_name, inp)
                    label = f"[{self._tool_name}] {arg}" if arg else f"[{self._tool_name}]"
                    out.append(label)
                    self._tool_name = None
                    self._tool_input_buf = ""

            elif etype == "message_stop":
                if self._text_buf.strip():
                    out.append(self._text_buf.rstrip())
                    self._text_buf = ""

        except (json.JSONDecodeError, KeyError):
            pass
        return out


# -- Step chain formatter --

def format_step_chain(steps: dict) -> str:
    """Format steps as a compact chain like 'spec·dev(x2)·review'."""
    parts: list[str] = []
    for step_name in imp_ledger.PIPELINE_STEPS:
        info = steps.get(step_name, {})
        status = info.get("status", "pending")
        attempts = info.get("attempts", 0)

        if status == "done":
            label = step_name
        elif status == "in-progress":
            label = step_name.upper()
        else:
            label = "---"

        if attempts > 1:
            label = f"{label}(x{attempts})"

        parts.append(label)
    return "·".join(parts)


# -- Subprocess runner --

async def run_claude_subprocess(
    args: list[str],
    jsonl_log_path: str,
    readable_log_path: str,
    state: RunnerState,
) -> int:
    """Run a claude subprocess, stream output, return exit code.

    The subprocess is started in its own process group (os.setsid) so that
    quit_now() can kill the entire group including any children claude spawns.
    """
    os.makedirs(os.path.dirname(jsonl_log_path), exist_ok=True)
    os.makedirs(os.path.dirname(readable_log_path), exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=PROJECT_ROOT,
        preexec_fn=os.setsid,  # new process group — enables killpg in quit_now
        limit=2**20,  # 1MB per line — default 64KB can overflow on long stream-json lines
    )
    state.subprocess_pid = proc.pid

    parser = StreamParser()
    with (
        open(jsonl_log_path, "w", encoding="utf-8") as jsonl_f,
        open(readable_log_path, "w", encoding="utf-8") as readable_f,
    ):
        while True:
            raw_line = await proc.stdout.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace")
            jsonl_f.write(line)
            jsonl_f.flush()

            for text in parser.feed(line):
                readable_f.write(text + "\n")
                readable_f.flush()
                state.append_output(text)
                # Track tool call counts for stats display
                if text.startswith("[") and "]" in text:
                    tool_name = text[1:text.index("]")]
                    if tool_name and tool_name[0].isupper():
                        state.increment_tool_count(tool_name)

    exit_code = await proc.wait()
    state.subprocess_pid = None
    return exit_code


# -- Step runners --

def _build_log_paths(story_id: str, step: str, attempt: int) -> tuple[str, str]:
    """Return (jsonl_path, readable_path) for a step attempt."""
    base = os.path.join(LOG_DIR, story_id)
    return (
        os.path.join(base, f"{step}-attempt-{attempt}.jsonl"),
        os.path.join(base, f"{step}-attempt-{attempt}.log"),
    )


def _get_step_chain(epic_id: str) -> str:
    """Read current story steps from ledger and format as chain string."""
    result, story = ledger_next_story(epic_id)
    return format_step_chain(story.get("steps", {}) if (result == "ok" and story) else {})


def _begin_step(
    state: RunnerState, story_id: str, step: str,
    attempt: int, max_attempts: int,
) -> None:
    """Set current step on state and clear output buffer."""
    state.set_current(CurrentStep(
        story_id=story_id, step=step, attempt=attempt,
        max_attempts=max_attempts,
        step_chain=_get_step_chain(state.epic_id),
        start_time=time.time(),
        log_path=os.path.join(LOG_DIR, story_id, f"{step}-attempt-{attempt}.log"),
    ))
    state.clear_output()
    if str(state.config.get("output_on_step_start", "true")).lower() in ("true", "1", "yes"):
        with state._lock:
            state.output_visible = True


def _record_completed(state: RunnerState, story_id: str, elapsed: float, log: str) -> None:
    """Append a StepRecord for a completed step."""
    usage_5h, _, _ = read_usage_cache()
    state.append_completed(StepRecord(
        story_id=story_id,
        steps_summary=_get_step_chain(state.epic_id),
        wall_time_s=elapsed,
        completed_at=datetime.now(timezone.utc).strftime("%H:%M"),
        usage_5h_after=usage_5h,
        log_path=log,
    ))


def _build_claude_args(prompt: str, model: str, effort: str) -> list[str]:
    """Build the full claude --print argument list."""
    return [
        "claude", "--print", *CLAUDE_FLAGS,
        prompt, "--model", model, "--effort", effort,
        "--output-format", "stream-json",
    ]


async def _run_spec(
    state: RunnerState, session: SessionLogger, story_id: str,
    story_file: str, model: str, effort: str,
) -> None:
    """Run the spec step for a story."""
    if os.path.isfile(os.path.join(PROJECT_ROOT, story_file)):
        session.log(f"{story_id}/spec: story file exists, skipping")
        imp_ledger.cmd_step_done(story_id, "spec")
        return

    prompt = (
        f"/bmad-create-story {story_id}\n\n"
        f"IMPORTANT: The story file MUST be written to exactly this path: `{story_file}`\n"
        + PREAMBLE_SPEC
    )

    imp_ledger.cmd_step_attempt(story_id, "spec")
    attempt_num = ledger_get_attempts(story_id, "spec")
    _begin_step(state, story_id, "spec", attempt_num, 0)

    jsonl_path, readable_path = _build_log_paths(story_id, "spec", attempt_num)
    rel_log = os.path.relpath(jsonl_path, SCRIPT_DIR)
    session.log(f"{story_id}/spec: attempt {attempt_num} starting  →  {rel_log}")

    start = time.time()
    await run_claude_subprocess(
        _build_claude_args(prompt, model, effort), jsonl_path, readable_path, state,
    )
    elapsed = time.time() - start
    state.clear_current()

    # User cancelled mid-step — mark as interrupted, not blocked
    if state.should_exit:
        ledger_story_interrupted(story_id)
        session.log(f"{story_id}/spec: interrupted by user")
        return

    if os.path.isfile(os.path.join(PROJECT_ROOT, story_file)):
        imp_ledger.cmd_step_done(story_id, "spec", session.session_id, rel_log)
        session.log(f"{story_id}/spec: created in {elapsed:.0f}s  →  {rel_log}")
        _record_completed(state, story_id, elapsed, jsonl_path)
    else:
        reason = f"spec failed — story file not created at {story_file}"
        ledger_story_blocked(story_id, reason)
        session.log(f"{story_id}/spec: BLOCKED — {reason}")
        state.request_exit(1)


async def _run_dev(
    state: RunnerState, session: SessionLogger, story_id: str,
    story_file: str, model: str, effort: str,
) -> None:
    """Run the dev step for a story."""
    imp_ledger.cmd_step_attempt(story_id, "dev")
    attempt_num = ledger_get_attempts(story_id, "dev")
    _begin_step(state, story_id, "dev", attempt_num, 0)

    jsonl_path, readable_path = _build_log_paths(story_id, "dev", attempt_num)
    rel_log = os.path.relpath(jsonl_path, SCRIPT_DIR)
    session.log(f"{story_id}/dev: attempt {attempt_num} starting  →  {rel_log}")

    prompt = f"/bmad-dev-story {story_file}\n{PREAMBLE_DEV}"

    start = time.time()
    exit_code = await run_claude_subprocess(
        _build_claude_args(prompt, model, effort), jsonl_path, readable_path, state,
    )
    elapsed = time.time() - start
    state.clear_current()

    # User cancelled mid-step — mark as interrupted, not blocked
    if state.should_exit:
        ledger_story_interrupted(story_id)
        session.log(f"{story_id}/dev: interrupted by user")
        return

    if exit_code == 0:
        imp_ledger.cmd_step_done(story_id, "dev", session.session_id, rel_log)
        session.log(f"{story_id}/dev: completed in {elapsed:.0f}s  →  {rel_log}")
        _record_completed(state, story_id, elapsed, jsonl_path)
    else:
        reason = f"dev failed (exit {exit_code})"
        ledger_story_blocked(story_id, reason)
        session.log(f"{story_id}/dev: BLOCKED — {reason}")
        state.request_exit(1)


async def _run_review(
    state: RunnerState, session: SessionLogger, story_id: str,
    story_file: str, model: str, effort: str, max_review: int,
) -> None:
    """Run the review step for a story."""
    attempts_so_far = ledger_get_attempts(story_id, "review")

    if max_review > 0 and attempts_so_far >= max_review:
        session.log(
            f"{story_id}/review: cap reached ({attempts_so_far}/{max_review})"
            f" — marking interrupted so next run retries with fresh config"
        )
        ledger_story_interrupted(story_id)
        state.request_exit(0)
        return

    imp_ledger.cmd_step_attempt(story_id, "review")
    attempt_num = ledger_get_attempts(story_id, "review")
    _begin_step(state, story_id, "review", attempt_num, max_review)

    jsonl_path, readable_path = _build_log_paths(story_id, "review", attempt_num)
    rel_log = os.path.relpath(jsonl_path, SCRIPT_DIR)
    session.log(f"{story_id}/review: attempt {attempt_num}/{max_review} starting  →  {rel_log}")

    prompt = f"/bmad-code-review {story_file}\n{PREAMBLE_REVIEW}"

    start = time.time()
    await run_claude_subprocess(
        _build_claude_args(prompt, model, effort), jsonl_path, readable_path, state,
    )
    elapsed = time.time() - start
    state.clear_current()

    # User cancelled mid-step — mark as interrupted, not blocked
    if state.should_exit:
        ledger_story_interrupted(story_id)
        session.log(f"{story_id}/review: interrupted by user")
        return

    sprint_status = ledger_check_sprint_status(story_id)
    session.log(f"{story_id}/review: sprint-status={sprint_status} in {elapsed:.0f}s")

    if sprint_status == "done":
        imp_ledger.cmd_step_done(story_id, "review", session.session_id, rel_log)
        imp_ledger.cmd_story_done(story_id)
        session.log(f"{story_id}: story complete — committing  →  {rel_log}")
        _record_completed(state, story_id, elapsed, jsonl_path)

        try:
            subprocess.run(
                ["git", "add", "-A"], cwd=PROJECT_ROOT,
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["git", "commit", "-m", f"feat({story_id}): implement story"],
                cwd=PROJECT_ROOT, capture_output=True, timeout=30,
            )
            session.log(f"{story_id}: git commit created")
        except (subprocess.SubprocessError, OSError) as exc:
            session.log(f"{story_id}: git commit failed (non-fatal): {exc}")

        state.remove_pending(story_id)
    else:
        session.log(
            f"{story_id}/review: issues found ({attempt_num}/{max_review}) "
            f"— sending back to dev"
        )
        imp_ledger.cmd_set_step(story_id, "dev")


# -- Between-step checks --

def _check_between_steps(
    state: RunnerState,
    config: dict,
    session: SessionLogger,
) -> bool:
    """Run between-step checks. Returns True if pipeline should stop."""
    # Reload config.yaml from disk at every step boundary
    fresh = imp_ledger.load_config()
    state.reload_config(fresh)
    session.log("Config reloaded from disk")
    config = state.config  # use fresh config for all checks below

    five_h = state.usage_5h
    seven_d = state.usage_7d

    # Config values — base_limit_pct supersedes legacy usage_limit_threshold
    base_limit = int(config.get("base_limit_pct", 0) or config.get("usage_limit_threshold", 0))
    limit_7d = int(config.get("limit_7d_pct", 0))
    extra_limit_eur = float(config.get("extra_limit_eur", 0) or 0)
    allow_extra = extra_limit_eur > 0  # extra credits allowed iff a cap is set
    on_base = config.get("on_base_limit", "pause")
    on_extra = config.get("on_extra_limit", "quit")

    # 1. Spillover guard — stop before extra credits are charged when no cap set
    if not allow_extra and five_h is not None and five_h >= 98:
        session.log(f"Spillover guard: 5h at {five_h:.0f}%, extra not allowed — stopping")
        state.request_exit(0)
        return True

    # 2. Base caps — 5h and 7d (first hit wins)
    limit_triggered = False
    limit_reason = ""
    if base_limit > 0 and five_h is not None and five_h >= base_limit:
        limit_reason = f"5h usage {five_h:.0f}% >= {base_limit}%"
        limit_triggered = True
    elif limit_7d > 0 and seven_d is not None and seven_d >= limit_7d:
        limit_reason = f"7d usage {seven_d:.0f}% >= {limit_7d}%"
        limit_triggered = True

    if limit_triggered:
        # PL/QL runtime toggles override config default
        if state.pause_on_limit:
            action = "pause"
        elif state.quit_on_limit:
            action = "quit"
        else:
            action = on_base

        session.log(f"Limit triggered: {limit_reason} — action: {action}")
        if action == "pause":
            state.set_paused()
        else:
            state.request_exit(0)
            return True

    # 3. Extra cap — financial hard stop
    if allow_extra and extra_limit_eur > 0 and state.usage_extra_spent is not None:
        try:
            extra_spent = float(state.usage_extra_spent)
            if extra_spent >= extra_limit_eur:
                session.log(
                    f"Extra cap: €{extra_spent:.2f} >= €{extra_limit_eur:.2f}"
                    f" — action: {on_extra}"
                )
                if on_extra == "pause":
                    state.set_paused()
                else:
                    state.request_exit(0)
                    return True
        except (ValueError, TypeError):
            pass

    # 4. pause_after — story-level planned stops (consume flag unconditionally)
    last_story = state.last_completed_story_id
    state.last_completed_story_id = None
    if last_story and last_story in _parse_pause_after(config):
        session.log(f"pause_after: pausing after {last_story}")
        state.set_paused()

    # 5. Epic boundary pause (consume flag unconditionally)
    crossed = state.epic_boundary_crossed
    state.epic_boundary_crossed = False
    if crossed and str(config.get("pause_between_epics", "false")).lower() in ("true", "1", "yes"):
        session.log("pause_between_epics: pausing at epic boundary")
        state.set_paused()

    # 6. Wait while pause_after_step is True
    while state.pause_after_step and not state.should_exit:
        time.sleep(0.5)
    state.paused_at = None  # clear timer once resumed

    if state.should_exit:
        return True

    # 7. Check quit_after_step flag
    if state.quit_after_step:
        session.log("Quit-after-step requested by user")
        state.request_exit(0)
        return True

    # 8. Check HALT file
    if os.path.isfile(HALT_FILE):
        try:
            with open(HALT_FILE, encoding="utf-8") as f:
                reason = f.read().strip() or "HALT file detected"
        except OSError:
            reason = "HALT file detected"
        session.log(f"HALT: {reason}")
        state.set_halt(reason)
        return True

    return False


# -- Usage poller --

def _usage_poller_thread(state: RunnerState, interval: float = 60.0) -> None:
    """Background thread: fetch full usage every `interval` seconds.

    Calls check-limits.sh, stores result in state. Exits when display_exit is set.
    Falls back gracefully if check-limits.sh is unavailable.
    """
    while not state.display_exit:
        data = fetch_full_usage()
        if data:
            state.update_full_usage(
                usage_5h=data.get("five_hour_pct"),
                usage_7d=data.get("seven_day_pct"),
                usage_sonnet=data.get("sonnet_pct"),
                usage_extra_pct=data.get("extra_pct"),
                usage_extra_spent=data.get("extra_spent_eur"),
                usage_extra_account_cap=data.get("extra_limit_eur"),
                usage_decision=data.get("decision", "PROCEED"),
                five_h_resets_at=data.get("five_hour_resets"),
                seven_d_resets_at=data.get("seven_day_resets"),
                updated_at=time.time(),
            )
        # Sleep in 0.5s slices so display_exit is detected promptly
        elapsed = 0.0
        while elapsed < interval and not state.display_exit:
            time.sleep(0.5)
            elapsed += 0.5


# -- Pipeline main (async) --

async def pipeline_main(state: RunnerState, session: SessionLogger) -> None:
    """Main pipeline loop — runs in a background thread's asyncio loop."""
    config = imp_ledger.CONFIG

    # Clean up stale HALT file
    if os.path.isfile(HALT_FILE):
        try:
            os.remove(HALT_FILE)
            session.log("Removed stale HALT file")
        except OSError:
            pass

    # Auto-reset any stories left in "interrupted" state from a prior cancelled run
    ledger_reset_interrupted(session)

    # Set pending stories and initial roadmap
    pending, next_steps = ledger_get_pending_story_ids(state.epic_id)
    state.set_pending_stories(pending, next_steps)
    state.pre_session_done_count = ledger_count_done_stories(state.epic_id)
    state.set_roadmap(_build_roadmap_rows(state.epic_id, session.session_id))

    while not state.should_exit:
        # Refresh roadmap for history view
        state.set_roadmap(_build_roadmap_rows(state.epic_id, session.session_id))

        # Get next story before the gate so epic boundary can be detected
        result, story = ledger_next_story(state.epic_id)

        if result == "done":
            session.log(f"All stories complete for: {state.epic_id}")
            if state.epic_id != "all":
                imp_ledger.cmd_epic_done(state.epic_id)
            state.request_exit(0)
            return

        if result == "blocked":
            info = story or {}
            story_id_blocked = info.get("story_id") or info.get("epic_id") or "unknown"
            reason = info.get("reason", "unknown reason")
            halt_msg = f"Blocked at {story_id_blocked}: {reason}"
            session.log(f"BLOCKED: {halt_msg}")
            state.set_halt(halt_msg)
            return

        story_id = story["id"]
        next_epic_id = story["epic_id"]
        step = story.get("current_step") or ""

        # Epic boundary detection — flag consumed by _check_between_steps phase 5
        if state.current_epic_id is not None and next_epic_id != state.current_epic_id:
            state.epic_boundary_crossed = True
        state.current_epic_id = next_epic_id

        # Between-step checks (config reload + limits + pause_after + epic boundary)
        if _check_between_steps(state, config, session):
            return

        # Re-read config fresh after possible reload — affects next step's model/effort
        cfg = state.config
        model_spec = str(cfg.get("model_spec", "claude-sonnet-4-6"))
        effort_spec = str(cfg.get("effort_spec", "medium"))
        model_dev = str(cfg.get("model_dev", "claude-sonnet-4-6"))
        effort_dev = str(cfg.get("effort_dev", "high"))
        model_review = str(cfg.get("model_review", "claude-opus-4-6"))
        effort_review = str(cfg.get("effort_review", "high"))
        max_review = int(cfg.get("max_review_attempts", 3))
        artifacts_dir = str(cfg.get("artifacts_dir", "_bmad-output/implementation-artifacts"))

        story_file = f"{artifacts_dir}/{story_id}.md"
        session.log(f"Next: {story_id} -> step: {step}")

        if step == "spec":
            await _run_spec(
                state, session, story_id, story_file,
                model_spec, effort_spec,
            )

        elif step == "dev":
            await _run_dev(
                state, session, story_id, story_file,
                model_dev, effort_dev,
            )

        elif step == "review":
            await _run_review(
                state, session, story_id, story_file,
                model_review, effort_review, max_review,
            )
            # If story is fully done (removed from pending), flag for pause_after check
            if story_id not in state.pending_stories:
                state.last_completed_story_id = story_id

        elif step == "":
            # current_step is null — story should already be done
            session.log(f"{story_id}: no pending step — marking done")
            imp_ledger.cmd_story_done(story_id)
            state.remove_pending(story_id)

        else:
            reason = f"unknown step '{step}' for {story_id}"
            ledger_story_blocked(story_id, reason)
            session.log(f"BLOCKED: {reason}")
            state.request_exit(1)
            return


# -- Threading + main --

def _pipeline_thread(state: RunnerState, session: SessionLogger) -> None:
    """Background thread entry: run the async pipeline loop."""
    try:
        asyncio.run(pipeline_main(state, session))
    except Exception as exc:
        session.log(f"Pipeline thread crashed: {exc}")
        state.request_exit(1)


def _make_quit_now(state: RunnerState, session: SessionLogger):
    """Return a callback that kills the subprocess and requests exit."""

    def quit_now() -> None:
        session.log("Quit-now triggered")
        pid = state.subprocess_pid
        if pid is not None:
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                # Give the process group a moment to exit cleanly
                time.sleep(0.3)
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except OSError:
                    pass  # Already gone — that's fine
            except OSError:
                pass
        # Roll back current step if in progress
        current = state.current
        if current is not None:
            try:
                imp_ledger.cmd_step_interrupted(current.story_id, current.step)
            except Exception:
                pass
        state.close_display()  # closes both pipeline and display immediately

    return quit_now


def main() -> None:
    """Entry point — parse args, start threads, run display loop."""
    parser = argparse.ArgumentParser(
        description="IMP Runner — automated story implementation pipeline",
    )
    parser.add_argument(
        "epic_id",
        nargs="?",
        default="all",
        help="Epic ID to process, or 'all' (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )
    args = parser.parse_args()

    # Load config and verify ledger exists
    config = imp_ledger.CONFIG
    ledger = imp_ledger.read_ledger()
    if not ledger:
        print("No ledger found. Run: python3 _imp/imp-ledger.py init <sprint-status-path>")
        sys.exit(1)

    # Also load runtime config from ledger
    ledger_config = ledger.get("config", {})
    merged_config = {**config, **{k: str(v) for k, v in ledger_config.items()}}

    # Create state
    state = create_initial_state(config=merged_config, epic_id=args.epic_id)

    # Set pending stories and initial roadmap for preflight display
    pending, next_steps = ledger_get_pending_story_ids(args.epic_id)
    state.set_pending_stories(pending, next_steps)
    state.pre_session_done_count = ledger_count_done_stories(args.epic_id)
    state.set_roadmap(_build_roadmap_rows(args.epic_id))  # no session yet — pre-launch view

    # Create session logger
    session = SessionLogger()
    session.log(f"IMP Runner started — epic={args.epic_id} verbose={args.verbose}")

    # Build quit callback
    quit_now = _make_quit_now(state, session)

    # Build config reload callback (used by r key and between-step auto-reload)
    def reload_config_now() -> None:
        fresh = imp_ledger.load_config()
        state.reload_config(fresh)
        session.log("Config reloaded by user (r key)")

    # Start keypress reader (daemon) — active during preflight too
    key_t = threading.Thread(
        target=start_keyreader,
        args=(state, quit_now, reload_config_now),
        daemon=True,
        name="keyreader",
    )
    key_t.start()

    # Start usage poller (daemon) — fires immediately, then every 60s
    usage_t = threading.Thread(
        target=_usage_poller_thread,
        args=(state,),
        daemon=True,
        name="usage-poller",
    )
    usage_t.start()

    # Main thread: display loop
    pipeline_t = None
    try:
        if build_layout is not None:
            from rich.live import Live
            from rich.console import Console

            console = Console(force_terminal=True)
            with Live(
                build_layout(state),
                console=console,
                refresh_per_second=10,  # Faster during preflight for snappy arrow-key response
                screen=True,
            ) as live:
                # Preflight phase — show roadmap, wait for Enter
                while state.app_phase == "preflight" and not state.display_exit:
                    live.update(build_layout(state))
                    time.sleep(0.05)

                if not state.display_exit:
                    # User confirmed — start the pipeline
                    session.log("User confirmed launch — starting pipeline")
                    pipeline_t = threading.Thread(
                        target=_pipeline_thread,
                        args=(state, session),
                        daemon=True,
                        name="pipeline",
                    )
                    pipeline_t.start()

                    # Running phase — normal display loop
                    while not state.display_exit:
                        live.update(build_layout(state))
                        time.sleep(0.05)
        else:
            # Fallback: no display module — skip preflight, run headless
            session.log("Warning: imp_display not available, running headless")
            state.confirm_launch()
            pipeline_t = threading.Thread(
                target=_pipeline_thread,
                args=(state, session),
                daemon=True,
                name="pipeline",
            )
            pipeline_t.start()
            while not state.should_exit:
                time.sleep(0.5)

    except KeyboardInterrupt:
        quit_now()

    # Cleanup
    session.log(f"Exiting with code {state.exit_code}")
    session.close()

    # Give pipeline thread a moment to finish
    if pipeline_t is not None:
        pipeline_t.join(timeout=5.0)

    sys.exit(state.exit_code)


if __name__ == "__main__":
    main()
