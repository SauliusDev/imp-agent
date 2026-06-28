#!/usr/bin/env bash
# IMP Agent installer bootstrapper.
# Run from your project root: curl -fsSL https://raw.githubusercontent.com/SauliusDev/imp-agent/main/setup.sh | bash

set -euo pipefail

IMP_REPO="https://github.com/SauliusDev/imp-agent"
IMP_TMP="/tmp/imp-agent-install"
IMP_AGENT_PROVIDER="${IMP_AGENT_PROVIDER:-claude}"

# ── 1. Python 3.10+ ──────────────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
  echo "" >&2
  echo "✗ python3 not found." >&2
  echo "" >&2
  echo "  Install Python 3.10+: https://python.org" >&2
  exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "" >&2
  echo "✗ Python 3.10+ required (found $PY_VERSION)" >&2
  echo "" >&2
  echo "  Install Python 3.10+: https://python.org" >&2
  exit 1
fi

# ── 2. rich ──────────────────────────────────────────────────────────────────

if ! python3 -c "import rich" 2>/dev/null; then
  echo "Missing dependency: rich"
  echo ""
  read -rp "Install it now? (pip install rich) [Y/n] " answer
  answer="${answer:-Y}"
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    pip3 install --break-system-packages rich 2>/dev/null || pip3 install rich
  else
    echo "" >&2
    echo "Aborted. Install rich manually: pip3 install rich" >&2
    exit 1
  fi
fi

# ── 3. BMAD check ────────────────────────────────────────────────────────────

if [ "$IMP_AGENT_PROVIDER" = "codex" ]; then
  BMAD_SKILLS_DIR=".agents/skills"
  BMAD_INSTALL_HINT="npx bmad-method@latest install --tools codex --directory $(pwd)"
else
  BMAD_SKILLS_DIR=".claude/skills"
  BMAD_INSTALL_HINT="npx bmad-method@latest install --tools claude-code --directory $(pwd)"
fi

if [ ! -d "$BMAD_SKILLS_DIR/bmad-dev-story" ]; then
  echo "" >&2
  echo "✗ BMAD not found in $BMAD_SKILLS_DIR/" >&2
  echo "" >&2
  echo "  IMP requires BMAD to run. Set up BMAD for $IMP_AGENT_PROVIDER first:" >&2
  echo "  $BMAD_INSTALL_HINT" >&2
  echo "  → https://github.com/SauliusDev/bmad-method" >&2
  echo "" >&2
  echo "  Then re-run this installer." >&2
  exit 1
fi

# ── 4. Clone or update imp-agent repo ────────────────────────────────────────

if [ -d "$IMP_TMP/.git" ]; then
  echo "Updating IMP installer..."
  git -C "$IMP_TMP" pull --rebase --quiet
else
  echo "Fetching IMP installer..."
  rm -rf "$IMP_TMP"
  git clone --quiet "$IMP_REPO" "$IMP_TMP"
fi

# ── 5. Hand off to Python installer ──────────────────────────────────────────

exec python3 "$IMP_TMP/install.py" --project-dir "$(pwd)" --agent-provider "$IMP_AGENT_PROVIDER"
