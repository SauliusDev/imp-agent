"""Rich layout builder for the IMP runner TUI.

Uses rich.layout.Layout with fixed-size slots.
Matches the pattern from scheduler_dashboard.py (screen=True).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional

from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.style import Style
from rich.text import Text
from rich.table import Table

from imp_state import RunnerState

STALE_THRESHOLD_S = 2 * 60 * 60


def _log_link(t: Text, path: str) -> None:
    """Append a clickable filename link to a Rich Text object.

    Uses Rich's native Style(link=) so OSC 8 escape sequences are handled
    correctly within Rich's rendering pipeline.
    """
    name = os.path.basename(path)
    t.append(name, style=Style(link=f"file://{path}", color="bright_black", underline=True))


def _fmt_elapsed(seconds: float) -> str:
    total_s = int(seconds)
    return f"{total_s // 60}m{total_s % 60:02d}s"


def _fmt_usage(val: Optional[float], stale: bool = False) -> str:
    if val is None:
        return "?%"
    pct = f"{int(val)}%"
    return f"{pct}(stale)" if stale else pct


def _short_model(model: str) -> str:
    return model.replace("claude-", "")


def _agent_provider(config: dict) -> str:
    return str(config.get("agent_provider", "claude")).strip().lower()


def _fmt_resets(iso_ts: Optional[str]) -> str:
    """Format an ISO timestamp as a countdown string like '3h48m' or '5d20h'."""
    if not iso_ts:
        return "?"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        secs = max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))
        h, rem = divmod(secs, 3600)
        m = rem // 60
        if h >= 24:
            d, h = divmod(h, 24)
            return f"{d}d{h:02d}h"
        return f"{h}h{m:02d}m"
    except (ValueError, AttributeError, TypeError):
        return "?"


# ---------------------------------------------------------------------------
# Header — config + session info (size=7)
# ---------------------------------------------------------------------------

def _build_header(state: RunnerState) -> Panel:
    cfg = state.config
    stale = state.usage_updated_at is not None and (time.time() - state.usage_updated_at) > STALE_THRESHOLD_S
    elapsed = _fmt_elapsed(time.time() - state.session_start)

    model_spec = _short_model(cfg.get("model_spec", "?"))
    model_dev = _short_model(cfg.get("model_dev", "?"))
    model_review = _short_model(cfg.get("model_review", "?"))
    effort_spec = cfg.get("effort_spec", "?")
    effort_dev = cfg.get("effort_dev", "?")
    effort_review = cfg.get("effort_review", "?")
    max_rev = cfg.get("max_review_attempts", "?")
    artifacts = cfg.get("artifacts_dir", "?")
    provider = _agent_provider(cfg)

    if provider == "codex":
        usage_5h = usage_7d = usage_snt = "off"
    else:
        usage_5h = _fmt_usage(state.usage_5h, stale=stale)
        usage_7d = _fmt_usage(state.usage_7d, stale=stale)
        usage_snt = _fmt_usage(state.usage_sonnet, stale=stale)

    # Extra display: "€6.34/€85" or "?" if unknown
    if state.usage_extra_spent is not None:
        acct_cap = f"/€{state.usage_extra_account_cap}" if state.usage_extra_account_cap else ""
        extra_display = f"€{state.usage_extra_spent}{acct_cap}"
    else:
        extra_display = "?"

    # Reset countdowns
    five_h_reset = _fmt_resets(state.five_h_resets_at)
    seven_d_reset = _fmt_resets(state.seven_d_resets_at)

    # Active limit config
    base_limit = int(cfg.get("base_limit_pct", 0) or cfg.get("usage_limit_threshold", 0))
    limit_7d = int(cfg.get("limit_7d_pct", 0))
    extra_limit_eur = float(cfg.get("extra_limit_eur", 0) or 0)
    decision = state.usage_decision

    # Left column width: colons align at col 8, right col starts at col 34
    C = 34

    t = Text()
    # Config rows — colons align, right column starts at fixed position
    t.append(f"  provider: {provider}".ljust(C), style="white")
    t.append(f"max: {max_rev}\n", style="white")
    t.append(f"  spec: {model_spec} / {effort_spec}".ljust(C), style="white")
    t.append(f"dev: {model_dev} / {effort_dev}\n", style="white")
    t.append(f"review: {model_review} / {effort_review}".ljust(C), style="white")
    t.append("\n", style="white")
    t.append(f"  artifacts: {artifacts}\n", style="bright_black")
    t.append("\n")

    # Single usage line: session + all percentages + extra + resets + badges
    t.append("Session: ", style="bold bright_white")
    t.append(elapsed, style="bold bright_white")
    t.append("   ", style="white")
    t.append(f"5h {usage_5h} │ 7d {usage_7d} │ snt {usage_snt}", style="bright_magenta")
    t.append("   extra: ", style="bright_magenta")
    t.append(extra_display, style="bright_magenta")
    if state.config_reloaded_at and (time.time() - state.config_reloaded_at) < 2.0:
        t.append("  [cfg reloaded]", style="bold bright_cyan")
    if decision == "WARN":
        t.append("  [WARN]", style="bold bright_yellow")
    elif decision == "STOP":
        t.append("  [STOP]", style="bold bright_red")
    if state.pause_on_limit:
        t.append(f"  [PL @{base_limit}%]", style="bold bright_yellow")
    if state.quit_on_limit:
        t.append(f"  [QL @{base_limit}%]", style="bold bright_yellow")
    if limit_7d > 0:
        t.append(f"  [7d @{limit_7d}%]", style="bright_yellow")
    if extra_limit_eur > 0:
        t.append(f"  [cap €{extra_limit_eur:.2f}]", style="bright_yellow")
    t.append("\n")
    t.append(f"resets: 5h→{five_h_reset} │ 7d→{seven_d_reset}", style="bright_black")

    return Panel(t, title="[bold bright_blue]IMP v1.0", border_style="bright_blue", box=box.ROUNDED)


# ---------------------------------------------------------------------------
# Stories — progress list (size=8)
# ---------------------------------------------------------------------------

def _build_stories(state: RunnerState) -> Panel:
    session_done = len(state.completed_steps)
    total_done = state.pre_session_done_count + session_done
    pending = [s for s in state.pending_stories if not state.current or state.current.story_id != s]
    total = total_done + (1 if state.current else 0) + len(pending)

    t = Text()

    # Header — e.g. "all   18 / 50 done  (6 this session)"
    t.append(f"  {state.epic_id}   ", style="bold bright_white")
    t.append(f"{total_done} / {total}", style="bold bright_white")
    t.append(" done", style="bold bright_white")
    if session_done > 0:
        t.append(f"  ({session_done} this session)", style="bright_green")
    t.append("\n\n")

    # Current story
    if state.halted:
        t.append(f"  !  HALTED \u2014 {state.halt_reason or 'unknown'}\n", style="bold bright_red")
    elif state.pause_after_step and state.current is None:
        # Paused between steps — no active subprocess
        paused_for = f"  ({_fmt_elapsed(time.time() - state.paused_at)})" if state.paused_at else ""
        t.append(f"  \u23f8  PAUSED{paused_for} \u2014 press p to resume\n", style="bold bright_yellow")
    elif state.current:
        cur = state.current
        max_s = str(cur.max_attempts) if cur.max_attempts > 0 else "\u221e"
        if state.pause_after_step:
            paused_for = f"  ({_fmt_elapsed(time.time() - state.paused_at)})" if state.paused_at else ""
            t.append(f"  \u23f8  PAUSED{paused_for} \u2014 press p to resume\n", style="bold bright_yellow")
        else:
            t.append("  >  ", style="bright_yellow")
            t.append(cur.story_id, style="bold bright_yellow")
            t.append("\n")
            t.append(f"     step: {cur.step}   attempt: {cur.attempt}/{max_s}", style="bright_black")
            t.append(f"   elapsed: {_fmt_elapsed(time.time() - cur.start_time)}\n", style="bright_black")
            t.append(f"     chain: {cur.step_chain}\n", style="bright_black")
            t.append("     log:   ", style="bright_black")
            _log_link(t, cur.log_path)
            t.append("\n")
    else:
        t.append("  (idle)\n", style="bright_black")

    # Next pending story
    if pending:
        next_step = state.pending_next_steps.get(pending[0], "spec")
        t.append("\n  o  ", style="bright_black")
        t.append(pending[0], style="bright_black")
        t.append(f"   {next_step}  pending", style="bright_black")
        if len(pending) > 1:
            t.append(f"   +{len(pending) - 1} more", style="bright_black")
        t.append("\n")

    border = "bright_yellow" if state.pause_after_step else "bright_green"
    title_color = "bright_yellow" if state.pause_after_step else "bright_green"
    return Panel(t, title=f"[bold {title_color}]Progress", border_style=border, box=box.ROUNDED)


# ---------------------------------------------------------------------------
# Main area — agent output or help (fills remaining space)
# ---------------------------------------------------------------------------

_ROADMAP_STATUS: dict[str, tuple[str, str]] = {
    "done-session": ("bright_green",  "+"),   # completed in this session
    "done":         ("green",         "+"),   # completed in a prior session
    "in-progress": ("bright_yellow",  ">"),
    "blocked":     ("bright_red",     "!"),
    "interrupted": ("bright_magenta", "~"),
    "pending":     ("bright_black",   "o"),
}


def _parse_pause_after_display(config: dict) -> set[str]:
    raw = config.get("pause_after", [])
    if isinstance(raw, list):
        return {str(s).strip() for s in raw if s}
    if isinstance(raw, str) and raw.strip():
        return {s.strip() for s in raw.split(",") if s.strip()}
    return set()


def _build_roadmap_panel(state: RunnerState, title: str) -> Panel:
    rows = state.roadmap_rows
    offset = state.history_scroll_offset
    max_render = 60  # More than any terminal height; Rich clips the rest

    visible = rows[offset:offset + max_render]

    pause_after = _parse_pause_after_display(state.config)
    pause_between_epics = str(state.config.get("pause_between_epics", "false")).lower() in ("true", "1", "yes")
    epics_seen = 0

    t = Text()
    for row_type, row_id, status, detail, blocked_reason in visible:
        style, icon = _ROADMAP_STATUS.get(status, ("white", "?"))
        if row_type == "epic":
            t.append(f"  [{icon}] ", style=f"bold {style}")
            t.append(f"{row_id}", style=f"bold {style}")
            t.append(f"  {detail}", style="white")
            if pause_between_epics and epics_seen > 0 and status != "done":
                t.append("  \u23f8", style="bold bright_cyan")
            t.append("\n")
            epics_seen += 1
        else:
            t.append(f"      {icon}  ", style=style)
            t.append(f"{row_id}", style=style)
            t.append(f"    {detail}", style="bright_black")
            if blocked_reason:
                t.append(f"  \u2192 {blocked_reason}", style="bright_red")
            if row_id in pause_after and status != "done":
                t.append("  \u23f8", style="bold bright_cyan")
            t.append("\n")

    total = len(rows)
    if total > 0 and offset > 0:
        shown_end = min(offset + max_render, total)
        t.append(f"\n  \u2191\u2193 scroll  ({offset + 1}\u2013{shown_end} of {total})", style="bright_black")
    elif total > max_render:
        t.append(f"\n  \u2193 more below  (1\u2013{max_render} of {total})", style="bright_black")

    return Panel(t, title=f"[bold bright_cyan]{title}", border_style="bright_cyan", box=box.ROUNDED)


def _build_main(state: RunnerState) -> Panel:
    if state.history_visible:
        return _build_roadmap_panel(state, "Roadmap")

    if state.help_visible:
        cfg = state.config
        base_limit = int(cfg.get("base_limit_pct", 0) or cfg.get("usage_limit_threshold", 0))
        limit_7d = int(cfg.get("limit_7d_pct", 0))
        extra_limit_eur = float(cfg.get("extra_limit_eur", 0) or 0)
        on_base = cfg.get("on_base_limit", "pause")
        on_extra = cfg.get("on_extra_limit", "quit")

        limit_cond = f"@{base_limit}%" if base_limit > 0 else "off"
        limit_7d_cond = f"@{limit_7d}%" if limit_7d > 0 else "off"
        extra_cond = f"€{extra_limit_eur:.2f}" if extra_limit_eur > 0 else "off"

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold bright_cyan", width=4)
        table.add_column(style="white")
        table.add_row("l", "Toggle agent output")
        table.add_row("p", "Pause/resume after step")
        table.add_row("PL", f"Pause on limit  [overrides on_base_limit]  5h {limit_cond}")
        table.add_row("q", "Quit now")
        table.add_row("Q", "Quit after step")
        table.add_row("QL", f"Quit on limit   [overrides on_base_limit]  5h {limit_cond}")
        table.add_row("r", "Reload config.yaml now")
        table.add_row("t", "Toggle timestamps in agent output")
        table.add_row("?", "Toggle this help")

        t = Text()
        t.append("\nUsage limits\n", style="bold bright_white")
        t.append("  5h cap:   ", style="bright_black")
        t.append(limit_cond, style="white")
        t.append("   action: ", style="bright_black")
        t.append(on_base, style="white")
        t.append("\n  7d cap:   ", style="bright_black")
        t.append(limit_7d_cond, style="white")
        t.append("\n  extra:    ", style="bright_black")
        t.append(extra_cond, style="white")
        t.append("   action: ", style="bright_black")
        t.append(on_extra if extra_limit_eur > 0 else "—", style="white")

        return Panel(Group(table, t), title="[bold bright_cyan]Help", border_style="bright_cyan", box=box.ROUNDED)

    if state.output_visible:
        entries = list(state.output_lines)  # [(ts, text), ...]
        tool_counts = dict(state.tool_call_counts)

        # Stats for panel title — top tools by count
        stats_parts = [
            f"{name}×{count}"
            for name, count in sorted(tool_counts.items(), key=lambda x: -x[1])
            if count > 0
        ]
        stats_str = "  ".join(stats_parts)
        title = "[bold bright_yellow]Agent output"
        if stats_str:
            title += f"  [bright_black]{stats_str}"

        # Auto-scroll: show only the lines that fit the panel
        try:
            term_h = os.get_terminal_size().lines
        except OSError:
            term_h = 40
        available = max(5, term_h - 7 - 10 - 3 - 6)  # header+stories+footer+borders
        visible = entries[-available:]

        if not visible:
            return Panel(
                Text("(waiting...)", style="bright_black"),
                title=title, border_style="bright_yellow", box=box.ROUNDED,
            )

        show_ts = state.timestamps_visible
        t = Text()
        for i, (ts, text) in enumerate(visible):
            if show_ts:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                t.append(dt.strftime("%H:%M:%S  "), style="bright_black")
            t.append(text)
            if i < len(visible) - 1:
                t.append("\n")
        return Panel(t, title=title, border_style="bright_yellow", box=box.ROUNDED)

    return Panel(
        Text("press [l] to show agent output  |  press [?] for help", style="bright_black"),
        title="[bold]Output",
        border_style="bright_black",
        box=box.ROUNDED,
    )


# ---------------------------------------------------------------------------
# Footer — key legend (size=3)
# ---------------------------------------------------------------------------

def _build_preflight_footer() -> Text:
    t = Text(" ")
    t.append("[Enter]", style="bold bright_green")
    t.append("  ")
    t.append("[↑↓]", style="white")
    t.append("  ")
    t.append("[q]", style="white")
    return t


def _build_footer(state: RunnerState) -> Text:
    if state.should_exit and not state.display_exit:
        t = Text(" ")
        t.append("pipeline stopped", style="bold bright_white")
        t.append("  —  press any key to exit", style="bright_black")
        return t

    cfg = state.config
    base_limit = int(cfg.get("base_limit_pct", 0) or cfg.get("usage_limit_threshold", 0))

    def _key(k: str, active: bool) -> tuple[str, str]:
        return (f"[{k}]", "bold bright_yellow" if active else "white")

    t = Text(" ")
    for key, active in [
        ("l", state.output_visible),
        ("p", state.pause_after_step),
        ("PL", state.pause_on_limit),
        ("q", False),
        ("Q", state.quit_after_step),
        ("QL", state.quit_on_limit),
        ("h", state.history_visible),
        ("r", False),
        ("t", state.timestamps_visible),
        ("?", state.help_visible),
    ]:
        k, s = _key(key, active)
        t.append(k, style=s)
        t.append("  ")
    return t


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

def build_layout(state: RunnerState) -> Layout:
    layout = Layout()

    if state.app_phase == "preflight":
        layout.split_column(
            Layout(name="header", size=8),
            Layout(name="roadmap"),
            Layout(name="footer", size=3),
        )
        layout["header"].update(_build_header(state))
        layout["roadmap"].update(_build_roadmap_panel(state, "Roadmap — press Enter to start"))
        layout["footer"].update(_build_preflight_footer())
        return layout

    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="stories", size=10),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )
    layout["header"].update(_build_header(state))
    layout["stories"].update(_build_stories(state))
    layout["main"].update(_build_main(state))
    layout["footer"].update(_build_footer(state))
    return layout
