import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from install import (
    install_config,
    install_engine,
    install_skills,
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
