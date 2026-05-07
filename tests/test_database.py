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
