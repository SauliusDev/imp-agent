from __future__ import annotations

from dataclasses import dataclass


PIPELINE_STEP_IDS = ["spec", "dev", "review"]

AGENT_PROVIDER_CLAUDE = "claude"
AGENT_PROVIDER_CODEX = "codex"
AGENT_PROVIDERS = {AGENT_PROVIDER_CLAUDE, AGENT_PROVIDER_CODEX}


@dataclass(frozen=True)
class StepDefinition:
    step_id: str
    skill: str
    model_key: str
    effort_key: str
    verifier: str
    max_attempts_key: str | None = None


@dataclass(frozen=True)
class StepRuntime:
    provider: str
    model: str
    effort: str


STEP_DEFINITIONS = {
    "spec": StepDefinition(
        step_id="spec",
        skill="bmad-create-story",
        model_key="model_spec",
        effort_key="effort_spec",
        verifier="story_file_exists",
    ),
    "dev": StepDefinition(
        step_id="dev",
        skill="bmad-dev-story",
        model_key="model_dev",
        effort_key="effort_dev",
        verifier="exit_code_zero",
    ),
    "review": StepDefinition(
        step_id="review",
        skill="bmad-code-review",
        model_key="model_review",
        effort_key="effort_review",
        verifier="sprint_status_done",
        max_attempts_key="max_review_attempts",
    ),
}

_HALT_SIGNAL = (
    "\n## Halt signal\n"
    "If you discover a structural flaw that makes the story impossible to implement,\n"
    "write a short explanation to the file _imp/HALT and then exit."
)

PREAMBLE_SPEC = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the story spec without halting for user input:\n"
    "- Do NOT use HALT or ask for clarification — make reasonable assumptions\n"
    "- Do NOT present menus or wait for responses\n"
    "- Complete the full spec and write the story file as per your normal workflow"
    + _HALT_SIGNAL
)

PREAMBLE_DEV = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the full implementation without halting for user input:\n"
    "- Do NOT use HALT, do NOT ask for manual verification, do NOT wait for responses\n"
    "- If a task requires manual action (e.g. pressing F5, opening a browser), "
    "skip the verification and mark it as done with a note that manual verification is deferred\n"
    "- Make all decisions autonomously — prefer the safest reasonable choice\n"
    "- Complete all tasks and update the story file status as per your normal workflow"
    + _HALT_SIGNAL
)

PREAMBLE_REVIEW = (
    "\n## AUTONOMOUS PIPELINE MODE\n"
    "You are running inside an automated pipeline with no human present.\n"
    "Complete the full code review without halting for user input:\n"
    "- Run all adversarial review layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor)\n"
    "- Auto-apply all patch fixes directly to source files\n"
    "- Defer all decision-needed findings (log them in the story file with [Review][Defer])\n"
    "- Do NOT present menus, ask for choices, or wait for responses\n"
    "- Update the story file status and sprint-status.yaml as per your normal workflow"
    + _HALT_SIGNAL
)

DEFAULT_MODELS = {
    "model_spec": "claude-sonnet-4-6",
    "model_dev": "claude-sonnet-4-6",
    "model_review": "claude-opus-4-6",
    "effort_spec": "medium",
    "effort_dev": "high",
    "effort_review": "high",
}


def get_step_definition(step_id: str) -> StepDefinition:
    try:
        return STEP_DEFINITIONS[step_id]
    except KeyError as exc:
        raise ValueError(f"unknown step: {step_id}") from exc


def build_step_prompt(step_id: str, *, story_id: str, story_file: str) -> str:
    definition = get_step_definition(step_id)
    if definition.step_id == "spec":
        return (
            f"/{definition.skill} {story_id}\n\n"
            f"IMPORTANT: The story file MUST be written to exactly this path: `{story_file}`\n"
            f"{PREAMBLE_SPEC}"
        )
    if definition.step_id == "dev":
        return f"/{definition.skill} {story_file}\n{PREAMBLE_DEV}"
    if definition.step_id == "review":
        return f"/{definition.skill} {story_file}\n{PREAMBLE_REVIEW}"
    raise ValueError(f"unknown step: {step_id}")


def resolve_step_runtime(step_id: str, config: dict) -> StepRuntime:
    definition = get_step_definition(step_id)
    return StepRuntime(
        provider=_normalize_agent_provider(config.get("agent_provider")),
        model=str(config.get(definition.model_key, DEFAULT_MODELS[definition.model_key])),
        effort=str(config.get(definition.effort_key, DEFAULT_MODELS[definition.effort_key])),
    )


def _normalize_agent_provider(provider: str | None) -> str:
    normalized = str(provider or AGENT_PROVIDER_CLAUDE).strip().lower()
    if normalized not in AGENT_PROVIDERS:
        return AGENT_PROVIDER_CLAUDE
    return normalized
