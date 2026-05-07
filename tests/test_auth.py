"""Tests for CAPEView's auth module — pure Python, no Qt required."""

from __future__ import annotations

import json

import pytest

from CAPEView import auth


@pytest.fixture()
def auth_file(tmp_path, monkeypatch):
    """Point auth_path() at a tmp file so tests don't touch the share."""
    p = tmp_path / "auth_users.json"
    monkeypatch.setenv("CAPEVIEW_AUTH_PATH", str(p))
    monkeypatch.delenv("CAPEVIEW_AUTH_BYPASS", raising=False)
    yield p


def test_current_user_includes_domain(monkeypatch):
    monkeypatch.setenv("USERDOMAIN", "DMUSA")
    monkeypatch.setenv("USERNAME", "hpayne")
    assert auth.current_user() == "DMUSA\\hpayne"


def test_current_user_falls_back_when_no_domain(monkeypatch):
    monkeypatch.delenv("USERDOMAIN", raising=False)
    monkeypatch.setenv("USERNAME", "hpayne")
    assert auth.current_user() == "hpayne"


def test_load_missing_file_returns_empty_config(auth_file):
    cfg = auth.load()
    assert cfg.users == []
    assert cfg.admins == []


def test_load_malformed_file_returns_empty_config(auth_file):
    auth_file.write_text("{ this is not json", encoding="utf-8")
    cfg = auth.load()
    assert cfg.users == []


def test_load_strips_blank_entries(auth_file):
    auth_file.write_text(
        json.dumps({"users": ["DMUSA\\a", "", "  "], "admins": [None, "DMUSA\\a"]}),
        encoding="utf-8",
    )
    cfg = auth.load()
    assert cfg.users == ["DMUSA\\a"]
    assert cfg.admins == ["DMUSA\\a"]


def test_save_roundtrip(auth_file):
    cfg = auth.AuthConfig(users=["DMUSA\\hpayne", "DMUSA\\rbloggs"], admins=["DMUSA\\hpayne"])
    auth.save(cfg)
    loaded = auth.load()
    assert loaded.users == cfg.users
    assert loaded.admins == cfg.admins
    on_disk = json.loads(auth_file.read_text(encoding="utf-8"))
    assert on_disk == {"users": cfg.users, "admins": cfg.admins}


def test_bootstrap_mode_when_no_admins(auth_file):
    """Empty admins list → everyone is treated as authorized AND admin."""
    auth.save(auth.AuthConfig(users=["DMUSA\\someone"], admins=[]))
    cfg = auth.load()
    assert auth.is_bootstrap_mode(cfg)
    assert auth.is_authorized("DMUSA\\anyone", cfg)
    assert auth.is_admin("DMUSA\\anyone", cfg)


def test_authorized_when_in_users_list(auth_file):
    auth.save(auth.AuthConfig(
        users=["DMUSA\\hpayne", "DMUSA\\rbloggs"],
        admins=["DMUSA\\hpayne"],
    ))
    cfg = auth.load()
    assert auth.is_authorized("DMUSA\\hpayne", cfg)
    assert auth.is_authorized("DMUSA\\rbloggs", cfg)
    assert not auth.is_authorized("DMUSA\\stranger", cfg)


def test_authorized_is_case_insensitive(auth_file):
    auth.save(auth.AuthConfig(
        users=["DMUSA\\HPayne"], admins=["DMUSA\\HPayne"],
    ))
    cfg = auth.load()
    assert auth.is_authorized("dmusa\\hpayne", cfg)
    assert auth.is_admin("DMUSA\\hpayne", cfg)


def test_admin_requires_admins_membership(auth_file):
    auth.save(auth.AuthConfig(
        users=["DMUSA\\hpayne", "DMUSA\\rbloggs"],
        admins=["DMUSA\\hpayne"],
    ))
    cfg = auth.load()
    assert auth.is_admin("DMUSA\\hpayne", cfg)
    assert not auth.is_admin("DMUSA\\rbloggs", cfg)


def test_bypass_env_var_overrides_everything(auth_file, monkeypatch):
    auth.save(auth.AuthConfig(
        users=["DMUSA\\hpayne"], admins=["DMUSA\\hpayne"],
    ))
    cfg = auth.load()
    assert not auth.is_authorized("DMUSA\\stranger", cfg)
    monkeypatch.setenv("CAPEVIEW_AUTH_BYPASS", "1")
    assert auth.is_authorized("DMUSA\\stranger", cfg)
    assert auth.is_admin("DMUSA\\stranger", cfg)
