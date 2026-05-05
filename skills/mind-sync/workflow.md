# mind-sync workflow

## Goal
Update `_mind/mind.md` with the latest project knowledge.
**Rule: merge and compress — never append. Output must be same size or smaller than current mind.md.**

---

## Step 1: Read current state

First, ensure the mind directory and files exist. If `_mind/` does not exist, create it.

If `_mind/mind.md` does not exist, create it with this default content:
```
# Project Mind — {project-name}
_Updated: {today} | Syncs: 0_

## Current State
Project just initialized.

## Active Work
(none yet)

## Lessons Learned
(none yet)

## Key Decisions
(none yet)

## Journey
(none yet)
```

If `_mind/index.yaml` does not exist, create it with this default content:
```yaml
project: {project-name}
last_sync: "{today}T00:00:00"
sync_count: 0
watch_patterns:
  - _bmad-output
transcript_sources: []
tracked_files: []
```

Ensure `_mind/logs/` exists (create if missing).

Then read both files:
- `_mind/mind.md`
- `_mind/index.yaml`

Note the current `sync_count` and `tracked_files` hashes.

**Important:** Store the full current content of `_mind/mind.md` as `old_content` before any changes. You will need it in Step 6 to produce the diff log.

---

## Step 2: Discover changed files

Run:
```bash
find _bmad-output -name "*.md" -o -name "*.yaml" 2>/dev/null | sort
```

For each file found, compute its hash:
```bash
md5 -q {filepath} 2>/dev/null || md5sum {filepath} | cut -d' ' -f1
```

Compare each hash against `tracked_files[].last_hash` in index.yaml.
Collect as `changed_files`: files where hash differs OR file is not yet in index.yaml.

If no changed files and `TRANSCRIPT_PATH` is not set → print `✓ mind.md already up to date` and stop.

---

## Step 3: Read changed content

Read each file in `changed_files` fully.

---

## Step 4: Read transcript context

Check if env var `TRANSCRIPT_PATH` is set (hook-triggered mode):
- If set: read the last 150 lines of that file — extract key decisions, errors encountered, and outcomes from assistant messages
- If not set (manual mode): summarize the current conversation context — what was discussed, decided, built, or learned

---

## Step 5: Synthesize updated mind.md
  
Using all gathered context, produce a new mind.md. Follow this schema exactly:

```
# Project Mind — {project-name}
_Updated: {YYYY-MM-DD} | Syncs: {sync_count + 1}_

## Current State
2-3 sentences. Where is the project right now? What was just completed or started?

## Active Work
- {Epic / Story / Task name} — {status}: {next concrete action}

## Lessons Learned
- ✓ {what worked, with brief context}
- ✗ {what failed or should be avoided, with brief context}

## Key Decisions
- {decision made} — {reason / tradeoff}

## Journey
Compressed narrative. What happened in what order, major pivots, milestones reached.
Old entries get compressed (1 line each). Recent entries get 2-3 lines.
```

**Synthesis rules:**
- Total token budget: match current mind.md line count ± 20% — do NOT grow unboundedly
- If new info doesn't fit: compress oldest Journey entries first
- Only keep decisions that are still relevant (drop superseded ones)
- Merge repeated lessons — don't list the same lesson twice
- Mark active work as completed/dropped if evidence shows it's done
- Write in dense, LLM-readable prose — not for humans, for future AI context injection

---

## Step 6: Write files

**Write 1:** Updated mind.md to `_mind/mind.md`

**Write 2:** Updated index.yaml to `_mind/index.yaml` with:
- `last_sync`: current ISO datetime (e.g. `"2026-04-02T14:30:00"`)
- `sync_count`: previous value + 1
- `tracked_files`: array updated with hash + timestamp for every file processed
  ```yaml
  tracked_files:
    - path: _bmad-output/planning-artifacts/epic-01.md
      last_hash: abc123def456
      last_read: "2026-04-02T14:30:00"
  ```
- `transcript_sources`: append transcript path if used (deduplicated)

---

**Write 3:** Diff log to `_mind/logs/sync-{sync_count+1}.md`

Compare `old_content` (captured in Step 1) against the new mind.md line by line. Write the file in this exact format:

```
sync: {sync_count+1} | {ISO datetime}
lines before: {N} | lines after: {M}

+ {any line that is new or changed in the new version}
- {any line that was in old_content but is absent or changed in the new version}
```

Rules for the diff:
- One `+` or `-` per changed line — no context lines, no section headers, no prose
- Blank lines and the header line (`# Project Mind`) are ignored — don't include them in the diff
- If a line was reworded (not just moved), show the old as `-` and the new as `+`
- If nothing changed, write `(no changes)` after the header

---

## Step 7: Confirm

Print a single summary line:
```
✓ mind-sync complete — {N} files synced, {M} lines in mind.md, sync #{sync_count}
```
