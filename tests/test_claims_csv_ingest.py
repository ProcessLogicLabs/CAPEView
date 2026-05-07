"""Tests for the claims CSV ingestion job."""

from __future__ import annotations

from pathlib import Path

import pytest

from CAPEView import cape_database as db
from CAPEView import claims_csv_ingest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Force the package to use a tmp DB by pointing CAPEVIEW_DB_PATH at it."""
    db_path = tmp_path / "cape.db"
    monkeypatch.setenv("CAPEVIEW_DB_PATH", str(db_path))
    yield db_path


def write_csv(path: Path, rows: list[dict], headers=("ENTRY_NUMBER", "CLAIM_NUMBER",
                                                     "STATUS", "ERROR_DESCRIPTION")):
    lines = [",".join(headers)]
    key_map = {
        "ENTRY_NUMBER": "entry_summary_number",
        "CLAIM_NUMBER": "claim_number",
        "STATUS": "status",
        "ERROR_DESCRIPTION": "error_description",
    }
    for r in rows:
        line = ",".join((r.get(key_map[h]) or "") for h in headers)
        lines.append(line)
    path.write_text("\n".join(lines), encoding="utf-8")


def test_process_inbox_inserts_then_dedupes(tmp_path, isolated_db):
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    csv1 = inbox / "claims_2026-05-01.csv"
    write_csv(csv1, [
        {"entry_summary_number": "60500000100", "claim_number": "C1",
         "status": "Entry Summary Updated", "error_description": ""},
        {"entry_summary_number": "60500000101", "claim_number": "C2",
         "status": "Failed", "error_description": "UNABLE TO CALCULATE DUTY"},
    ])

    summary = claims_csv_ingest.process_inbox(inbox)
    assert summary["files"] == 1
    assert summary["rows"] == 2
    assert summary["inserted"] == 2
    assert summary["updated"] == 0
    assert not list(inbox.glob("*.csv"))  # archived

    # Drop a duplicate file with one updated row + one new row
    csv2 = inbox / "claims_2026-05-02.csv"
    write_csv(csv2, [
        {"entry_summary_number": "60500000100", "claim_number": "C1",
         "status": "Entry Summary Updated", "error_description": ""},
        {"entry_summary_number": "60500000102", "claim_number": "C3",
         "status": "Entry Summary Updated", "error_description": ""},
    ])
    summary2 = claims_csv_ingest.process_inbox(inbox)
    assert summary2["inserted"] == 1
    assert summary2["updated"] == 1

    conn = db.connect()
    db.init_db(conn)
    total = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    conn.close()
    assert total == 3


def test_process_single_file_copies_and_archives(tmp_path, isolated_db):
    """Drop-zone path: ingest a CSV that lives outside the inbox."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    # Caller's file lives somewhere unrelated to the inbox
    drop_dir = tmp_path / "user_downloads"
    drop_dir.mkdir()
    src = drop_dir / "claims_dropped.csv"
    write_csv(src, [
        {"entry_summary_number": "60500000900", "claim_number": "D1",
         "status": "Entry Summary Updated", "error_description": ""},
    ])

    summary = claims_csv_ingest.process_single_file(src, inbox=inbox)
    assert summary["files"] == 1
    assert summary["rows"] == 1
    assert summary["inserted"] == 1
    assert summary["errors"] == []
    assert not list(inbox.glob("*.csv"))  # copied in then archived
    assert any(p.name == "claims_dropped.csv" for p in (inbox / "processed").rglob("*.csv"))


def test_process_single_file_handles_inbox_collision(tmp_path, isolated_db):
    """Same filename already in inbox → timestamp-suffixed copy, both ingest."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    # Sitting target with the same name (simulating a previous undelivered drop)
    sitting = inbox / "claims_dropped.csv"
    write_csv(sitting, [
        {"entry_summary_number": "60500001000", "claim_number": "P1",
         "status": "Entry Summary Updated", "error_description": ""},
    ])

    drop_dir = tmp_path / "downloads"
    drop_dir.mkdir()
    src = drop_dir / "claims_dropped.csv"
    write_csv(src, [
        {"entry_summary_number": "60500001001", "claim_number": "P2",
         "status": "Failed", "error_description": "PROTEST ON ENTRY"},
    ])

    summary = claims_csv_ingest.process_single_file(src, inbox=inbox)
    assert summary["inserted"] == 1
    # The pre-existing file is NOT touched by process_single_file
    assert sitting.exists()


def test_process_single_file_reports_parse_error(tmp_path, isolated_db):
    """Malformed CSV (missing required columns) → error captured in summary."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    drop_dir = tmp_path / "downloads"
    drop_dir.mkdir()
    bad = drop_dir / "wrong_schema.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")

    summary = claims_csv_ingest.process_single_file(bad, inbox=inbox)
    assert summary["inserted"] == 0
    assert summary["updated"] == 0
    assert summary["errors"], "expected an error string"
    assert "required columns missing" in summary["errors"][0]


def test_resolve_columns_handles_aliases(tmp_path, isolated_db):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    csv = inbox / "claims_alias.csv"

    csv.write_text(
        "Entry Summary Number,Cape Claim Number,Filing Status,Error Detail\n"
        "60500000200,C9,Failed,UNABLE\n",
        encoding="utf-8",
    )
    summary = claims_csv_ingest.process_inbox(inbox)
    assert summary["inserted"] == 1
