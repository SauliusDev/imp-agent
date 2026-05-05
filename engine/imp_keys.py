"""Raw terminal keypress reader for IMP Runner TUI.

Runs in a daemon thread, reads one byte at a time from stdin in raw mode,
and dispatches commands by mutating RunnerState flags.

Uses os.read(fd, 1) throughout — bypasses Python's internal stdio buffer so
that select() reliably detects multi-byte escape sequences (arrow keys).
"""

from __future__ import annotations

import os
import select
import sys
import termios
import tty
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from imp_state import RunnerState

SEQUENCE_TIMEOUT_S = 0.3   # 300ms for two-char command sequences (PL, QL)
ARROW_TIMEOUT_S = 0.1      # 100ms for arrow escape continuation bytes


def _readbyte(fd: int) -> str:
    """Read exactly one byte from fd, return as str."""
    return os.read(fd, 1).decode("utf-8", errors="replace")


def _read_next(fd: int, timeout: float) -> str | None:
    """Wait up to `timeout` seconds for the next byte on fd.

    Returns the character if one arrives, or None on timeout.
    Uses the raw fd — not affected by Python's stdio buffer.
    """
    ready, _, _ = select.select([fd], [], [], timeout)
    if ready:
        return _readbyte(fd)
    return None


def start_keyreader(
    state: "RunnerState",
    on_quit_now: Callable[[], None],
    on_reload_config: Callable[[], None] | None = None,
) -> None:
    """Blocking keypress reader — call from a daemon thread.

    Sets the terminal to raw mode, reads keypresses, dispatches commands
    via state mutation methods, and restores terminal settings on exit.

    Returns immediately if stdin is not a terminal.
    """
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        return

    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)

        while not state.display_exit:
            # Block until a byte is available (or check periodically)
            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready:
                continue

            ch = _readbyte(fd)

            # Pipeline already stopped — any key dismisses the TUI
            if state.should_exit:
                state.close_display()
                break

            # Preflight: only Enter/Space (confirm), arrows (scroll), q/Ctrl-C (quit)
            if state.app_phase == "preflight":
                if ch in ("\r", "\n", " "):
                    state.confirm_launch()
                elif ch == "q":
                    on_quit_now()
                    break
                elif ch == "\x03":  # Ctrl+C
                    on_quit_now()
                    break
                elif ch == "\x1b":  # arrow keys
                    second = _read_next(fd, ARROW_TIMEOUT_S)
                    if second == "[":
                        third = _read_next(fd, ARROW_TIMEOUT_S)
                        if third == "A":    # Up
                            state.scroll_history(-1)
                        elif third == "B":  # Down
                            state.scroll_history(1)
                continue

            # Running phase keys
            if ch == "l":
                state.toggle_output()

            elif ch == "h":
                state.toggle_history()

            elif ch == "\x1b":  # arrow keys — scroll roadmap when visible
                second = _read_next(fd, ARROW_TIMEOUT_S)
                if second == "[":
                    third = _read_next(fd, ARROW_TIMEOUT_S)
                    if third == "A":    # Up
                        state.scroll_history(-1)
                    elif third == "B":  # Down
                        state.scroll_history(1)

            elif ch == "p":
                state.toggle_pause()

            elif ch == "P":
                second = _read_next(fd, SEQUENCE_TIMEOUT_S)
                if second == "L":
                    state.toggle_pause_on_limit()
                # P alone (timeout or different char) → ignored

            elif ch == "Q":
                second = _read_next(fd, SEQUENCE_TIMEOUT_S)
                if second == "L":
                    state.toggle_quit_on_limit()
                else:
                    # Q alone → quit after step
                    state.quit_after_step = True

            elif ch == "q":
                on_quit_now()
                break

            elif ch == "r":
                if on_reload_config is not None:
                    on_reload_config()

            elif ch == "t":
                state.toggle_timestamps()

            elif ch == "?":
                state.toggle_help()

            elif ch == "\x03":  # Ctrl+C
                on_quit_now()
                break

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
