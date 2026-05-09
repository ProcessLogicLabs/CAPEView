"""Database layer tests — schema bootstrapping and upsert idempotency."""

from __future__ import annotations

from pathlib import Path

import pytest

from CAPEView import cape_database as db


@pytest.fixture()
def tmp_db(tmp_path: Path):
    path = tmp_path / "cape_test.db"
    conn = db.connect(path)
    db.init_db(conn)
    yield conn
    conn.close()


def test_init_db_creates_all_tables(tmp_db):
    rows = tmp_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {
        "entries", "entry_lines", "claims", "importer_status",
        "entry_actions", "audit_log", "import_runs",
    } <= names


def test_cleanup_excel_quoted_keys_unwraps_in_place(tmp_db):
    """Polluted row → updated to clean values."""
    ts = db.now_iso()
    tmp_db.execute(
        "INSERT INTO claims (entry_summary_number, claim_number, status, "
        " error_description, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
        ('="60576069342"', '="100000241223"', "Failed",
         "HTS RELATIONSHIP/SEQUENCE MISMATCH", ts, ts),
    )

    result = db.cleanup_excel_quoted_keys(tmp_db)

    row = tmp_db.execute(
        "SELECT entry_summary_number, claim_number FROM claims"
    ).fetchone()
    assert row[0] == "60576069342"
    assert row[1] == "100000241223"
    assert result == {"updated": 1, "deleted_duplicates": 0}


def test_cleanup_excel_quoted_keys_drops_duplicates(tmp_db):
    """Polluted + clean equivalent → polluted is deleted, clean kept."""
    ts = db.now_iso()
    # Clean row already exists
    tmp_db.execute(
        "INSERT INTO claims (entry_summary_number, claim_number, status, "
        " error_description, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
        ("60576069342", "100000241223", "Failed", "FOO", ts, ts),
    )
    # Polluted duplicate ingested before the parser fix
    tmp_db.execute(
        "INSERT INTO claims (entry_summary_number, claim_number, status, "
        " error_description, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
        ('="60576069342"', '="100000241223"', "Failed", "BAR", ts, ts),
    )

    result = db.cleanup_excel_quoted_keys(tmp_db)

    rows = tmp_db.execute(
        "SELECT entry_summary_number, claim_number, error_description "
        "FROM claims ORDER BY entry_summary_number"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "60576069342"
    assert rows[0][2] == "FOO"  # kept the clean row, not the polluted one
    assert result == {"updated": 0, "deleted_duplicates": 1}


def test_cleanup_excel_quoted_keys_idempotent(tmp_db):
    """Re-running on already-clean data is a no-op."""
    ts = db.now_iso()
    tmp_db.execute(
        "INSERT INTO claims (entry_summary_number, claim_number, status, "
        " error_description, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
        ("60576069342", "100000241223", "Failed", "FOO", ts, ts),
    )
    result = db.cleanup_excel_quoted_keys(tmp_db)
    assert result == {"updated": 0, "deleted_duplicates": 0}


def test_upsert_claims_inserts_then_updates(tmp_db):
    rows = [
        {"entry_summary_number": "60500000001", "claim_number": "100",
         "status": "Updated", "error_description": None},
        {"entry_summary_number": "60500000002", "claim_number": "100",
         "status": "Failed", "error_description": "DUTY"},
    ]
    inserted, updated = db.upsert_claims(tmp_db, rows)
    assert inserted == 2 and updated == 0

    rows_again = [
        {"entry_summary_number": "60500000001", "claim_number": "100",
         "status": "Updated", "error_description": "RESOLVED"},
        {"entry_summary_number": "60500000003", "claim_number": "200",
         "status": "Updated", "error_description": None},
    ]
    inserted2, updated2 = db.upsert_claims(tmp_db, rows_again)
    assert inserted2 == 1 and updated2 == 1

    # Total distinct rows should now be 3
    total = tmp_db.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    assert total == 3

    err = tmp_db.execute(
        "SELECT error_description FROM claims WHERE entry_summary_number = ?",
        ("60500000001",),
    ).fetchone()[0]
    assert err == "RESOLVED"


def _seed_importer(conn, importer_number="12-3456789", **flags):
    """Insert a minimal importer_status row for the flag-edit tests."""
    cols = ["importer_number", "importer_name", "self_filer", "ace_account",
            "ach_details_in_ace", "is_4811_client", "psc_for_4811", "last_synced_at"]
    values = [importer_number, "ACME INC",
              flags.get("self_filer"), flags.get("ace_account"),
              flags.get("ach_details_in_ace"), flags.get("is_4811_client"),
              flags.get("psc_for_4811"), db.now_iso()]
    conn.execute(
        f"INSERT INTO importer_status ({', '.join(cols)}) "
        f"VALUES ({', '.join(['?'] * len(cols))})",
        values,
    )


def test_update_importer_flag_writes_value_and_audit_log(tmp_db):
    _seed_importer(tmp_db, self_filer=0)
    changed = db.update_importer_flag(
        tmp_db, "12-3456789", "self_filer", 1, "DMUSA\\hpayne",
    )
    assert changed is True

    val = tmp_db.execute(
        "SELECT self_filer FROM importer_status WHERE importer_number = ?",
        ("12-3456789",),
    ).fetchone()[0]
    assert val == 1

    row = tmp_db.execute(
        "SELECT user_id, table_name, row_key, field, old_value, new_value "
        "FROM audit_log WHERE table_name = 'importer_status'"
    ).fetchone()
    assert row[0] == "DMUSA\\hpayne"
    assert row[2] == "12-3456789"
    assert row[3] == "self_filer"
    assert row[4] == "0"
    assert row[5] == "1"


def test_update_importer_flag_handles_null_transitions(tmp_db):
    """NULL → 1 logs old=NULL, then 1 → NULL logs new=NULL."""
    _seed_importer(tmp_db)  # all flags NULL
    db.update_importer_flag(tmp_db, "12-3456789", "ace_account", 1, "u")
    db.update_importer_flag(tmp_db, "12-3456789", "ace_account", None, "u")
    rows = tmp_db.execute(
        "SELECT old_value, new_value FROM audit_log "
        "WHERE table_name = 'importer_status' AND field = 'ace_account' "
        "ORDER BY id"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [(None, "1"), ("1", None)]


def test_update_importer_flag_noop_skips_audit_log(tmp_db):
    _seed_importer(tmp_db, is_4811_client=1)
    changed = db.update_importer_flag(
        tmp_db, "12-3456789", "is_4811_client", 1, "u",
    )
    assert changed is False
    n = tmp_db.execute(
        "SELECT COUNT(*) FROM audit_log WHERE table_name = 'importer_status'"
    ).fetchone()[0]
    assert n == 0


def test_update_importer_flag_rejects_unknown_field(tmp_db):
    _seed_importer(tmp_db)
    with pytest.raises(ValueError, match="Unknown importer flag field"):
        db.update_importer_flag(tmp_db, "12-3456789", "importer_name", 1, "u")


def test_update_importer_flag_rejects_bad_value(tmp_db):
    _seed_importer(tmp_db)
    with pytest.raises(ValueError, match="Flag value must be"):
        db.update_importer_flag(tmp_db, "12-3456789", "self_filer", 2, "u")


def test_update_importer_flag_rejects_unknown_importer(tmp_db):
    with pytest.raises(ValueError, match="No importer_status row"):
        db.update_importer_flag(tmp_db, "99-9999999", "self_filer", 1, "u")


def test_upsert_entries_basic(tmp_db):
    rows = [
        {"entry_summary_number": "60500000010",
         "importer_number": "12-3456789", "importer_name": "ACME INC",
         "cape_phase1_eligible": "Y", "total_liquidated_duty": 100.0},
    ]
    inserted, updated = db.upsert_entries(tmp_db, rows)
    assert inserted == 1 and updated == 0

    rows[0]["total_liquidated_duty"] = 250.5
    inserted, updated = db.upsert_entries(tmp_db, rows)
    assert inserted == 0 and updated == 1

    duty = tmp_db.execute(
        "SELECT total_liquidated_duty FROM entries WHERE entry_summary_number = ?",
        ("60500000010",),
    ).fetchone()[0]
    assert duty == 250.5
