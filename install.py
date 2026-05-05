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
