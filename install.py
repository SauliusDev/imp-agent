#!/usr/bin/env python3
"""IMP Agent installer."""

import argparse
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

SCRIPT_DIR = Path(__file__).parent
console = Console()

PROJECT_MARKERS = ["package.json", "pyproject.toml", "go.mod", "Cargo.toml"]


def install_engine(project_dir: Path) -> tuple[int, bool]:
    """Copy engine/ and built web assets → _imp/. Returns (file_count, was_update)."""
    imp_dir = project_dir / "_imp"
    was_update = imp_dir.exists()
    imp_dir.mkdir(exist_ok=True)

    engine_dir = SCRIPT_DIR / "engine"
    count = 0
    for src in sorted(engine_dir.iterdir()):
        if src.is_file():
            shutil.copy2(src, imp_dir / src.name)
            count += 1

    web_dist = SCRIPT_DIR / "web" / "dist"
    if web_dist.exists():
        web_dest = imp_dir / "web" / "dist"
        if web_dest.exists():
            shutil.rmtree(web_dest)
        shutil.copytree(web_dist, web_dest)

    (imp_dir / "imp.sh").chmod(0o755)
    return count, was_update


def skills_dest_for_provider(project_dir: Path, agent_provider: str = "claude") -> Path:
    """Return the IMP skill destination for the selected agent provider."""
    provider = agent_provider.strip().lower()
    if provider == "codex":
        return project_dir / ".agents" / "skills"
    return project_dir / ".claude" / "skills"


def install_skills(project_dir: Path, agent_provider: str = "claude") -> Path:
    """Copy skills/ to the provider-specific skills directory. Returns destination."""
    skills_src = SCRIPT_DIR / "skills"
    skills_dest = skills_dest_for_provider(project_dir, agent_provider)
    skills_dest.mkdir(parents=True, exist_ok=True)

    for skill_dir in sorted(skills_src.iterdir()):
        if skill_dir.is_dir():
            dest = skills_dest / skill_dir.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill_dir, dest)
    return skills_dest


def install_config(project_dir: Path) -> bool:
    """Copy config template → _imp/config.yaml. Returns True if created."""
    config_dest = project_dir / "_imp" / "config.yaml"
    if config_dest.exists():
        return False
    shutil.copy2(SCRIPT_DIR / "templates" / "config.yaml", config_dest)
    return True


VSCODE_SETTINGS = """{
  // _imp/ is written to thousands of times per second while the imp agent runs
  // (stream-json logs flushed per partial message). VS Code's file watcher does
  // NOT honor .gitignore, so without these excludes the renderer's FSEvents
  // backlog grows until the V8 heap hits its ~4GB ceiling and VS Code crashes
  // (JavaScript heap out of memory). Keep these excludes in place.
  "files.watcherExclude": {
    "**/_imp/**": true
  },
  "search.exclude": {
    "**/_imp": true
  },
  "files.exclude": {
    "**/_imp/logs": true
  }
}
"""


def install_vscode_excludes(project_dir: Path) -> str:
    """Write .vscode/settings.json excluding _imp/ from the VS Code watcher.

    Without this, the high-frequency log writes under _imp/ flood VS Code's
    file watcher and crash it with a JavaScript-heap OOM. Returns one of:
    "created", "preserved" (already has _imp exclude or a settings file we
    won't risk clobbering).
    """
    vscode_dir = project_dir / ".vscode"
    settings = vscode_dir / "settings.json"
    if settings.exists():
        # Never clobber an existing (possibly JSONC) settings file.
        if "_imp" in settings.read_text():
            return "preserved"
        return "manual"
    vscode_dir.mkdir(exist_ok=True)
    settings.write_text(VSCODE_SETTINGS)
    return "created"


def check_project_markers(project_dir: Path) -> None:
    if not any((project_dir / m).exists() for m in PROJECT_MARKERS):
        console.print("[yellow]  ⚠  No package.json / pyproject.toml / go.mod detected.[/yellow]")
        console.print("     Are you in the right directory? Continuing anyway.")
        console.print()


def ensure_agent_dir(project_dir: Path, agent_provider: str) -> None:
    if agent_provider.strip().lower() == "codex":
        agents_dir = project_dir / ".agents"
        if not agents_dir.exists():
            console.print("[yellow]  ⚠  No .agents/ directory found — creating it[/yellow]")
            console.print()
            agents_dir.mkdir(parents=True)
        return

    claude_dir = project_dir / ".claude"
    if not claude_dir.exists():
        console.print("[yellow]  ⚠  No .claude/ directory found — creating it[/yellow]")
        console.print()
        claude_dir.mkdir(parents=True)


def print_summary(
    project_name: str,
    engine_count: int,
    was_update: bool,
    config_created: bool,
    vscode_status: str,
    skills_dest: Path,
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
    if skills_dest.is_relative_to(Path.cwd()):
        skills_label = str(skills_dest.relative_to(Path.cwd()))
    else:
        skills_label = str(skills_dest)
    table.add_row("Skills", skills_label, "imp-init")

    if config_created:
        table.add_row("Config", "_imp/config.yaml", "created")
    else:
        table.add_row("Config", "_imp/config.yaml", "preserved ← your edits kept")

    vscode_notes = {
        "created": "created — prevents VS Code OOM crash",
        "preserved": "_imp exclude already present",
        "manual": "[yellow]exists — add **/_imp/** to files.watcherExclude[/yellow]",
    }
    table.add_row("VS Code", ".vscode/settings.json", vscode_notes[vscode_status])

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
    parser.add_argument(
        "--agent-provider",
        choices=["claude", "codex"],
        default="claude",
        help="Install provider-specific IMP skill target (default: claude)",
    )
    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    project_name = project_dir.name
    agent_provider = args.agent_provider

    console.print(Panel.fit("[bold cyan]IMP Agent Installer[/bold cyan]", border_style="cyan"))
    console.print()

    if sys.version_info < (3, 10):
        console.print(
            f"[red]✗ Python 3.10+ required "
            f"(found {sys.version_info.major}.{sys.version_info.minor})[/red]"
        )
        sys.exit(1)

    check_project_markers(project_dir)
    ensure_agent_dir(project_dir, agent_provider)

    engine_count, was_update = install_engine(project_dir)
    skills_dest = install_skills(project_dir, agent_provider)
    config_created = install_config(project_dir)
    vscode_status = install_vscode_excludes(project_dir)

    print_summary(
        project_name, engine_count, was_update, config_created, vscode_status, skills_dest,
    )


if __name__ == "__main__":
    main()
