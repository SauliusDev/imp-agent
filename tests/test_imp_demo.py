import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_demo import create_demo_callbacks, create_demo_state
from imp_server import build_state_snapshot


def test_create_demo_state_populates_dashboard_snapshot():
    state = create_demo_state("all")

    snapshot = build_state_snapshot(state)

    assert snapshot["epic_id"] == "all"
    assert snapshot["provider"] == "codex"
    assert snapshot["app_phase"] == "preflight"
    assert snapshot["pending_stories"] == [
        "1-2-tmux-runner",
        "1-3-web-dashboard",
        "2-1-human-breakpoints",
    ]
    assert snapshot["roadmap_rows"][0] == [
        "epic",
        "epic-1",
        "in-progress",
        "Local runner foundation",
        None,
    ]
    assert "Demo mode loaded" in snapshot["output_lines"][0]
    assert snapshot["usage"]["decision"] == "PROCEED"


def test_create_demo_state_filters_single_epic():
    state = create_demo_state("epic-2")

    snapshot = build_state_snapshot(state)

    assert snapshot["epic_id"] == "epic-2"
    assert snapshot["pending_stories"] == ["2-1-human-breakpoints"]
    assert [row[1] for row in snapshot["roadmap_rows"]] == [
        "epic-2",
        "2-1-human-breakpoints",
        "2-2-agent-tags",
    ]


def test_demo_run_controls_mutate_state_without_launching_agents():
    state = create_demo_state("all")
    callbacks = create_demo_callbacks(state)

    callbacks.start_run()
    running = build_state_snapshot(state)

    assert running["app_phase"] == "running"
    assert running["current"]["story_id"] == "1-2-tmux-runner"
    assert running["current"]["tmux_session"] == "demo-imp-agent"
    assert "Demo run started" in running["output_lines"][-1]

    callbacks.pause()
    paused = build_state_snapshot(state)
    assert paused["app_phase"] == "paused"
    assert paused["halted"] is False

    callbacks.resume()
    resumed = build_state_snapshot(state)
    assert resumed["app_phase"] == "running"

    callbacks.reload_config()
    reloaded = build_state_snapshot(state)
    assert "Demo config reload requested" in reloaded["output_lines"][-1]

    callbacks.quit_now()
    stopped = build_state_snapshot(state)
    assert stopped["should_exit"] is True
    assert stopped["app_phase"] == "done"
