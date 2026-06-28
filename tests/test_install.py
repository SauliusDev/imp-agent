import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from install import (
    install_config,
    install_engine,
    install_skills,
)
from imp_runner import (
    ClaudeStreamParser,
    CodexStreamParser,
    _build_claude_args,
    _build_codex_args,
    run_agent_subprocess,
)
from imp_state import create_initial_state


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


def test_install_skills_can_target_codex_skills_dir(tmp_path):
    install_skills(tmp_path, agent_provider="codex")
    assert (tmp_path / ".agents" / "skills" / "imp-init" / "SKILL.md").exists()
    assert not (tmp_path / ".claude").exists()


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


def test_config_template_includes_agent_provider():
    config_template = (Path(__file__).parent.parent / "templates" / "config.yaml").read_text()
    assert "agent_provider:" in config_template
    assert "claude|codex" in config_template


def test_build_codex_args_uses_codex_exec(monkeypatch):
    monkeypatch.setattr("imp_runner._codex_supports_ask_for_approval", lambda: True)
    args = _build_codex_args("/bmad-dev-story story.md", "gpt-5.5", "high")
    assert args[:2] == ["codex", "exec"]
    assert "--cd" in args
    assert "--sandbox" in args
    assert "--ask-for-approval" in args
    assert "--json" in args
    assert "--model" in args
    assert args[-1] == "/bmad-dev-story story.md"


def test_build_claude_args_keeps_claude_stream_json():
    args = _build_claude_args("/bmad-dev-story story.md", "claude-sonnet-4-6", "high")
    assert args[0:2] == ["claude", "--print"]
    assert "--output-format" in args
    assert "stream-json" in args


def test_codex_parser_reads_text_and_command_events():
    parser = CodexStreamParser()
    assert parser.feed('{"type":"unknown.event","value":1}') == []
    assert parser.feed(
        '{"type":"item.completed","item":{"type":"agent_message","text":"Hello\\nworld"}}'
    ) == ["Hello", "world"]
    assert parser.feed(
        '{"type":"item.started","item":{"type":"command_execution","command":"pwd"}}'
    ) == ["[command] pwd"]
    assert parser.feed(
        '{"type":"item.completed","item":{"type":"error","message":"bad model"}}'
    ) == ["[error] bad model"]
    assert parser.feed(
        '{"type":"turn.failed","error":{"message":"failed turn"}}'
    ) == ["[error] failed turn"]


def test_claude_parser_still_parses_text_delta():
    parser = ClaudeStreamParser()
    line = (
        '{"event":{"type":"content_block_delta",'
        '"delta":{"type":"text_delta","text":"hello\\n"}}}'
    )
    assert parser.feed(line) == ["hello"]


def test_run_agent_subprocess_can_keep_stderr_out_of_jsonl(tmp_path):
    script = (
        "import sys; "
        "print('{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"ok\"}}'); "
        "print('diagnostic', file=sys.stderr)"
    )
    state = create_initial_state(config={"agent_provider": "codex"}, epic_id="all")
    jsonl = tmp_path / "out.jsonl"
    readable = tmp_path / "out.log"

    exit_code = asyncio.run(run_agent_subprocess(
        [sys.executable, "-c", script],
        str(jsonl),
        str(readable),
        state,
        CodexStreamParser(),
        stderr_to_readable=True,
    ))

    assert exit_code == 0
    assert "diagnostic" not in jsonl.read_text()
    assert "diagnostic" in readable.read_text()
    assert "ok" in readable.read_text()
