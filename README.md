<p align="center">
  <img src="banner.md.png" alt="IMP Agent — Autonomous loop engine for BMAD" width="720">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&labelColor=1a1a2e" alt="Python 3.10+">
  &nbsp;
  <img src="https://img.shields.io/badge/Claude%20Code%20%7C%20Codex-supported-orange?style=flat-square&labelColor=1a1a2e" alt="Claude Code | Codex supported">
  &nbsp;
  <img src="https://img.shields.io/badge/install-curl-purple?style=flat-square&labelColor=1a1a2e" alt="curl install">
  &nbsp;
  <img src="https://img.shields.io/badge/License-AGPL%20v3-green?style=flat-square&labelColor=1a1a2e" alt="License AGPL v3">
</p>

---

## What is IMP Agent?

`imp` is an autonomous pipeline engine for [BMAD](https://github.com/bmad-method/bmad-method). It drives `/bmad-create-story`, `/bmad-dev-story`, and `/bmad-code-review` in a continuous loop over your sprint stories — with a Rich TUI, a persistent ledger, per-story usage gates, and keyboard controls.

I built it because running BMAD stories by hand means babysitting a terminal. You kick off a story, wait, check it, kick off the next one. IMP does that loop for you. It runs until the sprint is done, pauses where you tell it to, and stays out of the way in between.

Both **Claude Code** and **Codex CLI** are supported.

![IMP Agent terminal demo](demo.png)

## Install

Run from your project root (BMAD must already be set up):

```bash
curl -fsSL https://raw.githubusercontent.com/SauliusDev/imp-agent/main/setup.sh | bash
```

For Codex projects:

```bash
npx bmad-method@latest install --tools codex --directory .
curl -fsSL https://raw.githubusercontent.com/SauliusDev/imp-agent/main/setup.sh | IMP_AGENT_PROVIDER=codex bash
```

## Prerequisites

- **BMAD** set up in the project — Claude: `.claude/skills/bmad-dev-story/` · Codex: `.agents/skills/bmad-dev-story/`
- **Python 3.10+**
- **Claude Code CLI** (`claude` on PATH) or **Codex CLI** (`codex` on PATH)
- **`rich`** Python package (installer offers to install it)

## What gets installed

| Path | Description |
|---|---|
| `_imp/` | IMP engine (7 Python files + shell launcher) |
| `.claude/skills/imp-init/` | Skill to initialize the ledger (Claude) |
| `.agents/skills/imp-init/` | Skill to initialize the ledger (Codex) |
| `_imp/config.yaml` | Pipeline config — edit before first run |

## Getting started

1. **Edit `_imp/config.yaml`** — set `agent_provider`, models, usage caps, pause points
2. **Run `/bmad-sprint-planning`** — generates `sprint-status.yaml`
3. **Run `/imp-init`** — initializes the ledger from `sprint-status.yaml`
4. **Run `bash _imp/imp.sh all`** — starts the pipeline

For Codex, update `config.yaml`:

```yaml
agent_provider: codex
model_spec: gpt-5.5
model_dev: gpt-5.5
model_review: gpt-5.5
codex_usage_source: auto  # app_server|quota_cache|off also supported
base_limit_pct: 90        # optional 5h cap
limit_7d_pct: 80          # optional weekly cap
```

Codex usage caps are best-effort. IMP can read subscription quota from
`codex app-server` or from `~/.codex/multi-auth/quota-cache.json`; `auto`
chooses the smoother source for the current Codex runtime.

## Usage

```bash
bash _imp/imp.sh all        # run all epics
bash _imp/imp.sh epic-1     # run a single epic
bash _imp/imp.sh --help
```

Keyboard shortcuts while running:

| Key | Action |
|-----|--------|
| `p` | Pause / resume |
| `l` | Toggle story output |
| `r` | Reload config |
| `q` | Quit |

## Re-installing / updating

Re-run the same `curl` command. Engine files are always overwritten. Your `_imp/config.yaml` and `_imp/ledger.json` are preserved.

## Working principle

IMP has three phases: **init**, **loop**, and **gate checks** between every step.

```mermaid
%%{init: {'theme': 'default', 'flowchart': {'curve': 'basis'}}}%%
flowchart TD
    A([sprint-status.yaml]) -->|imp-init skill| B[(ledger.json)]
    B --> C[imp.sh all]
    C --> D{next story?}
    D -->|none left| Z([done])
    D -->|yes| E[bmad-create-story\nspec step]
    E --> G1{usage cap?}
    G1 -->|over limit| P1([pause / quit])
    G1 -->|ok| F[bmad-dev-story\ndev step]
    F --> G2{usage cap?}
    G2 -->|over limit| P2([pause / quit])
    G2 -->|ok| G[bmad-code-review\nreview step]
    G --> H{pass?}
    H -->|fail| I[requeue to\nprior step]
    I --> F
    H -->|pass| J[mark done\nin ledger]
    J --> K{pause\nconfigured?}
    K -->|yes| L([operator gate])
    K -->|no| D
```

**Three threads run concurrently:**

```mermaid
%%{init: {'theme': 'default'}}%%
flowchart LR
    subgraph threads["three threads"]
        T1[pipeline\norchestrator]
        T2[keypress\nreader]
        T3[usage\npoller]
    end
    T1 <-->|shared state| T2
    T1 <-->|cap signals| T3
```

The pipeline thread spawns each BMAD skill as a subprocess and streams output to the Rich TUI. The keypress thread reads raw TTY so `p / l / r / q` work at any point. The usage poller samples Claude's 5h/7d consumption and signals the pipeline to pause or quit when caps are hit.

Every step result is written to `ledger.json` immediately — kill the process any time and restart from the exact same story and step.
