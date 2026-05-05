# IMP Agent Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a one-liner curl installer that copies the IMP engine and skills into any BMAD project, with interactive mind-sync toggle.

**Architecture:** A bash bootstrapper (`setup.sh`) handles preflight checks and clones the repo to `/tmp/imp-agent-install`, then delegates to a Python installer (`install.py`) that uses `rich` for clean TUI output and handles all file operations and interactive prompts.

**Tech Stack:** Bash, Python 3.10+, rich, pytest

---

## File Map

| File | Purpose |
|---|---|
| `setup.sh` | Bash bootstrapper: Python check, rich check, BMAD check, clone repo, exec install.py |
| `install.py` | Python installer: copies files, handles mind-sync prompt, prints summary |
| `engine/` | 7 IMP engine files copied verbatim from mermvis — source of truth for installs |
| `skills/imp-init/SKILL.md` | Claude skill: initialize ledger from sprint-status.yaml |
| `skills/mind-sync/SKILL.md` | Claude skill: sync project memory |
| `skills/mind-sync/workflow.md` | Mind-sync step-by-step workflow |
| `templates/config.yaml` | Config template with clean defaults (no project-specific entries) |
| `templates/mind/mind.md` | Blank 8-section project memory template with `{{project_name}}` / `{{today}}` |
| `templates/mind/index.yaml` | Blank mind index template with `{{project_name}}` / `{{today}}` |
| `tests/test_install.py` | Pytest tests for install.py file operation functions |
| `README.md` | One-liner install command, prerequisites, post-install steps |

---

## Task 1: Scaffold directories and copy engine files

**Files:**
- Create: `engine/` (7 files copied from mermvis)
- Create: `skills/`, `templates/`, `templates/mind/`, `tests/`

- [ ] **Step 1: Create directory structure**

```bash
cd /Users/azuolasbalbieris/dev/imp-agent
mkdir -p engine skills/imp-init skills/mind-sync templates/mind tests
```

- [ ] **Step 2: Copy engine files from mermvis**

```bash
cp /Users/azuolasbalbieris/dev/mermvis/_imp/imp.sh engine/
cp /Users/azuolasbalbieris/dev/mermvis/_imp/imp_runner.py engine/
cp /Users/azuolasbalbieris/dev/mermvis/_imp/imp_state.py engine/
cp /Users/azuolasbalbieris/dev/mermvis/_imp/imp_display.py engine/
cp /Users/azuolasbalbieris/dev/mermvis/_imp/imp_keys.py engine/
cp /Users/azuolasbalbieris/dev/mermvis/_imp/imp_usage.py engine/
cp /Users/azuolasbalbieris/dev/mermvis/_imp/imp-ledger.py engine/
```

- [ ] **Step 3: Verify 7 files are present**

```bash
ls -1 engine/
```

Expected output:
```
imp-ledger.py
imp.sh
imp_display.py
imp_keys.py
imp_runner.py
imp_state.py
imp_usage.py
```

- [ ] **Step 4: Commit**

```bash
git add engine/
git commit -m "feat: add IMP engine files (copied from mermvis)"
```

---

## Task 2: Copy skills

**Files:**
- Create: `skills/imp-init/SKILL.md`
- Create: `skills/mind-sync/SKILL.md`
- Create: `skills/mind-sync/workflow.md`

- [ ] **Step 1: Copy imp-init skill**

```bash
cp /Users/azuolasbalbieris/dev/mermvis/.claude/skills/imp-init/SKILL.md skills/imp-init/SKILL.md
```

- [ ] **Step 2: Copy mind-sync skill**

```bash
cp /Users/azuolasbalbieris/dev/mermvis/.claude/skills/mind-sync/SKILL.md skills/mind-sync/SKILL.md
cp /Users/azuolasbalbieris/dev/mermvis/.claude/skills/mind-sync/workflow.md skills/mind-sync/workflow.md
```

- [ ] **Step 3: Verify**

```bash
find skills/ -type f
```

Expected:
```
skills/imp-init/SKILL.md
skills/mind-sync/SKILL.md
skills/mind-sync/workflow.md
```

- [ ] **Step 4: Commit**

```bash
git add skills/
git commit -m "feat: add imp-init and mind-sync skills"
```

---

## Task 3: Create templates

**Files:**
- Create: `templates/config.yaml`
- Create: `templates/mind/mind.md`
- Create: `templates/mind/index.yaml`

- [ ] **Step 1: Create `templates/config.yaml`**

This is a clean version of mermvis config — project-specific `pause_after` entries removed, `mind_sync_after_story` defaulting to `false` (installer sets this based on user choice).

Write the file with this exact content:

```yaml
# IMP Pipeline Configuration
# Edit these values to customize the runner's behavior.
# Changes take effect on the next imp.sh invocation.

# ---------------------------------------------------------------------------
# Per-step model and effort
# ---------------------------------------------------------------------------
# Each pipeline step can use a different model + effort level.
# Effort levels: low (fast/cheap), medium (balanced), high (deeper reasoning)
#
# Available models: claude-sonnet-4-6, claude-opus-4-7, claude-haiku-4-5-20251001
#
# spec   — generates story spec from PRD/epics/architecture. Document work.
# dev    — implements the story. Writes actual code.
# review — adversarial code review. Quality gate.

model_spec: claude-sonnet-4-6
effort_spec: high

model_dev: claude-sonnet-4-6
effort_dev: high

model_review: claude-sonnet-4-6
effort_review: high

# ---------------------------------------------------------------------------
# Review gate
# ---------------------------------------------------------------------------
# Maximum number of times code review can fail before a story is blocked.
# Set to 0 for infinite retries. Recommended: 3 for most projects.
max_review_attempts: 3

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
# Automatically show agent output panel when each step starts (toggle with [l])
output_on_step_start: true

# ---------------------------------------------------------------------------
# Paths (relative to project root)
# ---------------------------------------------------------------------------
mind_file: _mind/mind.md
sprint_status: _bmad-output/implementation-artifacts/sprint-status.yaml
artifacts_dir: _bmad-output/implementation-artifacts

# ---------------------------------------------------------------------------
# Usage budget strategy
# ---------------------------------------------------------------------------
# base_limit_pct  — pause/quit when 5h rolling usage hits this % (0 = off).
# limit_7d_pct    — pause/quit when 7d cumulative usage hits this % (0 = off).
# extra_limit_eur — hard stop when extra credit spend reaches this € (0 = off).
# on_base_limit   — action when base/7d cap is hit: "pause" or "quit".
# on_extra_limit  — action when extra € cap is hit: "pause" or "quit".

base_limit_pct: 0
limit_7d_pct: 0
extra_limit_eur: 50.00
on_base_limit: pause
on_extra_limit: pause

# ---------------------------------------------------------------------------
# Planned pause points
# ---------------------------------------------------------------------------
# pause_after         - pause after these story IDs complete (reload live with r).
# pause_between_epics - pause before starting each new epic for manual QA gates.

pause_after:
  # - story-id-here

pause_between_epics: false

# ---------------------------------------------------------------------------
# Mind sync
# ---------------------------------------------------------------------------
# mind_sync_after_story — run mind-sync after each story completes (blocking).
#                         Keeps mind.md current so every spec gets fresh context.
# mind_sync_model       — model to use for mind-sync.

mind_sync_after_story: false
mind_sync_model: claude-sonnet-4-6
```

- [ ] **Step 2: Create `templates/mind/mind.md`**

```markdown
# Project Mind — {{project_name}}
_Updated: {{today}} | Syncs: 0_

## Current State
Project just initialized.

## Active Work
(none yet)

## Lessons Learned
(none yet)

## Key Decisions
(none yet)

## Journey
(none yet)
```

- [ ] **Step 3: Create `templates/mind/index.yaml`**

```yaml
project: {{project_name}}
last_sync: "{{today}}T00:00:00"
sync_count: 0
watch_patterns:
  - _bmad-output
transcript_sources: []
tracked_files: []
```

- [ ] **Step 4: Commit**

```bash
git add templates/
git commit -m "feat: add config and mind templates"
```

---

## Task 4: Write setup.sh

**Files:**
- Create: `setup.sh`

- [ ] **Step 1: Write `setup.sh`**

```bash
#!/usr/bin/env bash
# IMP Agent installer bootstrapper.
# Run from your project root: curl -fsSL https://raw.githubusercontent.com/SauliusDev/imp-agent/main/setup.sh | bash

set -euo pipefail

IMP_REPO="https://github.com/SauliusDev/imp-agent"
IMP_TMP="/tmp/imp-agent-install"

# ── 1. Python 3.10+ ──────────────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
  echo "" >&2
  echo "✗ python3 not found." >&2
  echo "" >&2
  echo "  Install Python 3.10+: https://python.org" >&2
  exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "" >&2
  echo "✗ Python 3.10+ required (found $PY_VERSION)" >&2
  echo "" >&2
  echo "  Install Python 3.10+: https://python.org" >&2
  exit 1
fi

# ── 2. rich ──────────────────────────────────────────────────────────────────

if ! python3 -c "import rich" 2>/dev/null; then
  echo "Missing dependency: rich"
  echo ""
  read -rp "Install it now? (pip install rich) [Y/n] " answer
  answer="${answer:-Y}"
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    pip3 install --break-system-packages rich 2>/dev/null || pip3 install rich
  else
    echo "" >&2
    echo "Aborted. Install rich manually: pip3 install rich" >&2
    exit 1
  fi
fi

# ── 3. BMAD check ────────────────────────────────────────────────────────────

if [ ! -d ".claude/skills/bmad-dev-story" ]; then
  echo "" >&2
  echo "✗ BMAD not found in .claude/skills/" >&2
  echo "" >&2
  echo "  IMP requires BMAD to run. Set up BMAD first:" >&2
  echo "  → https://github.com/SauliusDev/bmad-method" >&2
  echo "" >&2
  echo "  Then re-run this installer." >&2
  exit 1
fi

# ── 4. Clone or update imp-agent repo ────────────────────────────────────────

if [ -d "$IMP_TMP/.git" ]; then
  echo "Updating IMP installer..."
  git -C "$IMP_TMP" pull --rebase --quiet
else
  echo "Fetching IMP installer..."
  rm -rf "$IMP_TMP"
  git clone --quiet "$IMP_REPO" "$IMP_TMP"
fi

# ── 5. Hand off to Python installer ──────────────────────────────────────────

exec python3 "$IMP_TMP/install.py" --project-dir "$(pwd)"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x setup.sh
```

- [ ] **Step 3: Commit**

```bash
git add setup.sh
git commit -m "feat: add setup.sh bash bootstrapper"
```

---

## Task 5: Write install.py file operation functions + tests

**Files:**
- Create: `install.py` (file operation functions only — no `main()` yet)
- Create: `tests/test_install.py`

- [ ] **Step 1: Write failing tests first**

Create `tests/test_install.py`:

```python
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from install import (
    create_mind_dir,
    install_config,
    install_engine,
    install_skills,
    set_mind_sync_flag,
)


def test_install_engine_fresh(tmp_path):
    count, was_update = install_engine(tmp_path)
    assert count == 7
    assert was_update is False
    assert (tmp_path / "_imp" / "imp.sh").exists()
    assert (tmp_path / "_imp" / "imp_runner.py").exists()


def test_install_engine_imp_sh_is_executable(tmp_path):
    install_engine(tmp_path)
    mode = oct((tmp_path / "_imp" / "imp.sh").stat().st_mode)
    assert mode.endswith("755")


def test_install_engine_returns_update_true_on_second_call(tmp_path):
    install_engine(tmp_path)
    _, was_update = install_engine(tmp_path)
    assert was_update is True


def test_install_skills_creates_skill_dirs(tmp_path):
    install_skills(tmp_path)
    assert (tmp_path / ".claude" / "skills" / "imp-init" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "skills" / "mind-sync" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "skills" / "mind-sync" / "workflow.md").exists()


def test_install_skills_overwrites_existing(tmp_path):
    skills_dir = tmp_path / ".claude" / "skills" / "imp-init"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("old content")
    install_skills(tmp_path)
    content = (skills_dir / "SKILL.md").read_text()
    assert content != "old content"


def test_install_config_creates_file(tmp_path):
    (tmp_path / "_imp").mkdir()
    created = install_config(tmp_path)
    assert created is True
    assert (tmp_path / "_imp" / "config.yaml").exists()


def test_install_config_skips_existing(tmp_path):
    (tmp_path / "_imp").mkdir()
    config = tmp_path / "_imp" / "config.yaml"
    config.write_text("my custom config\n")
    created = install_config(tmp_path)
    assert created is False
    assert config.read_text() == "my custom config\n"


def test_set_mind_sync_flag_enable(tmp_path):
    (tmp_path / "_imp").mkdir()
    config = tmp_path / "_imp" / "config.yaml"
    config.write_text("mind_sync_after_story: false\n")
    set_mind_sync_flag(tmp_path, enabled=True)
    assert "mind_sync_after_story: true" in config.read_text()


def test_set_mind_sync_flag_disable(tmp_path):
    (tmp_path / "_imp").mkdir()
    config = tmp_path / "_imp" / "config.yaml"
    config.write_text("mind_sync_after_story: true\n")
    set_mind_sync_flag(tmp_path, enabled=False)
    assert "mind_sync_after_story: false" in config.read_text()


def test_set_mind_sync_flag_noop_if_no_config(tmp_path):
    set_mind_sync_flag(tmp_path, enabled=True)  # should not raise


def test_create_mind_dir_creates_structure(tmp_path):
    created = create_mind_dir(tmp_path, "myproject")
    assert created is True
    assert (tmp_path / "_mind" / "mind.md").exists()
    assert (tmp_path / "_mind" / "index.yaml").exists()
    assert (tmp_path / "_mind" / "logs").is_dir()


def test_create_mind_dir_substitutes_project_name(tmp_path):
    create_mind_dir(tmp_path, "myproject")
    mind_content = (tmp_path / "_mind" / "mind.md").read_text()
    index_content = (tmp_path / "_mind" / "index.yaml").read_text()
    assert "myproject" in mind_content
    assert "myproject" in index_content
    assert "{{project_name}}" not in mind_content
    assert "{{project_name}}" not in index_content


def test_create_mind_dir_substitutes_today(tmp_path):
    create_mind_dir(tmp_path, "myproject")
    today = date.today().isoformat()
    mind_content = (tmp_path / "_mind" / "mind.md").read_text()
    assert today in mind_content
    assert "{{today}}" not in mind_content


def test_create_mind_dir_skips_if_exists(tmp_path):
    (tmp_path / "_mind").mkdir()
    created = create_mind_dir(tmp_path, "myproject")
    assert created is False
```

- [ ] **Step 2: Run tests — confirm they all fail with ImportError**

```bash
cd /Users/azuolasbalbieris/dev/imp-agent
python -m pytest tests/test_install.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'install'`

- [ ] **Step 3: Write `install.py` file operation functions**

Create `install.py` with this content:

```python
#!/usr/bin/env python3
"""IMP Agent installer."""

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

SCRIPT_DIR = Path(__file__).parent
console = Console()

PROJECT_MARKERS = ["package.json", "pyproject.toml", "go.mod", "Cargo.toml"]


def install_engine(project_dir: Path) -> tuple[int, bool]:
    """Copy engine/ → _imp/. Returns (file_count, was_update)."""
    imp_dir = project_dir / "_imp"
    was_update = imp_dir.exists()
    imp_dir.mkdir(exist_ok=True)

    engine_dir = SCRIPT_DIR / "engine"
    count = 0
    for src in sorted(engine_dir.iterdir()):
        if src.is_file():
            shutil.copy2(src, imp_dir / src.name)
            count += 1

    (imp_dir / "imp.sh").chmod(0o755)
    return count, was_update


def install_skills(project_dir: Path) -> None:
    """Copy skills/ → .claude/skills/ (overwrite)."""
    skills_src = SCRIPT_DIR / "skills"
    skills_dest = project_dir / ".claude" / "skills"
    skills_dest.mkdir(parents=True, exist_ok=True)

    for skill_dir in sorted(skills_src.iterdir()):
        if skill_dir.is_dir():
            dest = skills_dest / skill_dir.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill_dir, dest)


def install_config(project_dir: Path) -> bool:
    """Copy config template → _imp/config.yaml. Returns True if created."""
    config_dest = project_dir / "_imp" / "config.yaml"
    if config_dest.exists():
        return False
    shutil.copy2(SCRIPT_DIR / "templates" / "config.yaml", config_dest)
    return True


def set_mind_sync_flag(project_dir: Path, enabled: bool) -> None:
    """Update mind_sync_after_story in _imp/config.yaml."""
    config_path = project_dir / "_imp" / "config.yaml"
    if not config_path.exists():
        return
    content = config_path.read_text()
    if enabled:
        content = content.replace("mind_sync_after_story: false", "mind_sync_after_story: true")
    else:
        content = content.replace("mind_sync_after_story: true", "mind_sync_after_story: false")
    config_path.write_text(content)


def create_mind_dir(project_dir: Path, project_name: str) -> bool:
    """Create _mind/ from templates. Returns True if created, False if existed."""
    mind_dir = project_dir / "_mind"
    if mind_dir.exists():
        return False

    mind_dir.mkdir()
    (mind_dir / "logs").mkdir()

    today = date.today().isoformat()
    templates_dir = SCRIPT_DIR / "templates" / "mind"
    for src in sorted(templates_dir.iterdir()):
        if src.is_file():
            content = src.read_text()
            content = content.replace("{{project_name}}", project_name)
            content = content.replace("{{today}}", today)
            (mind_dir / src.name).write_text(content)

    return True
```

- [ ] **Step 4: Run tests — all should pass**

```bash
python -m pytest tests/test_install.py -v
```

Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add install.py tests/
git commit -m "feat: add install.py file operation functions with tests"
```

---

## Task 6: Complete install.py — interactive prompts, display, and main()

**Files:**
- Modify: `install.py` (add remaining functions and `main()`)

- [ ] **Step 1: Add display helper functions to `install.py`**

Append these functions after `create_mind_dir`:

```python
def check_project_markers(project_dir: Path) -> None:
    if not any((project_dir / m).exists() for m in PROJECT_MARKERS):
        console.print("[yellow]  ⚠  No package.json / pyproject.toml / go.mod detected.[/yellow]")
        console.print("     Are you in the right directory? Continuing anyway.")
        console.print()


def ensure_claude_dir(project_dir: Path) -> None:
    claude_dir = project_dir / ".claude"
    if not claude_dir.exists():
        console.print("[yellow]  ⚠  No .claude/ directory found — creating it[/yellow]")
        console.print()
        claude_dir.mkdir(parents=True)


def handle_mind_sync(project_dir: Path, project_name: str) -> tuple[bool, bool]:
    """Interactive mind-sync prompt. Returns (enabled, mind_dir_created)."""
    mind_available = shutil.which("mind") is not None

    console.print()
    if not mind_available:
        console.print("  [yellow]mind CLI not found on PATH.[/yellow]")
        console.print("  Install it: [dim]pip install project-mind[/dim]")

    answer = console.input("  Enable mind-sync integration? [y/N] ").strip().lower()
    enabled = answer in ("y", "yes")

    set_mind_sync_flag(project_dir, enabled)
    mind_dir_created = create_mind_dir(project_dir, project_name) if enabled else False

    return enabled, mind_dir_created


def print_summary(
    project_name: str,
    engine_count: int,
    was_update: bool,
    config_created: bool,
    mind_enabled: bool,
    mind_dir_created: bool,
) -> None:
    console.print()
    action = "updated" if was_update else "installed"
    console.print(Panel.fit(
        f"[bold green]IMP {action} successfully in {project_name}[/bold green]",
        border_style="green",
    ))
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_column(style="dim")

    engine_note = f"updated ({engine_count} files overwritten)" if was_update else f"{engine_count} files"
    table.add_row("Engine", "_imp/", engine_note)
    table.add_row("Skills", ".claude/skills/", "imp-init, mind-sync")

    if config_created:
        table.add_row("Config", "_imp/config.yaml", "created")
    else:
        table.add_row("Config", "_imp/config.yaml", "preserved ← your edits kept")

    if mind_enabled:
        mind_note = "_mind/ created" if mind_dir_created else "_mind/ already exists"
        table.add_row("Mind sync", "enabled", mind_note)
    else:
        table.add_row("Mind sync", "disabled", "")

    console.print(table)
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  1. Edit [cyan]_imp/config.yaml[/cyan]      — set models, usage caps, pause points")
    console.print("  2. Run [cyan]/bmad-sprint-planning[/cyan]  — if not done yet")
    console.print("  3. Run [cyan]/imp-init[/cyan]              — initialize the ledger from sprint-status.yaml")
    console.print("  4. Run: [cyan]bash _imp/imp.sh all[/cyan]")
    console.print()


def main() -> None:
    parser = argparse.ArgumentParser(description="IMP Agent installer")
    parser.add_argument("--project-dir", required=True, type=Path)
    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    project_name = project_dir.name

    console.print(Panel.fit("[bold cyan]IMP Agent Installer[/bold cyan]", border_style="cyan"))
    console.print()

    if sys.version_info < (3, 10):
        console.print(
            f"[red]✗ Python 3.10+ required "
            f"(found {sys.version_info.major}.{sys.version_info.minor})[/red]"
        )
        sys.exit(1)

    check_project_markers(project_dir)
    ensure_claude_dir(project_dir)

    engine_count, was_update = install_engine(project_dir)
    install_skills(project_dir)
    config_created = install_config(project_dir)
    mind_enabled, mind_dir_created = handle_mind_sync(project_dir, project_name)

    print_summary(project_name, engine_count, was_update, config_created, mind_enabled, mind_dir_created)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Confirm existing tests still pass**

```bash
python -m pytest tests/test_install.py -v
```

Expected: 15 passed

- [ ] **Step 3: Smoke test the installer output (dry run against a temp dir)**

```bash
mkdir -p /tmp/test-project/.claude/skills/bmad-dev-story
# Run installer — answer "n" to mind-sync prompt
echo "n" | python3 install.py --project-dir /tmp/test-project
```

Expected: IMP header panel, installs engine + skills, prints summary with "Mind sync disabled".

- [ ] **Step 4: Verify files were created**

```bash
ls /tmp/test-project/_imp/
ls /tmp/test-project/.claude/skills/
```

Expected:
```
# _imp/
config.yaml  imp-ledger.py  imp.sh  imp_display.py  imp_keys.py  imp_runner.py  imp_state.py  imp_usage.py

# .claude/skills/
imp-init  mind-sync
```

- [ ] **Step 5: Commit**

```bash
git add install.py
git commit -m "feat: complete install.py with prompts, display, and main()"
```

---

## Task 7: Write README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
# IMP Agent

Autonomous BMAD pipeline orchestrator. Drives `/bmad-create-story`, `/bmad-dev-story`,
and `/bmad-code-review` in a loop over sprint stories — with a Rich TUI, persistent ledger,
usage gates, and optional mind-sync.

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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with install instructions"
```

---

## Self-Review Checklist

- [x] **spec: one-liner curl install** → covered by setup.sh + README
- [x] **spec: runs from project root** → `setup.sh` uses `$(pwd)`, no path args
- [x] **spec: Python 3.10+ check** → setup.sh + install.py main()
- [x] **spec: rich check with install offer** → setup.sh
- [x] **spec: BMAD hard stop** → setup.sh checks `.claude/skills/bmad-dev-story/`
- [x] **spec: clone/pull repo to /tmp** → setup.sh
- [x] **spec: overwrite engine, skip config** → install_engine (always copy), install_config (skip if exists)
- [x] **spec: skills always overwritten** → install_skills (rmtree + copytree)
- [x] **spec: mind detection + interactive prompt** → handle_mind_sync
- [x] **spec: mind CLI not on PATH shows note** → handle_mind_sync
- [x] **spec: _mind/ created only if not present** → create_mind_dir (returns False if exists)
- [x] **spec: set_mind_sync_flag updates config** → set_mind_sync_flag
- [x] **spec: no .claude/ dir → warn + create** → ensure_claude_dir
- [x] **spec: no project markers → warn + continue** → check_project_markers
- [x] **spec: post-install summary table** → print_summary
- [x] **spec: "preserved ← your edits kept" on re-install** → print_summary config row
- [x] **spec: templates/mind uses {{project_name}} and {{today}}** → create_mind_dir substitution
- [x] **no placeholders** → all steps have full code
- [x] **type consistency** → all function signatures match between tasks
