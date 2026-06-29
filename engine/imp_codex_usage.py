"""Read Codex subscription quota for live IMP usage caps.

Codex has two useful local surfaces:
- `codex app-server` exposes account/rateLimits/read over JSON-RPC.
- codex-multi-auth maintains a local quota-cache.json with the same 5h/7d
  quota percentages per account.

Both surfaces are best-effort and must fail open; missing quota data should not
block a pipeline run.
"""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


CODEX_HOME = Path(os.path.expanduser(os.environ.get("CODEX_HOME", "~/.codex")))
USER_CODEX_HOME = Path.home() / ".codex"
MULTI_AUTH_DIR = USER_CODEX_HOME / "multi-auth"
QUOTA_CACHE_PATH = MULTI_AUTH_DIR / "quota-cache.json"
ACCOUNTS_PATH = MULTI_AUTH_DIR / "openai-codex-accounts.json"


def _candidate_multi_auth_dirs() -> list[Path]:
    dirs = [USER_CODEX_HOME / "multi-auth", CODEX_HOME / "multi-auth"]
    for parent in (CODEX_HOME, *CODEX_HOME.parents):
        if parent.name == "multi-auth":
            dirs.append(parent)
            break

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in dirs:
        key = str(path)
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def _default_multi_auth_paths() -> tuple[Path, Path]:
    for directory in _candidate_multi_auth_dirs():
        quota = directory / "quota-cache.json"
        accounts = directory / "openai-codex-accounts.json"
        if quota.exists():
            return quota, accounts
    return QUOTA_CACHE_PATH, ACCOUNTS_PATH


def _running_under_multi_auth_shadow() -> bool:
    return "multi-auth" in CODEX_HOME.parts and "runtime-shadow-homes" in CODEX_HOME.parts


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_from_ms(value: Any) -> Optional[str]:
    ms = _num(value)
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reset_value(limit: dict[str, Any]) -> Optional[str]:
    for key in ("resetsAt", "resetAt", "resetAtMs", "resetsAtMs", "reset_at_ms"):
        value = limit.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.isdigit():
            return value
        return _iso_from_ms(value)
    return None


def _window_minutes(limit: dict[str, Any]) -> Optional[int]:
    for key in ("windowMinutes", "windowDurationMins", "windowMins", "window_minutes"):
        value = _num(limit.get(key))
        if value is not None:
            return int(value)
    return None


def _used_percent(limit: dict[str, Any]) -> Optional[float]:
    for key in ("usedPercent", "usedPercentage", "used_percentage", "used"):
        value = _num(limit.get(key))
        if value is not None:
            return value
    return None


def _limits_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    limits = result.get("rateLimits") if isinstance(result.get("rateLimits"), dict) else result
    if not isinstance(limits, dict):
        return {}
    return limits


def _find_limit(limits: dict[str, Any], target_minutes: int, named_key: str) -> dict[str, Any]:
    named = limits.get(named_key)
    if isinstance(named, dict):
        return named

    def iter_candidates(obj: Any) -> list[dict[str, Any]]:
        if not isinstance(obj, (dict, list)):
            return []
        if isinstance(obj, list):
            out: list[dict[str, Any]] = []
            for item in obj:
                out.extend(iter_candidates(item))
            return out
        if _window_minutes(obj) is not None or _used_percent(obj) is not None:
            return [obj]
        out = []
        for value in obj.values():
            out.extend(iter_candidates(value))
        return out

    candidates: list[dict[str, Any]] = []
    for value in limits.values():
        if isinstance(value, dict):
            candidates.extend(iter_candidates(value))
        elif isinstance(value, list):
            candidates.extend(iter_candidates(value))

    for candidate in candidates:
        if _window_minutes(candidate) == target_minutes:
            return candidate
    return {}


def _usage_from_limits(limits: dict[str, Any], source: str) -> Optional[dict]:
    primary = _find_limit(limits, 300, "primary")
    secondary = _find_limit(limits, 10080, "secondary")
    five_h = _used_percent(primary)
    seven_d = _used_percent(secondary)
    if five_h is None and seven_d is None:
        return None
    return {
        "five_hour_pct": five_h,
        "seven_day_pct": seven_d,
        "five_hour_resets": _reset_value(primary),
        "seven_day_resets": _reset_value(secondary),
        "decision": "PROCEED",
        "source": source,
    }


def _usage_from_app_server_payload(payload: dict[str, Any]) -> Optional[dict]:
    return _usage_from_limits(_limits_from_payload(payload), "codex-app-server")


def _active_multi_auth_account_id(accounts_path: Path = ACCOUNTS_PATH) -> Optional[str]:
    try:
        data = json.loads(accounts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    accounts = data.get("accounts")
    active_index = data.get("activeIndex")
    if not isinstance(accounts, list) or not isinstance(active_index, int):
        return None
    if active_index < 0 or active_index >= len(accounts):
        return None
    account = accounts[active_index]
    if not isinstance(account, dict):
        return None
    account_id = account.get("accountId")
    return str(account_id) if account_id else None


def _usage_from_quota_cache(
    payload: dict[str, Any],
    active_account_id: Optional[str] = None,
) -> Optional[dict]:
    by_account = payload.get("byAccountId")
    if not isinstance(by_account, dict):
        return None

    entries = [
        (str(account_id), entry)
        for account_id, entry in by_account.items()
        if isinstance(entry, dict) and entry.get("status") == 200
    ]
    if not entries:
        return None

    selected = None
    if active_account_id:
        selected = next((entry for account_id, entry in entries if account_id == active_account_id), None)
    if selected is None:
        selected = max(entries, key=lambda item: _num(item[1].get("updatedAt")) or 0)[1]

    return _usage_from_limits(selected, "codex-quota-cache")


def fetch_codex_usage_from_app_server(timeout: float = 5.0) -> Optional[dict]:
    """Fetch live Codex quota from app-server JSON-RPC, or None on failure."""
    proc: subprocess.Popen[str] | None = None
    selector: selectors.BaseSelector | None = None
    try:
        proc = subprocess.Popen(
            ["codex", "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(json.dumps({
            "method": "initialize",
            "id": 1,
            "params": {
                "clientInfo": {
                    "name": "imp-agent",
                    "title": "IMP Agent",
                    "version": "1.0",
                }
            },
        }) + "\n")
        proc.stdin.write(json.dumps({"method": "account/rateLimits/read", "id": 2}) + "\n")
        proc.stdin.flush()

        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready = selector.select(max(0, deadline - time.time()))
            if not ready:
                return None
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    return None
                time.sleep(0.05)
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("id") == 2:
                if obj.get("error"):
                    return None
                return _usage_from_app_server_payload(obj)
        return None
    except (OSError, subprocess.SubprocessError, BrokenPipeError, ValueError):
        return None
    finally:
        if selector is not None:
            selector.close()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()


def fetch_codex_usage_from_quota_cache(
    quota_path: Optional[Path] = None,
    accounts_path: Optional[Path] = None,
) -> Optional[dict]:
    """Read codex-multi-auth quota cache, or None when unavailable."""
    if quota_path is None or accounts_path is None:
        default_quota, default_accounts = _default_multi_auth_paths()
        quota_path = quota_path or default_quota
        accounts_path = accounts_path or default_accounts
    try:
        data = json.loads(quota_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return _usage_from_quota_cache(data, _active_multi_auth_account_id(accounts_path))


def fetch_codex_usage(source: str = "auto") -> Optional[dict]:
    """Return Codex quota percentages.

    source:
      - auto: app-server first, quota cache fallback; in codex-multi-auth shadow
        homes, quota cache is tried first to avoid app-server auth mismatch delays
      - app_server: only app-server
      - quota_cache: only local codex-multi-auth quota cache
      - off: disabled
    """
    normalized = str(source or "auto").strip().lower().replace("-", "_")
    if normalized in ("off", "false", "none", "0"):
        return None
    if normalized == "auto" and _running_under_multi_auth_shadow():
        usage = fetch_codex_usage_from_quota_cache()
        if usage is not None:
            return usage
    if normalized in ("auto", "app_server"):
        usage = fetch_codex_usage_from_app_server()
        if usage is not None or normalized == "app_server":
            return usage
    if normalized in ("auto", "quota_cache", "local_quota_cache"):
        return fetch_codex_usage_from_quota_cache()
    return None
