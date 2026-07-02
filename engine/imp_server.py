from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path

from imp_state import RunnerState


def web_dist_path(base_file: str | Path = __file__) -> Path:
    script_dir = Path(base_file).resolve().parent
    installed_dist = script_dir / "web" / "dist"
    if script_dir.name == "_imp":
        return installed_dist
    if installed_dist.exists():
        return installed_dist
    return script_dir.parent / "web" / "dist"


def build_state_snapshot(state: RunnerState) -> dict:
    """Build a JSON-serializable snapshot of the runner state."""
    with state._lock:
        current = state.current
        now = time.time()
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
                "extra_pct": state.usage_extra_pct,
                "extra_spent_eur": state.usage_extra_spent,
                "extra_account_cap_eur": state.usage_extra_account_cap,
                "decision": state.usage_decision,
                "five_hour_resets_at": state.five_h_resets_at,
                "seven_day_resets_at": state.seven_d_resets_at,
                "updated_at": state.usage_updated_at,
            },
            "current": None if current is None else {
                "story_id": current.story_id,
                "step": current.step,
                "attempt": current.attempt,
                "max_attempts": current.max_attempts,
                "step_chain": current.step_chain,
                "start_time": current.start_time,
                "elapsed_s": max(0, now - current.start_time),
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
    shutdown_server: Callable[[], None] | None = None,
):
    try:
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse
    except ImportError as exc:
        raise RuntimeError("FastAPI is required for IMP web API. Install fastapi and uvicorn.") from exc

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
        if shutdown_server is not None:
            shutdown_server()
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

    try:
        from fastapi.staticfiles import StaticFiles

        dist = web_dist_path()
        if dist.exists():
            app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")
    except ImportError:
        pass

    return app
