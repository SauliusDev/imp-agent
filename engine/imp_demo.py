from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from imp_state import CurrentStep, RunnerState, create_initial_state


DEMO_LEDGER_PATH = Path(__file__).resolve().parent.parent / "_imp" / "demo" / "ledger.json"
PIPELINE_STEPS = ("spec", "dev", "review")


def _step_chain(steps: dict) -> str:
    parts = []
    for name in PIPELINE_STEPS:
        status = steps.get(name, {}).get("status", "pending")
        if status == "done":
            parts.append(f"{name}:done")
        elif status == "in-progress":
            parts.append(f"{name}:running")
        else:
            parts.append(f"{name}:pending")
    return " | ".join(parts)


def _demo_rows(ledger: dict, epic_id: str) -> list[list[str | None]]:
    epics = ledger.get("epics", [])
    if epic_id != "all":
        epics = [epic for epic in epics if epic.get("id") == epic_id]

    rows: list[list[str | None]] = []
    for epic in epics:
        rows.append([
            "epic",
            epic["id"],
            epic.get("status", "pending"),
            epic.get("title", epic["id"]),
            None,
        ])
        for story in epic.get("stories", []):
            status = story.get("status", "pending")
            rows.append([
                "story",
                story["id"],
                status,
                _step_chain(story.get("steps", {})),
                story.get("blocked_reason") if status == "blocked" else None,
            ])
    return rows


def _demo_pending(ledger: dict, epic_id: str) -> tuple[list[str], dict[str, str]]:
    epics = ledger.get("epics", [])
    if epic_id != "all":
        epics = [epic for epic in epics if epic.get("id") == epic_id]

    pending: list[str] = []
    next_steps: dict[str, str] = {}
    for epic in epics:
        if epic.get("status") in {"done", "blocked"}:
            continue
        for story in epic.get("stories", []):
            if story.get("status") in {"done", "blocked"}:
                continue
            pending.append(story["id"])
            steps = story.get("steps", {})
            next_steps[story["id"]] = next(
                (name for name in PIPELINE_STEPS if steps.get(name, {}).get("status") != "done"),
                "review",
            )
    return pending, next_steps


def create_demo_state(epic_id: str) -> RunnerState:
    ledger = json.loads(DEMO_LEDGER_PATH.read_text())
    config = {"agent_provider": "codex", **ledger.get("config", {})}
    state = create_initial_state(config=config, epic_id=epic_id)
    pending, next_steps = _demo_pending(ledger, epic_id)
    state.set_pending_stories(pending, next_steps)
    state.set_roadmap(_demo_rows(ledger, epic_id))
    state.update_full_usage(
        usage_5h=18,
        usage_7d=31,
        usage_sonnet=42,
        usage_extra_pct=6,
        usage_extra_spent="1.70",
        usage_extra_account_cap="30.00",
        usage_decision="PROCEED",
        five_h_resets_at=None,
        seven_d_resets_at=None,
        updated_at=time.time(),
    )
    state.append_output("Demo mode loaded from _imp/demo/ledger.json")
    state.append_output("No tmux sessions or agents will be launched.")
    state.append_output("Press Run to simulate the current story step.")
    return state


@dataclass(frozen=True)
class DemoCallbacks:
    start_run: Callable[[], None]
    pause: Callable[[], None]
    resume: Callable[[], None]
    quit_now: Callable[[], None]
    reload_config: Callable[[], None]


def create_demo_callbacks(state: RunnerState) -> DemoCallbacks:
    def start_run() -> None:
        with state._lock:
            if state.current is not None:
                state.output_lines.append((time.time(), "Demo run already active."))
                return
            story_id = state.pending_stories[0] if state.pending_stories else "demo-story"
            step = state.pending_next_steps.get(story_id, "dev")
            state.app_phase = "running"
            state.current = CurrentStep(
                story_id=story_id,
                step=step,
                attempt=1,
                max_attempts=3,
                step_chain="spec:done | dev:running | review:pending",
                start_time=time.time(),
                log_path="_imp/demo/logs/demo-run.log",
                tmux_session="demo-imp-agent",
            )
            state.output_lines.append((time.time(), f"Demo run started: {story_id} / {step}"))

    def pause() -> None:
        with state._lock:
            state.pause_after_step = True
            state.paused_at = time.time()
            state.app_phase = "paused"
            state.output_lines.append((time.time(), "Demo run paused."))

    def resume() -> None:
        with state._lock:
            state.pause_after_step = False
            state.paused_at = None
            state.app_phase = "running" if state.current is not None else "preflight"
            state.output_lines.append((time.time(), "Demo run resumed."))

    def quit_now() -> None:
        with state._lock:
            state.current = None
            state.app_phase = "done"
            state.should_exit = True
            state.display_exit = True
            state.exit_code = 0
            state.output_lines.append((time.time(), "Demo server stopped."))

    def reload_config() -> None:
        state.append_output("Demo config reload requested; fixture data is unchanged.")

    return DemoCallbacks(
        start_run=start_run,
        pause=pause,
        resume=resume,
        quit_now=quit_now,
        reload_config=reload_config,
    )
