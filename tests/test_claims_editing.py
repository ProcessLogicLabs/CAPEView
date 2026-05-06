"""Tests for user-driven edits to the claims table.

Covers:
- update_claim_field writes the value, sets manual_override=1, audit-logs
- upsert_claims preserves user edits when manual_override=1
- update is a no-op when value unchanged
- editing an unknown field raises
"""

from __future__ import annotations

import pytest

from CAPEView import cape_database as db


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    path = tmp_path / "cape.db"
    monkeypatch.setenv("CAPEVIEW_DB_PATH", str(path))
    conn = db.connect(path)
    db.init_db(conn)
    db.upsert_claims(conn, [
        {"entry_summary_number": "E001", "claim_number": "C100",
         "status": "Failed", "error_description": "UNABLE TO CALCULATE DUTY"},
    ])
    yield conn
    conn.close()


def test_update_claim_field_sets_override_and_audit(seeded_db):
    ok = db.update_claim_field(
        seeded_db, "E001", "C100", "status",
        new_value="Resolved", user_id="alice",
    )
    assert ok is True

    row = seeded_db.execute(
        "SELECT status, manual_override, updated_by FROM claims "
        "WHERE entry_summary_number='E001' AND claim_number='C100'"
    ).fetchone()
    assert row[0] == "Resolved"
    assert row[1] == 1
    assert row[2] == "alice"

    audit = seeded_db.execute(
        "SELECT user_id, table_name, row_key, field, old_value, new_value "
        "FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert audit[0] == "alice"
    assert audit[1] == "claims"
    assert audit[2] == "E001|C100"
    assert audit[3] == "status"
    assert audit[4] == "Failed"
    assert audit[5] == "Resolved"


def test_update_claim_field_noop_when_unchanged(seeded_db):
    # First edit -> override flag flips to 1, one audit row
    db.update_claim_field(seeded_db, "E001", "C100", "notes",
                          new_value="under review", user_id="alice")
    audit_before = seeded_db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    # Same value again -> no-op (returns False, no audit row added)
    ok = db.update_claim_field(seeded_db, "E001", "C100", "notes",
                               new_value="under review", user_id="alice")
    assert ok is False
    audit_after = seeded_db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert audit_after == audit_before


def test_csv_ingest_preserves_manual_override(seeded_db):
    # User edits the row
    db.update_claim_field(seeded_db, "E001", "C100", "status",
                          new_value="Resolved", user_id="alice")
    # Next CSV cycle re-supplies the original ingest values
    db.upsert_claims(seeded_db, [
        {"entry_summary_number": "E001", "claim_number": "C100",
         "status": "Failed", "error_description": "UNABLE TO CALCULATE DUTY"},
    ])
    row = seeded_db.execute(
        "SELECT status, error_description FROM claims "
        "WHERE entry_summary_number='E001' AND claim_number='C100'"
    ).fetchone()
    # User's edit survives
    assert row[0] == "Resolved"
    # Error description we never edited stays at user's value (None) since
    # manual_override locks the whole row from CSV writes — that's the
    # intentional all-or-nothing semantic.
    assert row[1] == "UNABLE TO CALCULATE DUTY"  # unchanged from initial seed


def test_csv_ingest_overwrites_when_no_override(seeded_db):
    # No manual edit yet — CSV with new values should win.
    db.upsert_claims(seeded_db, [
        {"entry_summary_number": "E001", "claim_number": "C100",
         "status": "Entry Summary Updated", "error_description": None},
    ])
    row = seeded_db.execute(
        "SELECT status, error_description FROM claims "
        "WHERE entry_summary_number='E001' AND claim_number='C100'"
    ).fetchone()
    assert row[0] == "Entry Summary Updated"
    assert row[1] is None


def test_update_unknown_field_rejected(seeded_db):
    with pytest.raises(ValueError):
        db.update_claim_field(seeded_db, "E001", "C100", "first_seen",
                              new_value="hack", user_id="alice")


def test_update_returns_false_for_missing_row(seeded_db):
    ok = db.update_claim_field(seeded_db, "DOES_NOT_EXIST", "C0",
                               "status", new_value="x", user_id="a")
    assert ok is False
