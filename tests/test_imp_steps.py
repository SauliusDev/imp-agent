import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from imp_steps import (  # noqa: E402
    PIPELINE_STEP_IDS,
    StepDefinition,
    build_step_prompt,
    get_step_definition,
    resolve_step_runtime,
)


def test_pipeline_steps_match_current_bmad_flow():
    assert PIPELINE_STEP_IDS == ["spec", "dev", "review"]


def test_get_step_definition_returns_bmad_skill_mapping():
    spec = get_step_definition("spec")

    assert isinstance(spec, StepDefinition)
    assert spec.step_id == "spec"
    assert spec.skill == "bmad-create-story"
    assert spec.model_key == "model_spec"
    assert spec.effort_key == "effort_spec"
    assert spec.verifier == "story_file_exists"


def test_build_step_prompt_keeps_current_spec_contract():
    prompt = build_step_prompt(
        "spec",
        story_id="1-1-example",
        story_file="_bmad-output/implementation-artifacts/1-1-example.md",
    )

    assert "/bmad-create-story 1-1-example" in prompt
    assert "MUST be written to exactly this path" in prompt
    assert "_bmad-output/implementation-artifacts/1-1-example.md" in prompt
    assert "- Do NOT use HALT or ask for clarification — make reasonable assumptions" in prompt
    assert "write a short explanation to the file _imp/HALT and then exit." in prompt


def test_build_step_prompt_keeps_current_dev_and_review_contracts():
    story_file = "_bmad-output/implementation-artifacts/1-1-example.md"

    dev_prompt = build_step_prompt("dev", story_id="1-1-example", story_file=story_file)
    review_prompt = build_step_prompt("review", story_id="1-1-example", story_file=story_file)

    assert dev_prompt.startswith(f"/bmad-dev-story {story_file}")
    assert (
        "- Do NOT use HALT, do NOT ask for manual verification, do NOT wait for responses"
        in dev_prompt
    )
    assert (
        "skip the verification and mark it as done with a note that manual verification is deferred"
        in dev_prompt
    )
    assert "- Make all decisions autonomously — prefer the safest reasonable choice" in dev_prompt
    assert "write a short explanation to the file _imp/HALT and then exit." in dev_prompt

    assert review_prompt.startswith(f"/bmad-code-review {story_file}")
    assert (
        "- Defer all decision-needed findings (log them in the story file with [Review][Defer])"
        in review_prompt
    )
    assert "write a short explanation to the file _imp/HALT and then exit." in review_prompt


def test_resolve_step_runtime_uses_configured_model_and_effort():
    runtime = resolve_step_runtime(
        "dev",
        {
            "agent_provider": "codex",
            "model_dev": "gpt-5.5",
            "effort_dev": "high",
        },
    )

    assert runtime.provider == "codex"
    assert runtime.model == "gpt-5.5"
    assert runtime.effort == "high"
