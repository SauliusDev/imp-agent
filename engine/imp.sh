#!/usr/bin/env bash
# imp — IMP Runner TUI launcher
#
# Usage:
#   ./imp [options] <epic-id|all>
#   ./imp epic-1
#   ./imp -v all
#   ./imp --help
#
# Checks for Python 3.10+ and the 'rich' package before launching.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/imp_runner.py"

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

# 1. Python 3.10+
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found. Install Python 3.10+ first." >&2
  exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "Error: Python 3.10+ required (found $PY_VERSION)" >&2
  exit 1
fi

# 2. rich package
if ! python3 -c "import rich" 2>/dev/null; then
  echo "Missing dependency: rich"
  echo ""
  read -rp "Install it now? (pip install rich) [Y/n] " answer
  answer="${answer:-Y}"
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    pip3 install --break-system-packages rich || pip3 install rich
  else
    echo "Aborted. Install rich manually: pip3 install rich" >&2
    exit 1
  fi
fi

# 3. Ledger exists (not required for log-sync)
FIRST_POS_ARG=""
for _arg in "$@"; do
  case "$_arg" in -*) ;; *) FIRST_POS_ARG="$_arg"; break ;; esac
done
if [ "$FIRST_POS_ARG" != "log-sync" ] && [ ! -f "$SCRIPT_DIR/ledger.json" ]; then
  echo "Error: No ledger found at $SCRIPT_DIR/ledger.json" >&2
  echo "Run /imp-init first." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
exec python3 "$RUNNER" "$@"
