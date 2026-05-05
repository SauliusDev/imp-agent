---
name: imp-init
description: Initialize the IMP ledger from sprint-status.yaml. Parses all epics and stories, creates _imp/ledger.json with step-level tracking state. Run once before first imp-run.sh, or to reinitialize.
---

# IMP Ledger Initialization

Initializes `_imp/ledger.json` from the project's BMAD sprint-status file.

## Steps

### 1. Locate sprint-status.yaml

Search for the sprint-status file:
```bash
find _bmad-output -name "sprint-status.yaml" 2>/dev/null | head -1
```

If not found, print:
> **Error:** No sprint-status.yaml found.
> Run `/bmad-sprint-planning` first to generate it, then re-run `/imp-init`.

Stop here if not found.

### 2. Run the ledger initializer

```bash
python3 _imp/imp-ledger.py init <sprint-status-path>
```

Where `<sprint-status-path>` is the path found in step 1.

### 3. Show result

If the command succeeds, run:
```bash
python3 _imp/imp-ledger.py status
```

Print the output verbatim — it shows the epic/story breakdown.

### 4. Confirm ready

Print:
> **Ledger initialized.** Run implementation with:
> ```bash
> bash _imp/imp-run.sh all
> ```
>
> Config: `_imp/config.yaml` — edit to change model, max review attempts, or paths.

## Trigger Phrases

```
/imp-init
initialize imp ledger
init imp
reset imp ledger
```
