"""Per-user settings store backed by a JSON file in %LOCALAPPDATA%\\CAPEView.

Settings file: ``%LOCALAPPDATA%\\CAPEView\\settings.json``
Override via env var ``CAPEVIEW_SETTINGS_PATH`` (used by tests).

The settings dict is shallow — keep it that way. Add new keys directly:

    settings = SettingsManager()
    settings.get("database.path")
    settings.set("database.path", r"\\\\share\\cape.db")
    settings.save()

Resolution priority for the database path is implemented in
``cape_database.resolve_db_path``:
    1. ``CAPEVIEW_DB_PATH`` env var (highest, for tests/CI)
    2. ``database.path`` from this settings file
    3. ``\\\\192.168.115.99\\scans\\Dev\\CAPEView\\Database\\cape.db`` if the share is reachable
    4. ``%LOCALAPPDATA%\\CAPEView\\cape.db`` (final local fallback)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS_PATH = Path.home() / "AppData" / "Local" / "CAPEView" / "settings.json"


def settings_path() -> Path:
    env = os.environ.get("CAPEVIEW_SETTINGS_PATH")
    return Path(env) if env else DEFAULT_SETTINGS_PATH


class SettingsManager:
    """Thin JSON-file wrapper. Loads on construction, saves on demand."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else settings_path()
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if value is None or value == "":
            self._data.pop(key, None)
        else:
            self._data[key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def all(self) -> dict[str, Any]:
        """Return a shallow copy of the settings dict."""
        return dict(self._data)

    def reload(self) -> None:
        self._data = self._load()
