# IMP Agent

Autonomous BMAD pipeline orchestrator. Drives `/bmad-create-story`, `/bmad-dev-story`,
and `/bmad-code-review` in a loop over sprint stories — with a Rich TUI, persistent ledger,
usage gates, and optional mind-sync.

![IMP Agent terminal demo](demo.png)

## Install

Run from your project root (BMAD must already be set up):

```bash
curl -fsSL https://raw.githubusercontent.com/SauliusDev/imp-agent/main/setup.sh | bash
```

## Prerequisites

- **BMAD** set up in the project (`.claude/skills/bmad-dev-story/` must exist)
- **Python 3.10+**
- **Claude Code CLI** (`claude` command on PATH)
- **`rich`** Python package (installer offers to install it)

## What gets installed

| Path | Description |
|---|---|
| `_imp/` | IMP engine (7 Python files + launcher) |
| `.claude/skills/imp-init/` | Skill to initialize the ledger |
| `.claude/skills/mind-sync/` | Skill to sync project memory (optional) |
| `_imp/config.yaml` | Pipeline config — edit before first run |
| `_mind/` | Project memory directory (only if mind-sync enabled) |

## After installing

1. **Edit `_imp/config.yaml`** — set models, usage caps, pause points
2. **Run `/bmad-sprint-planning`** — generates `sprint-status.yaml` if not done yet
3. **Run `/imp-init`** — initializes the ledger from `sprint-status.yaml`
4. **Run `bash _imp/imp.sh all`** — starts the pipeline

## Re-installing / updating

Re-run the same curl command. Engine files are always overwritten; your `_imp/config.yaml` is preserved.

## Mind-sync (optional)

IMP can sync project memory after each story using [mind](https://github.com/SauliusDev/mind).
The installer asks about this interactively. To toggle later, edit `_imp/config.yaml`:

```yaml
mind_sync_after_story: true   # or false
```

## Usage

```bash
bash _imp/imp.sh all          # run all epics
bash _imp/imp.sh epic-1       # run a single epic
bash _imp/imp.sh --help
```

Keyboard shortcuts while running: `p` pause · `l` toggle output · `r` reload config · `q` quit
