"""Read Claude Code's rate limit cache and check usage thresholds."""

import json
import os
import subprocess
import time
from typing import Optional, Tuple

DEFAULT_CACHE_PATH = "/tmp/claude-rate-limits.json"
CHECK_LIMITS_SCRIPT = os.path.expanduser("~/.claude/check-limits.sh")
STALE_THRESHOLD_S = 2 * 3600  # 2 hours


def read_usage_cache(
    path: str = DEFAULT_CACHE_PATH,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Read the rate-limit cache file.

    Returns (usage_5h, usage_7d, file_mtime).
    Returns (None, None, None) if file is missing, corrupt, or has no rate_limits data.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return (None, None, None)

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return (None, None, None)

    rate_limits = data.get("rate_limits") if isinstance(data, dict) else None
    if rate_limits is None:
        return (None, None, mtime)

    five_hour = rate_limits.get("five_hour") or {}
    seven_day = rate_limits.get("seven_day") or {}

    usage_5h = five_hour.get("used_percentage")
    usage_7d = seven_day.get("used_percentage")

    return (usage_5h, usage_7d, mtime)


def is_stale(mtime: Optional[float]) -> bool:
    """Return True if mtime is None or older than STALE_THRESHOLD_S."""
    if mtime is None:
        return True
    return (time.time() - mtime) > STALE_THRESHOLD_S


def check_threshold(usage_5h: Optional[float], threshold: int) -> bool:
    """Return True if usage_5h >= threshold and threshold > 0."""
    if usage_5h is None or threshold <= 0:
        return False
    return usage_5h >= threshold


def fetch_full_usage() -> Optional[dict]:
    """Call check-limits.sh and return parsed JSON, or None on failure.

    Returns keys: five_hour_pct, seven_day_pct, sonnet_pct, extra_pct,
    extra_spent_eur, extra_limit_eur, five_hour_resets, seven_day_resets,
    decision, cache_age_sec.
    """
    if not os.path.isfile(CHECK_LIMITS_SCRIPT):
        return None
    try:
        result = subprocess.run(
            ["bash", CHECK_LIMITS_SCRIPT],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError, ValueError):
        return None
