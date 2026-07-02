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


def test_build_step_prompt_keeps_current_dev_and_review_contracts():
    story_file = "_bmad-output/implementation-artifacts/1-1-example.md"

    assert build_step_prompt("dev", story_id="1-1-example", story_file=story_file).startswith(
        f"/bmad-dev-story {story_file}"
    )
    assert build_step_prompt("review", story_id="1-1-example", story_file=story_file).startswith(
        f"/bmad-code-review {story_file}"
    )


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
