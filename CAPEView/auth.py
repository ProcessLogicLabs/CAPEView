"""Authentication & authorization for CAPEView.

Identity is captured passively from the Windows session (USERDOMAIN /
USERNAME env vars; falls back to getpass.getuser). No login prompt — every
DMUSA user is already Kerberos-authenticated by Windows when they log in.

Authorization is gated by an ``auth_users.json`` allowlist that the CAPEView
admin maintains. The file lives on the shared CAPEView folder so it is the
single source of truth for everyone on the LAN — independent of where
each user's local cape.db sits.

File format::

    {
      "users":  ["DMUSA\\\\hpayne", "DMUSA\\\\rbloggs"],
      "admins": ["DMUSA\\\\hpayne"]
    }

Bootstrap mode: if the file does not exist OR the ``admins`` list is empty,
all users are treated as authorized AND admin so that a fresh install can be
locked down from the in-app admin dialog (Ctrl+Shift+A) on first launch.
Once at least one admin is set, the gate takes effect.

Resolution priority for the allowlist path:
    1. ``CAPEVIEW_AUTH_PATH`` env var (highest, for tests / emergencies)
    2. Shared share default if reachable
    3. Same path even if unreachable — load() degrades to bootstrap mode
       so a missing share doesn't lock everyone out cold

Emergency override:
    Set ``CAPEVIEW_AUTH_BYPASS=1`` to skip the gate entirely. The user is
    still recorded for audit_log; this is meant for off-network debugging.
"""

from __future__ import annotations

import getpass
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

SHARED_AUTH_PATH = r"\\192.168.115.99\scans\Dev\CAPEView\Database\auth_users.json"


@dataclass
class AuthConfig:
    """In-memory representation of auth_users.json."""
    users: list[str] = field(default_factory=list)
    admins: list[str] = field(default_factory=list)


def current_user() -> str:
    """Return ``DOMAIN\\username`` from the Windows session.

    Falls back to a bare username on non-domain machines or non-Windows
    environments (mainly relevant in tests and CI).
    """
    domain = os.environ.get("USERDOMAIN", "").strip()
    name = (os.environ.get("USERNAME", "") or "").strip()
    if not name:
        try:
            name = getpass.getuser()
        except Exception:
            name = "local"
    if domain and name:
        return f"{domain}\\{name}"
    return name or "local"


def auth_path() -> Path:
    """Resolved allowlist path. Env var wins for tests / emergencies."""
    env = os.environ.get("CAPEVIEW_AUTH_PATH")
    if env:
        return Path(env)
    return Path(SHARED_AUTH_PATH)


def load() -> AuthConfig:
    """Read the allowlist. Missing / unreachable / malformed → empty config
    (which puts the app in bootstrap mode — see ``is_bootstrap_mode``)."""
    p = auth_path()
    try:
        if not p.exists():
            return AuthConfig()
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AuthConfig()
    if not isinstance(data, dict):
        return AuthConfig()
    return AuthConfig(
        users=_clean_list(data.get("users")),
        admins=_clean_list(data.get("admins")),
    )


def _clean_list(items) -> list[str]:
    """Filter to non-empty strings; reject None/numbers/other types."""
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, str) and x.strip()]


def save(cfg: AuthConfig) -> None:
    """Write the allowlist to disk. Caller is responsible for validation
    (non-empty admins, current user in users) — this function is dumb."""
    p = auth_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"users": list(cfg.users), "admins": list(cfg.admins)}
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _norm(s: str) -> str:
    return s.strip().lower()


def _bypass() -> bool:
    return os.environ.get("CAPEVIEW_AUTH_BYPASS", "").strip() == "1"


def is_bootstrap_mode(cfg: AuthConfig) -> bool:
    """No admins on file → first-run / unconfigured → everyone is admin."""
    return not cfg.admins


def is_authorized(user: str, cfg: AuthConfig) -> bool:
    if _bypass():
        return True
    if is_bootstrap_mode(cfg):
        return True
    return _norm(user) in {_norm(u) for u in cfg.users}


def is_admin(user: str, cfg: AuthConfig) -> bool:
    if _bypass():
        return True
    if is_bootstrap_mode(cfg):
        return True
    return _norm(user) in {_norm(a) for a in cfg.admins}
