# IMP Agent Installer — Design Spec
_2026-05-05_

## Overview

IMP is a multi-threaded autonomous orchestrator that drives BMAD's three core implementation skills (`/bmad-create-story`, `/bmad-dev-story`, `/bmad-code-review`) in a loop over sprint stories. This spec covers making IMP installable into any BMAD project via a one-liner curl installer.

## Install Command

```bash
curl -fsSL https://raw.githubusercontent.com/SauliusDev/imp-agent/main/setup.sh | bash
```

Run from the project root. No path arguments — installs into current directory.

## Repo Structure

```
imp-agent/
├── setup.sh              # Bash bootstrapper (~35 lines)
├── install.py            # Python installer using rich (~200 lines)
├── engine/               # Copied verbatim to _imp/ in target project
│   ├── imp.sh
│   ├── imp_runner.py
│   ├── imp_state.py
│   ├── imp_display.py
│   ├── imp_keys.py
│   ├── imp_usage.py
│   └── imp-ledger.py
├── skills/               # Copied to .claude/skills/ in target project
│   ├── imp-init/
│   │   └── SKILL.md
│   └── mind-sync/
│       ├── SKILL.md
│       └── workflow.md
└── templates/
    ├── config.yaml       # Template with {{project_name}} placeholder
    └── mind/
        ├── mind.md       # Blank 8-section project memory template
        └── index.yaml    # Initial index (empty tracked_files list)
```

## Install Flow

### Phase 1: `setup.sh` (bash bootstrapper)

Performs preflight only — no file installation. Hands off to Python as fast as possible.

1. Check Python 3.10+ (`python3 --version`) — hard stop if missing
2. Check `rich` is installed — offer `pip install rich` interactively if not
3. Check BMAD present (`.claude/skills/bmad-dev-story/` exists) — hard stop if missing, print actionable error with BMAD repo link
4. Clone or pull `SauliusDev/imp-agent` into `/tmp/imp-agent-install`
5. Exec: `python3 /tmp/imp-agent-install/install.py --project-dir "$(pwd)"`

### Phase 2: `install.py` (Python + rich)

1. Print IMP header panel
2. Show preflight summary (project name derived from `pwd` basename, BMAD ✓, Python ✓)
3. Copy `engine/` → `_imp/` — overwrite all files, show count
4. Copy `skills/` → `.claude/skills/{imp-init,mind-sync}/` — overwrite
5. Generate `_imp/config.yaml` from template — **skip if exists** (preserve user edits), inject project name
6. Create `.claude/` if missing (with warning)
7. Detect `mind` CLI (`which mind`) → interactive prompt:
   _"Enable mind-sync integration? [y/N]"_
   - **Yes**: set `mind_sync_after_story: true` in config, create `_mind/` from templates
   - **No**: set `mind_sync_after_story: false`, skip `_mind/` creation
   - Mind-sync skill is copied regardless (toggling it later just means editing config)
8. Print post-install summary + next steps

### Post-install Output

```
╭──────────────────────────────────────────╮
│  IMP installed successfully in myproject │
╰──────────────────────────────────────────╯

  Engine      _imp/            7 files
  Skills      .claude/skills/  imp-init, mind-sync
  Config      _imp/config.yaml created
  Mind sync   enabled          _mind/ created

Next steps:
  1. Edit _imp/config.yaml      — set models, usage caps, pause points
  2. Run /bmad-sprint-planning  — if not done yet
  3. Run /imp-init              — initialize the ledger from sprint-status.yaml
  4. Run: bash _imp/imp.sh all
```

## Re-install / Update Behavior

Re-running the installer on a project where IMP is already present:

| Component | Behavior |
|---|---|
| `_imp/*.py`, `_imp/imp.sh` | Always overwrite — engine updates are safe |
| `_imp/config.yaml` | Skip if exists — preserve user edits |
| `.claude/skills/imp-init/` | Always overwrite |
| `.claude/skills/mind-sync/` | Always overwrite |
| `_mind/` | Only create if not present |

Output on re-install:
```
  Engine      _imp/            updated (7 files overwritten)
  Config      _imp/config.yaml preserved ← your edits kept
  Skills      .claude/skills/  updated
```

## Mind-Sync Integration

Mind is a separate optional project (`pip install project-mind`). It is toggled at install time via interactive prompt, and can be re-toggled anytime by editing `_imp/config.yaml`:

```yaml
mind_sync_after_story: true   # or false to disable
mind_sync_model: claude-sonnet-4-6
```

Detection at install time:
```python
subprocess.run(["which", "mind"], capture_output=True).returncode == 0
```

If `mind` is not on PATH, the prompt still shows it with a note:
```
  mind CLI not found on PATH.
  Install it: pip install project-mind
  Enable mind-sync integration? [y/N]
```

User can still opt in — installer will configure the flag and create `_mind/` even if mind isn't installed yet.

## Error Handling

### BMAD not detected
```
✗ BMAD not found in .claude/skills/

  IMP requires BMAD to run. Set up BMAD first:
  → https://github.com/SauliusDev/bmad-method

  Then re-run this installer.
```
Exit code: 1.

### Python < 3.10
```
✗ Python 3.10+ required (found 3.9.x)

  Install Python 3.10+: https://python.org
```
Exit code: 1.

### No `.claude/` directory
```
⚠  No .claude/ directory found — creating it
```
Continue — not a hard stop. IMP will populate the skills directory.

### No obvious project markers
```
⚠  No package.json / pyproject.toml / go.mod detected.
   Are you in the right directory? Continuing anyway.
```
Continue — warn only.

## Prerequisites (documented in README)

- BMAD already set up in the project (`.claude/skills/bmad-*/` present)
- Python 3.10+
- Claude Code CLI (`claude` command)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` must exist before running `/imp-init`

## What's Project-Specific (Not Templated)

- `_imp/config.yaml` — user edits `pause_after` story IDs, usage caps, model choices
- `_mind/` — built up over time by mind-sync runs; starts from blank template
- `ledger.json` — created by `/imp-init` from sprint-status, not part of installer
