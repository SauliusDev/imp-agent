# IMP Web UI And Tmux Runner Design

Date: 2026-07-02

## Goal

Replace the terminal-first IMP operator experience with a local web UI while preserving the current cheap, deterministic control model.

Version 1 keeps the existing BMAD sprint-to-ledger flow:

1. `imp-init` creates `_imp/ledger.json` from BMAD sprint status.
2. A Python runner reads the ledger and decides the next step.
3. Exactly one Claude or Codex child step runs at a time.
4. The runner updates ledger, logs, usage state, and pause/quit state.
5. The web UI visualizes and controls that loop.

The v1 scope does not include a Mermaid workflow compiler. The design leaves room for later `.mmd -> ledger` generation by making step execution data-driven rather than hardcoding BMAD behavior into the UI.

## Current Model

The current runner is a single Python process in `engine/imp_runner.py`.

It owns:

- ledger reads and writes through `engine/imp-ledger.py`
- current session state through `engine/imp_state.py`
- Rich terminal rendering through `engine/imp_display.py`
- keyboard controls through `engine/imp_keys.py`
- Claude and Codex child execution through direct subprocesses
- logs under `_imp/logs`

This is already cleaner than the BMAD Automator parent-agent model because no parent LLM spends tokens deciding the loop. The control plane is normal Python code.

The main limitation is lifecycle coupling: if the runner UI/process dies, the active child process is harder to rediscover and inspect. Terminal controls also limit future richer UI features.

## Target Model

The target model keeps deterministic Python orchestration and adds tmux as the child execution container.

```text
imp-init -> ledger.json -> Python state machine -> tmux child step -> verifier -> ledger update
                                      |
                                      v
                             local API/WebSocket
                                      |
                                      v
                                  web UI
```

The "orchestrator" is not an AI agent. It is deterministic Python code that:

- loads config and ledger
- selects the next story and step
- resolves the step definition
- starts one tmux child session
- monitors child state and output
- verifies completion against ledger/sprint/story truth
- updates ledger and UI state
- pauses, quits, or advances

## Why Tmux

Tmux gives the active child step an external lifecycle.

Benefits:

- browser or API server can restart without immediately losing the child step
- operator can inspect or attach to the raw child pane
- the runner can classify active, completed, crashed, or stuck states from pane/process state
- xterm.js can show a real terminal fallback later
- future parallel or branched sessions can use the same execution boundary

For v1, tmux does not mean parallel agents. It means one durable child session per active step.

## Step Definitions

V1 ships with the current fixed BMAD steps:

```json
{
  "spec": "bmad-create-story",
  "dev": "bmad-dev-story",
  "review": "bmad-code-review"
}
```

The runner should treat these as step definitions, not permanent hardcoded branches.

Each step definition should describe:

- step id: `spec`, `dev`, `review`
- provider: inherited from config, `claude` or `codex`
- skill or prompt command to run
- model and effort keys
- retry policy
- verifier policy
- whether human pause is allowed or required after completion

This keeps the future custom-node path simple. A later `.mmd -> ledger` generator can emit node tags like `research`, `human`, `qa`, or `design-review`, and the runner can execute those tags through the same step-definition interface.

## Ledger Compatibility

The existing ledger remains the source of workflow state for v1.

The runner may add execution metadata, but it must preserve existing fields so current commands and tests keep working.

Allowed additions:

- active tmux session id per step
- readable log path
- raw terminal capture path
- started/finished timestamps
- provider used
- exit code
- failure reason

The ledger remains project-local and file-backed. It should be inspectable and recoverable without a database.

## Tmux Runtime

Add a small runtime module responsible only for tmux lifecycle.

Responsibilities:

- create a safe session name from run id, story id, and step id
- write long commands to temp script files instead of passing huge shell strings
- start detached tmux sessions
- capture pane output to log files
- read session state
- detect completed/crashed/stuck states
- kill active session on quit
- clean stale temp files when safe

The implementation should borrow the useful parts of `bmad-automator`:

- detached child sessions
- state files for monitor reconciliation
- command scripts for long commands
- tests around session status and cleanup

It should not copy the BMAD Automator parent-agent architecture.

## Local Server

Add a local server that exposes runner state and control actions.

Recommended backend: Python FastAPI or Starlette because the existing runner is Python.

Core endpoints:

- `GET /api/state` returns current runner state snapshot
- `GET /api/ledger` returns parsed ledger summary
- `GET /api/logs/session` returns current session log
- `GET /api/logs/step/{storyId}/{step}` returns readable step log
- `POST /api/run` starts a run for `all` or one epic
- `POST /api/pause` pauses after the current safe point
- `POST /api/resume` resumes from pause
- `POST /api/quit` quits after killing or preserving the active tmux session based on request body
- `POST /api/reload-config` reloads `_imp/config.yaml`
- `GET /api/events` streams live state/log updates through Server-Sent Events or WebSocket

The server should bind to localhost by default.

## Web UI

The UI should remake the current TUI first, then improve it.

V1 screens:

- dashboard header with provider, models, usage, elapsed time, and active limits
- roadmap panel with epics, stories, status, and blocked reasons
- current step panel with story id, step, attempt, elapsed time, tmux session id, and log link
- agent output panel with readable streaming log
- controls for run, pause/resume, quit, quit-after-step, reload config, show terminal
- fallback terminal tab backed by xterm.js and the tmux pane

Use the supplied IMP icon at `_board/icon/imp-agent.png` as the app icon/brand mark.

Recommended frontend stack:

- React
- Tailwind
- shadcn or Origin UI components
- xterm.js for terminal fallback
- Mermaid rendering later for workflow visualization

The visual style should be an operator dashboard, not a marketing landing page: dense, readable, glass/macOS-inspired where useful, but not decorative at the cost of clarity.

## Data Flow

1. User opens local web UI.
2. UI requests `/api/state` and subscribes to live events.
3. User starts `all` or an epic.
4. Python runner loads config and ledger.
5. Runner resolves the next story and step.
6. Runner creates a tmux child session for that step.
7. Tmux runtime captures output and updates child state.
8. Runner verifies completion and updates ledger.
9. Server pushes state/log updates to UI.
10. Runner advances, pauses, blocks, or exits.

## Failure Modes

Active child crashes:

- mark step failed
- preserve logs and tmux/output metadata
- retry if policy allows
- block story if retry budget is exhausted

API server crashes:

- tmux child may continue
- on restart, server/runner reloads ledger and tmux metadata
- UI shows recovered state

Browser disconnects:

- no effect on runner
- reconnect resumes state and logs

Usage limit hit:

- same behavior as current config
- pause or quit at safe point

Manual quit:

- default behavior should stop the child tmux session and mark story interrupted
- advanced option can preserve tmux session for inspection

Unknown tmux state:

- show as `unknown`
- do not mark story done
- require operator action or explicit retry

## Testing

Keep tests focused on risky boundaries:

- ledger compatibility tests for existing `imp-init` output
- step-definition resolution tests
- tmux runtime tests for spawn, complete, crash, kill, and stale state
- API tests for state/control endpoints
- UI smoke test for dashboard rendering and controls
- Playwright visual check for the local UI at desktop and mobile widths

Manual verification should include:

- Claude run starts in tmux
- Codex run starts in tmux
- pause/resume works
- quit kills or preserves tmux as selected
- server/browser restart does not lose visible state

## Out Of Scope For V1

- Mermaid workflow editor
- `.mmd -> ledger` compiler
- arbitrary custom agent/node authoring UI
- parallel execution
- remote/mobile access
- GitHub/Linear integrations
- desktop packaging with Tauri

These should be added after the tmux-backed web dashboard is stable.

