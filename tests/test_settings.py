"""Tests for settings_manager + DB resolution priority + copy helper."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from CAPEView import cape_database as db
from CAPEView.settings_manager import SettingsManager


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Point both settings + DB env-vars at a temp dir."""
    monkeypatch.setenv("CAPEVIEW_SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.delenv("CAPEVIEW_DB_PATH", raising=False)
    return tmp_path


def test_settings_set_get_save_reload(isolated):
    s = SettingsManager()
    assert s.get("database.path") is None
    s.set("database.path", str(isolated / "x.db"))
    assert s.get("database.path") == str(isolated / "x.db")
    s.save()

    # Fresh load picks up persisted value
    s2 = SettingsManager()
    assert s2.get("database.path") == str(isolated / "x.db")


def test_settings_set_none_clears_key(isolated):
    s = SettingsManager()
    s.set("database.path", "x")
    s.set("database.path", None)
    s.save()

    s2 = SettingsManager()
    assert s2.get("database.path") is None
    assert s2.all() == {}


def test_settings_corrupt_file_falls_back(isolated):
    p = Path(isolated) / "settings.json"
    p.write_text("{not valid json", encoding="utf-8")
    s = SettingsManager()
    assert s.all() == {}


def test_settings_purges_deprecated_email_keys_on_load(isolated):
    """Settings written by older versions (email.enabled / email.recipients)
    are stripped on first load and the file is rewritten without them."""
    import json
    p = Path(isolated) / "settings.json"
    p.write_text(json.dumps({
        "database.path": "/some/where.db",
        "email.enabled": True,
        "email.recipients": ["a@b.com"],
    }), encoding="utf-8")

    s = SettingsManager()
    assert s.get("email.enabled") is None
    assert s.get("email.recipients") is None
    assert s.get("database.path") == "/some/where.db"

    # File on disk no longer carries the dead keys
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert "email.enabled" not in on_disk
    assert "email.recipients" not in on_disk
    assert on_disk["database.path"] == "/some/where.db"


def test_resolve_db_path_env_wins(isolated, monkeypatch):
    target = isolated / "from_env.db"
    monkeypatch.setenv("CAPEVIEW_DB_PATH", str(target))
    # Even if settings file says something else, env wins:
    s = SettingsManager()
    s.set("database.path", str(isolated / "from_settings.db"))
    s.save()
    assert db.resolve_db_path() == target


def test_resolve_db_path_settings_overrides_default(isolated):
    target = isolated / "from_settings.db"
    s = SettingsManager()
    s.set("database.path", str(target))
    s.save()
    assert db.resolve_db_path() == target


def test_copy_db_helper_round_trips_data(tmp_path):
    """_copy_db copies the .db plus any WAL/SHM siblings."""
    from CAPEView.settings_dialog import _copy_db, _quick_counts

    src = tmp_path / "source.db"
    conn = db.connect(src)
    db.init_db(conn)
    db.upsert_claims(conn, [
        {"entry_summary_number": "E1", "claim_number": "C1",
         "status": "Updated", "error_description": None},
    ])
    conn.close()

    dst = tmp_path / "moved" / "destination.db"
    n = _copy_db(src, dst)
    assert n >= 1
    assert dst.exists()

    counts = _quick_counts(dst)
    assert counts["claims"] == 1


def test_copy_db_missing_source_raises(tmp_path):
    from CAPEView.settings_dialog import _copy_db
    with pytest.raises(FileNotFoundError):
        _copy_db(tmp_path / "nope.db", tmp_path / "out.db")


def test_quick_counts_handles_unmigrated_db(tmp_path):
    """An empty / non-CAPEView SQLite file should produce '—' rather than crashing."""
    from CAPEView.settings_dialog import _quick_counts
    p = tmp_path / "blank.db"
    sqlite3.connect(p).close()  # creates file with no tables
    counts = _quick_counts(p)
    assert all(v == "—" for v in counts.values())
