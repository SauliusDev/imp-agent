#!/usr/bin/env python3
"""
IMP Ledger — state management for the IMP implementation runner.

Ledger lives at _imp/ledger.json (or $IMP_LEDGER env override).
Config lives at _imp/config.yaml (plain key:value, no nested YAML needed).

Usage:
  python3 imp-ledger.py init <sprint-status-path>
  python3 imp-ledger.py status
  python3 imp-ledger.py next-story [epic-id|all]
  python3 imp-ledger.py step-done <story-id> <step>
  python3 imp-ledger.py step-attempt <story-id> <step>
  python3 imp-ledger.py story-done <story-id>
  python3 imp-ledger.py story-blocked <story-id> <reason>
  python3 imp-ledger.py story-unblock <story-id|all>
  python3 imp-ledger.py set-step <story-id> <step>
  python3 imp-ledger.py get-attempts <story-id> <step>
  python3 imp-ledger.py get-config <key>
  python3 imp-ledger.py check-sprint-status <story-id>
  python3 imp-ledger.py epic-done <epic-id>
  python3 imp-ledger.py global-status
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

LEDGER_PATH = os.environ.get(
    "IMP_LEDGER",
    os.path.join(PROJECT_ROOT, "_imp/ledger.json"),
)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "_imp/config.yaml")

PIPELINE_STEPS = ["spec", "dev", "review"]

# ---------------------------------------------------------------------------
# Config loading (simple key: value parser — no PyYAML needed)
# ---------------------------------------------------------------------------

def load_config():
    defaults = {
        "model_spec": "claude-sonnet-4-6",
        "effort_spec": "medium",
        "model_dev": "claude-sonnet-4-6",
        "effort_dev": "high",
        "model_review": "claude-opus-4-6",
        "effort_review": "high",
        "max_review_attempts": "3",
        "mind_file": "_mind/mind.md",
        "sprint_status": "_bmad-output/implementation-artifacts/sprint-status.yaml",
        "artifacts_dir": "_bmad-output/implementation-artifacts",
    }
    if not os.path.exists(CONFIG_PATH):
        return defaults
    with open(CONFIG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                val = val.strip()
                # Strip inline YAML comments (e.g. "value # note")
                if " #" in val:
                    val = val[:val.index(" #")].strip()
                defaults[key.strip()] = val
    return defaults


CONFIG = load_config()

# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_ledger():
    if not os.path.exists(LEDGER_PATH):
        return None
    with open(LEDGER_PATH) as f:
        return json.load(f)


def write_ledger(data):
    data["updated"] = _now()
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    with open(LEDGER_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Sprint-status.yaml parser (no PyYAML — handles the flat BMAD format)
# ---------------------------------------------------------------------------

def parse_sprint_status(path):
    """
    Returns (metadata, dev_status) where dev_status is dict[key -> status_str].
    The file format is:
        project: foo
        development_status:
          epic-1: backlog
          1-1-user-auth: backlog
    """
    metadata = {}
    dev_status = {}
    in_dev = False

    with open(path) as f:
        for line in f:
            raw = line.rstrip("\n")
            stripped = raw.strip()

            if not stripped or stripped.startswith("#"):
                continue

            if stripped == "development_status:":
                in_dev = True
                continue

            if in_dev:
                # Any non-indented non-empty line ends the block
                if raw and not raw[0].isspace():
                    in_dev = False
                else:
                    if ":" in stripped:
                        k, _, v = stripped.partition(":")
                        dev_status[k.strip()] = v.strip()
                    continue

            if not in_dev and ":" in stripped:
                k, _, v = stripped.partition(":")
                metadata[k.strip()] = v.strip().strip('"\'')

    return metadata, dev_status


def _epic_num_from_story(story_key):
    """'1-2-user-auth' → 'epic-1'"""
    m = re.match(r"^(\d+)-", story_key)
    return f"epic-{m.group(1)}" if m else None


def _is_epic_key(key):
    return bool(re.match(r"^epic-\d+$", key))


def _is_retro_key(key):
    return "retrospective" in key


def _initial_step_state():
    return {step: {"status": "pending", "attempts": 0} for step in PIPELINE_STEPS}


def _story_status_from_sprint(sprint_val):
    """Map BMAD status → ledger status for a story."""
    done_vals = {"done", "review"}  # treat 'review' as needing review step
    if sprint_val in ("done",):
        return "done"
    if sprint_val in ("backlog", "ready-for-dev", "in-progress", "review"):
        return "pending"
    return "pending"


def _story_current_step(sprint_val, steps=None):
    """Infer which step to start on based on sprint status."""
    if sprint_val == "done":
        return None  # already done
    if sprint_val == "ready-for-dev":
        return "dev"  # spec already created
    if sprint_val == "in-progress":
        return "dev"
    if sprint_val == "review":
        return "review"
    return "spec"  # backlog → start from scratch


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(sprint_status_path):
    if not os.path.exists(sprint_status_path):
        print(f"ERROR: sprint-status not found: {sprint_status_path}", file=sys.stderr)
        sys.exit(1)

    meta, dev_status = parse_sprint_status(sprint_status_path)
    project = meta.get("project", os.path.basename(PROJECT_ROOT))

    # Group stories under their epics preserving declaration order
    epics_order = []
    epic_stories = {}  # epic_id -> list of story keys in order

    for key, val in dev_status.items():
        if _is_retro_key(key):
            continue
        if _is_epic_key(key):
            if key not in epic_stories:
                epics_order.append(key)
                epic_stories[key] = []
        else:
            epic_id = _epic_num_from_story(key)
            if epic_id:
                if epic_id not in epic_stories:
                    epics_order.append(epic_id)
                    epic_stories[epic_id] = []
                epic_stories[epic_id].append((key, val))

    # Build ledger structure
    epics = []
    for epic_id in epics_order:
        epic_sprint_val = dev_status.get(epic_id, "backlog")
        stories = []
        for story_key, sprint_val in epic_stories.get(epic_id, []):
            story_status = _story_status_from_sprint(sprint_val)
            current_step = _story_current_step(sprint_val)

            # If done, mark all steps done
            if story_status == "done":
                steps = {s: {"status": "done", "attempts": 1} for s in PIPELINE_STEPS}
                current_step = None
            else:
                steps = _initial_step_state()
                # Mark steps before current_step as done
                if current_step in PIPELINE_STEPS:
                    idx = PIPELINE_STEPS.index(current_step)
                    for i in range(idx):
                        steps[PIPELINE_STEPS[i]]["status"] = "done"
                        steps[PIPELINE_STEPS[i]]["attempts"] = 1

            stories.append({
                "id": story_key,
                "status": story_status,
                "current_step": current_step,
                "steps": steps,
                "blocked_reason": None,
            })

        # Epic status
        if epic_sprint_val == "done":
            epic_status = "done"
        elif all(s["status"] == "done" for s in stories):
            epic_status = "done"
        elif any(s["status"] == "in-progress" for s in stories):
            epic_status = "in-progress"
        else:
            epic_status = "pending"

        epics.append({
            "id": epic_id,
            "status": epic_status,
            "stories": stories,
        })

    total_stories = sum(len(e["stories"]) for e in epics)
    done_stories = sum(
        1 for e in epics for s in e["stories"] if s["status"] == "done"
    )

    global_status = "done" if done_stories == total_stories else "ready"

    ledger = {
        "version": 1,
        "project": project,
        "created": _now(),
        "updated": _now(),
        "global_status": global_status,
        "config": {
            "model_spec": CONFIG["model_spec"],
            "effort_spec": CONFIG["effort_spec"],
            "model_dev": CONFIG["model_dev"],
            "effort_dev": CONFIG["effort_dev"],
            "model_review": CONFIG["model_review"],
            "effort_review": CONFIG["effort_review"],
            "max_review_attempts": int(CONFIG["max_review_attempts"]),
            "mind_file": CONFIG["mind_file"],
            "artifacts_dir": CONFIG["artifacts_dir"],
        },
        "epics": epics,
    }

    write_ledger(ledger)
    print(f"✓ Ledger initialized — {len(epics)} epics, {total_stories} stories ({done_stories} already done)")
    print(f"  Written to: {LEDGER_PATH}")


def cmd_status():
    ledger = read_ledger()
    if not ledger:
        print("No ledger found. Run: python3 imp-ledger.py init <sprint-status-path>")
        return

    print(f"\nIMP — {ledger.get('project', 'unknown')}")
    print("━" * 44)

    total_epics = len(ledger["epics"])
    done_epics = sum(1 for e in ledger["epics"] if e["status"] == "done")
    blocked_epics = sum(1 for e in ledger["epics"] if e["status"] == "blocked")

    print(f"Epics:  {done_epics}/{total_epics} done  {blocked_epics} blocked")
    print()

    for epic in ledger["epics"]:
        stories = epic["stories"]
        done_s = sum(1 for s in stories if s["status"] == "done")
        blocked_s = sum(1 for s in stories if s["status"] == "blocked")
        in_prog = [s for s in stories if s["status"] == "in-progress"]

        icon = {"done": "✓", "blocked": "⚠", "in-progress": "▶", "pending": "○"}.get(
            epic["status"], "○"
        )
        print(f"  {icon} {epic['id']:<12} {done_s}/{len(stories)} stories", end="")
        if blocked_s:
            print(f"  {blocked_s} blocked", end="")
        if in_prog:
            s = in_prog[0]
            step = s.get("current_step", "?")
            attempts = s["steps"].get(step, {}).get("attempts", 0) if step else 0
            print(f"  → {s['id']} [{step}#{attempts}]", end="")
        print()

    print("━" * 44)
    print(f"Global: {ledger.get('global_status', '?')}")
    print(f"Updated: {ledger.get('updated', '?')}\n")


def _find_story(ledger, story_id):
    for epic in ledger["epics"]:
        for story in epic["stories"]:
            if story["id"] == story_id:
                return epic, story
    return None, None


def cmd_next_story(epic_id="all"):
    ledger = read_ledger()
    if not ledger:
        print("null")
        return

    epics = ledger["epics"]
    if epic_id != "all":
        epics = [e for e in epics if e["id"] == epic_id]

    for epic in epics:
        if epic["status"] in ("done", "blocked"):
            continue
        for story in epic["stories"]:
            if story["status"] in ("done", "blocked"):
                continue
            print(json.dumps({
                "id": story["id"],
                "epic_id": epic["id"],
                "status": story["status"],
                "current_step": story["current_step"],
                "steps": story["steps"],
            }))
            return

    print("null")


def cmd_step_done(story_id, step, session_id=None, log_path=None):
    ledger = read_ledger()
    epic, story = _find_story(ledger, story_id)
    if not story:
        print(f"ERROR: story {story_id} not found", file=sys.stderr)
        sys.exit(1)

    story["steps"][step]["status"] = "done"
    if session_id:
        story["steps"][step]["session"] = session_id
    if log_path:
        story["steps"][step]["log"] = log_path
    story["status"] = "in-progress"

    # Advance current_step
    idx = PIPELINE_STEPS.index(step)
    next_idx = idx + 1
    if next_idx < len(PIPELINE_STEPS):
        story["current_step"] = PIPELINE_STEPS[next_idx]
    else:
        # All steps done — story complete
        story["current_step"] = None
        story["status"] = "done"
        # Check if epic is done
        if all(s["status"] == "done" for s in epic["stories"]):
            epic["status"] = "done"

    write_ledger(ledger)


def cmd_step_attempt(story_id, step):
    ledger = read_ledger()
    epic, story = _find_story(ledger, story_id)
    if not story:
        print(f"ERROR: story {story_id} not found", file=sys.stderr)
        sys.exit(1)

    story["steps"][step]["attempts"] += 1
    story["steps"][step]["status"] = "in-progress"
    story["status"] = "in-progress"
    story["current_step"] = step
    write_ledger(ledger)


def cmd_step_interrupted(story_id, step):
    """Roll back an interrupted step — reset status, undo attempt increment."""
    ledger = read_ledger()
    if not ledger:
        return
    epic, story = _find_story(ledger, story_id)
    if not story:
        return
    step_data = story["steps"].get(step)
    if not step_data or step_data["status"] != "in-progress":
        return
    step_data["status"] = "pending"
    step_data["attempts"] = max(0, step_data["attempts"] - 1)
    story["status"] = "in-progress"
    write_ledger(ledger)


def cmd_story_done(story_id):
    ledger = read_ledger()
    epic, story = _find_story(ledger, story_id)
    if not story:
        sys.exit(1)

    story["status"] = "done"
    story["current_step"] = None
    for step in PIPELINE_STEPS:
        if story["steps"][step]["status"] != "done":
            story["steps"][step]["status"] = "done"

    if all(s["status"] == "done" for s in epic["stories"]):
        epic["status"] = "done"

    all_done = all(e["status"] == "done" for e in ledger["epics"])
    if all_done:
        ledger["global_status"] = "done"

    write_ledger(ledger)


def cmd_story_blocked(story_id, reason):
    ledger = read_ledger()
    epic, story = _find_story(ledger, story_id)
    if not story:
        sys.exit(1)

    story["status"] = "blocked"
    story["blocked_reason"] = reason
    epic["status"] = "blocked"
    ledger["global_status"] = "blocked"
    write_ledger(ledger)
    print(f"BLOCKED: {story_id} — {reason}")


def cmd_story_unblock(story_id_or_all):
    """Reset blocked story/stories back to spec/pending so the runner can retry them."""
    ledger = read_ledger()
    if not ledger:
        print("No ledger found.", file=sys.stderr)
        sys.exit(1)

    def _reset_story(story):
        story["status"] = "pending"
        story["blocked_reason"] = None
        story["current_step"] = "spec"
        story["steps"] = _initial_step_state()

    count = 0
    if story_id_or_all == "all":
        for epic in ledger["epics"]:
            for story in epic["stories"]:
                if story["status"] == "blocked":
                    _reset_story(story)
                    count += 1
            # Recompute epic status
            if epic["status"] == "blocked":
                non_done = [s for s in epic["stories"] if s["status"] != "done"]
                epic["status"] = "pending" if non_done else "done"
    else:
        epic, story = _find_story(ledger, story_id_or_all)
        if not story:
            print(f"ERROR: story {story_id_or_all} not found", file=sys.stderr)
            sys.exit(1)
        if story["status"] != "blocked":
            print(f"Story {story_id_or_all} is not blocked (status={story['status']})")
            return
        _reset_story(story)
        if epic["status"] == "blocked":
            epic["status"] = "pending"
        count = 1

    # Recompute global status
    all_done = all(e["status"] == "done" for e in ledger["epics"])
    any_blocked = any(e["status"] == "blocked" for e in ledger["epics"])
    ledger["global_status"] = "done" if all_done else ("blocked" if any_blocked else "ready")

    write_ledger(ledger)
    noun = "story" if count == 1 else "stories"
    print(f"✓ Unblocked {count} {noun} — global status: {ledger['global_status']}")


def cmd_set_step(story_id, step):
    """Force a story back to a specific step (e.g. back to dev after failed review)."""
    ledger = read_ledger()
    epic, story = _find_story(ledger, story_id)
    if not story:
        sys.exit(1)

    story["current_step"] = step
    story["status"] = "in-progress"
    story["blocked_reason"] = None
    story["steps"][step]["status"] = "pending"
    # Clear epic/global blocked status if this was the only blocked story
    if epic["status"] == "blocked":
        epic["status"] = "in-progress"
    if ledger["global_status"] == "blocked":
        ledger["global_status"] = "in-progress"
    write_ledger(ledger)


def cmd_get_attempts(story_id, step):
    ledger = read_ledger()
    _, story = _find_story(ledger, story_id)
    if not story:
        print("0")
        return
    print(story["steps"].get(step, {}).get("attempts", 0))


def cmd_get_config(key):
    val = CONFIG.get(key, "")
    # Also check ledger config for runtime overrides
    ledger = read_ledger()
    if ledger and key in ledger.get("config", {}):
        val = ledger["config"][key]
    print(val)


def cmd_epic_done(epic_id):
    ledger = read_ledger()
    for epic in ledger["epics"]:
        if epic["id"] == epic_id:
            epic["status"] = "done"
            break
    if all(e["status"] == "done" for e in ledger["epics"]):
        ledger["global_status"] = "done"
    write_ledger(ledger)


def cmd_check_sprint_status(story_id):
    """Read sprint-status.yaml and return the current status for a story."""
    sprint_path = os.path.join(PROJECT_ROOT, CONFIG.get("sprint_status", ""))
    if not os.path.exists(sprint_path):
        print("unknown")
        return

    _, dev_status = parse_sprint_status(sprint_path)

    # Try exact match first, then partial match on the story_id prefix
    if story_id in dev_status:
        print(dev_status[story_id])
        return

    # Partial match: story_id might be "1-1-auth" but key is "1-1-user-authentication"
    for key, val in dev_status.items():
        if key.startswith(story_id):
            print(val)
            return

    print("unknown")


def cmd_global_status():
    ledger = read_ledger()
    if not ledger:
        print("not-initialized")
        return
    print(ledger.get("global_status", "unknown"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]

    if cmd == "init":
        if len(args) < 2:
            print("Usage: imp-ledger.py init <sprint-status-path>", file=sys.stderr)
            sys.exit(1)
        cmd_init(args[1])

    elif cmd == "status":
        cmd_status()

    elif cmd == "next-story":
        epic_id = args[1] if len(args) > 1 else "all"
        cmd_next_story(epic_id)

    elif cmd == "step-done":
        cmd_step_done(args[1], args[2])

    elif cmd == "step-attempt":
        cmd_step_attempt(args[1], args[2])

    elif cmd == "step-interrupted":
        cmd_step_interrupted(args[1], args[2])

    elif cmd == "story-done":
        cmd_story_done(args[1])

    elif cmd == "story-blocked":
        reason = " ".join(args[2:]) if len(args) > 2 else "unknown"
        cmd_story_blocked(args[1], reason)

    elif cmd == "story-unblock":
        if len(args) < 2:
            print("Usage: imp-ledger.py story-unblock <story-id|all>", file=sys.stderr)
            sys.exit(1)
        cmd_story_unblock(args[1])

    elif cmd == "set-step":
        cmd_set_step(args[1], args[2])

    elif cmd == "get-attempts":
        cmd_get_attempts(args[1], args[2])

    elif cmd == "get-config":
        cmd_get_config(args[1])

    elif cmd == "epic-done":
        cmd_epic_done(args[1])

    elif cmd == "check-sprint-status":
        cmd_check_sprint_status(args[1])

    elif cmd == "global-status":
        cmd_global_status()

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
