"""Thread-safe shared state for the IMP runner TUI."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StepRecord:
    """One completed story step — immutable once created."""

    story_id: str
    steps_summary: str  # e.g. "spec·dev·review"
    wall_time_s: float
    completed_at: str  # HH:MM
    usage_5h_after: Optional[float]
    log_path: str


@dataclass
class CurrentStep:
    """Currently running step, live-updating."""

    story_id: str
    step: str  # "spec", "dev", "review"
    attempt: int
    max_attempts: int  # 0 = infinite
    step_chain: str  # e.g. "spec✓ dev(×2)·---"
    start_time: float  # time.time()
    log_path: str


class RunnerState:
    """Thread-safe shared state. All mutations acquire a lock."""

    def __init__(
        self,
        config: dict,
        epic_id: str,
    ) -> None:
        self._lock = threading.Lock()

        # Set once at startup
        self.config: dict = config
        self.epic_id: str = epic_id
        self.session_start: float = time.time()

        # Usage tracking
        self.usage_5h: Optional[float] = None
        self.usage_7d: Optional[float] = None
        self.usage_sonnet: Optional[float] = None
        self.usage_extra_pct: Optional[float] = None
        self.usage_extra_spent: Optional[str] = None   # e.g. "6.34"
        self.usage_extra_account_cap: Optional[str] = None  # e.g. "85.00"
        self.usage_decision: str = "PROCEED"
        self.five_h_resets_at: Optional[str] = None   # ISO timestamp
        self.seven_d_resets_at: Optional[str] = None  # ISO timestamp
        self.usage_updated_at: Optional[float] = None

        # Progress
        self.completed_steps: list[StepRecord] = []
        self.current: Optional[CurrentStep] = None
        self.pending_stories: list[str] = []
        self.pending_next_steps: dict[str, str] = {}  # story_id → next step (spec/dev/review)
        self.pre_session_done_count: int = 0  # stories already done when this session started

        # Pause tracking — written by pipeline thread, consumed by _check_between_steps
        self.last_completed_story_id: Optional[str] = None  # set when review passes
        self.current_epic_id: Optional[str] = None          # updated per story
        self.epic_boundary_crossed: bool = False             # set when epic changes

        # Output log — stores (timestamp, text) tuples
        self.output_lines: deque[tuple[float, str]] = deque(maxlen=500)
        self.tool_call_counts: dict[str, int] = {}

        # UI toggles
        self.output_visible: bool = False
        self.timestamps_visible: bool = True
        self.pause_after_step: bool = False
        self.pause_on_limit: bool = False
        self.quit_on_limit: bool = False
        self.quit_after_step: bool = False
        self.help_visible: bool = False

        # App phase
        self.app_phase: str = "preflight"  # "preflight" | "running" | "halted" | "done"

        # Roadmap / history
        self.history_visible: bool = False
        self.history_scroll_offset: int = 0
        self.roadmap_rows: list = []  # (type, id, status, detail, blocked_reason)

        # Halt / exit
        self.halted: bool = False
        self.halt_reason: Optional[str] = None
        self.should_exit: bool = False   # pipeline stops
        self.display_exit: bool = False  # TUI closes (user acknowledged)
        self.exit_code: int = 0

        # Pause tracking
        self.paused_at: Optional[float] = None  # set when pause_after_step becomes True

        # Config reload
        self.config_reloaded_at: Optional[float] = None

        # Subprocess tracking
        self.subprocess_pid: Optional[int] = None

    # --- Toggle methods ---

    def reload_config(self, new_config: dict) -> None:
        with self._lock:
            self.config = new_config
            self.config_reloaded_at = time.time()

    def toggle_output(self) -> None:
        with self._lock:
            self.output_visible = not self.output_visible

    def set_paused(self) -> None:
        with self._lock:
            self.pause_after_step = True
            self.paused_at = time.time()

    def clear_paused(self) -> None:
        with self._lock:
            self.pause_after_step = False
            self.paused_at = None

    def toggle_pause(self) -> None:
        with self._lock:
            self.pause_after_step = not self.pause_after_step
            self.paused_at = time.time() if self.pause_after_step else None

    def toggle_pause_on_limit(self) -> None:
        with self._lock:
            self.pause_on_limit = not self.pause_on_limit

    def toggle_quit_on_limit(self) -> None:
        with self._lock:
            self.quit_on_limit = not self.quit_on_limit

    def toggle_help(self) -> None:
        with self._lock:
            self.help_visible = not self.help_visible

    def confirm_launch(self) -> None:
        with self._lock:
            self.app_phase = "running"

    def toggle_history(self) -> None:
        with self._lock:
            if self.history_visible:
                self.history_visible = False
                self.history_scroll_offset = 0
            else:
                self.history_visible = True

    def scroll_history(self, delta: int) -> None:
        with self._lock:
            max_offset = max(0, len(self.roadmap_rows) - 5)
            self.history_scroll_offset = max(0, min(self.history_scroll_offset + delta, max_offset))

    def set_roadmap(self, rows: list) -> None:
        with self._lock:
            self.roadmap_rows = list(rows)

    # --- Progress methods ---

    def append_completed(self, record: StepRecord) -> None:
        with self._lock:
            self.completed_steps = [*self.completed_steps, record]

    def set_current(self, current: CurrentStep) -> None:
        with self._lock:
            self.current = current

    def clear_current(self) -> None:
        with self._lock:
            self.current = None

    # --- Pending stories ---

    def set_pending_stories(self, stories: list[str], next_steps: dict[str, str] | None = None) -> None:
        with self._lock:
            self.pending_stories = list(stories)
            if next_steps is not None:
                self.pending_next_steps = dict(next_steps)

    def remove_pending(self, story_id: str) -> None:
        with self._lock:
            self.pending_stories = [
                s for s in self.pending_stories if s != story_id
            ]

    def toggle_timestamps(self) -> None:
        with self._lock:
            self.timestamps_visible = not self.timestamps_visible

    # --- Output log ---

    def append_output(self, line: str) -> None:
        with self._lock:
            self.output_lines.append((time.time(), line))

    def increment_tool_count(self, name: str) -> None:
        with self._lock:
            self.tool_call_counts[name] = self.tool_call_counts.get(name, 0) + 1

    def clear_output(self) -> None:
        with self._lock:
            self.output_lines.clear()
            self.tool_call_counts.clear()

    # --- Usage ---

    def update_usage(
        self,
        usage_5h: Optional[float],
        usage_7d: Optional[float],
        updated_at: Optional[float],
    ) -> None:
        with self._lock:
            self.usage_5h = usage_5h
            self.usage_7d = usage_7d
            self.usage_updated_at = updated_at

    def update_full_usage(
        self,
        usage_5h: Optional[float],
        usage_7d: Optional[float],
        usage_sonnet: Optional[float],
        usage_extra_pct: Optional[float],
        usage_extra_spent: Optional[str],
        usage_extra_account_cap: Optional[str],
        usage_decision: str,
        five_h_resets_at: Optional[str],
        seven_d_resets_at: Optional[str],
        updated_at: Optional[float],
    ) -> None:
        with self._lock:
            self.usage_5h = usage_5h
            self.usage_7d = usage_7d
            self.usage_sonnet = usage_sonnet
            self.usage_extra_pct = usage_extra_pct
            self.usage_extra_spent = usage_extra_spent
            self.usage_extra_account_cap = usage_extra_account_cap
            self.usage_decision = usage_decision or "PROCEED"
            self.five_h_resets_at = five_h_resets_at
            self.seven_d_resets_at = seven_d_resets_at
            self.usage_updated_at = updated_at

    # --- Exit / halt ---

    def request_exit(self, code: int = 0) -> None:
        with self._lock:
            self.should_exit = True
            self.exit_code = code

    def close_display(self) -> None:
        with self._lock:
            self.display_exit = True
            self.should_exit = True

    def set_halt(self, reason: str) -> None:
        with self._lock:
            self.halted = True
            self.halt_reason = reason
            self.should_exit = True


def create_initial_state(config: dict, epic_id: str) -> RunnerState:
    """Factory function to create a fresh RunnerState."""
    return RunnerState(config=config, epic_id=epic_id)
