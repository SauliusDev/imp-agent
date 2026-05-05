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
