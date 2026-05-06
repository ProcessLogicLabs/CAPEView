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
