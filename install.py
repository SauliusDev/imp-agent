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
