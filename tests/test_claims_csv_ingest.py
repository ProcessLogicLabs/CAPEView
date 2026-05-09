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


def test_status_change_writes_audit_log(tmp_path, isolated_db):
    """A claim transitioning Failed → Updated across two CSVs lands in audit_log."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    # First file: claim is Failed
    csv1 = inbox / "day1.csv"
    write_csv(csv1, [
        {"entry_summary_number": "60500002000", "claim_number": "X1",
         "status": "Failed", "error_description": "UNABLE TO CALCULATE DUTY"},
    ])
    claims_csv_ingest.process_inbox(inbox)

    # Second file: same key, now Entry Summary Updated and error cleared
    csv2 = inbox / "day2.csv"
    write_csv(csv2, [
        {"entry_summary_number": "60500002000", "claim_number": "X1",
         "status": "Entry Summary Updated", "error_description": ""},
    ])
    claims_csv_ingest.process_inbox(inbox)

    conn = db.connect()
    db.init_db(conn)
    rows = conn.execute(
        "SELECT field, old_value, new_value, user_id FROM audit_log "
        "WHERE row_key = '60500002000|X1' ORDER BY id"
    ).fetchall()
    conn.close()

    fields = [(r[0], r[1], r[2], r[3]) for r in rows]
    assert ("status", "Failed", "Entry Summary Updated", "csv_ingest") in fields
    # error_description went from a string to "" (treated as empty/None) — also tracked
    assert any(f[0] == "error_description" and f[3] == "csv_ingest" for f in fields)


def test_no_audit_log_on_unchanged_row(tmp_path, isolated_db):
    """Re-ingesting an identical row adds no NEW audit_log entries.

    Note: a brand-new Failed claim writes one audit_log row at insert time
    (NULL -> Failed transition) so the NEW REJECTS dashboard card can find
    newly-arrived rejects. The test intent is "subsequent re-ingests don't
    keep adding entries" — so the count after both ingests should equal
    the count after just the first ingest.
    """
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    payload = [
        {"entry_summary_number": "60500002100", "claim_number": "X2",
         "status": "Failed", "error_description": "PROTEST ON ENTRY"},
    ]
    csv1 = inbox / "first.csv"
    write_csv(csv1, payload)
    claims_csv_ingest.process_inbox(inbox)

    conn = db.connect()
    db.init_db(conn)
    after_first = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE row_key = '60500002100|X2'"
    ).fetchone()[0]
    conn.close()
    assert after_first == 1  # the NULL -> Failed insert audit

    csv2 = inbox / "second.csv"
    write_csv(csv2, payload)
    claims_csv_ingest.process_inbox(inbox)

    conn = db.connect()
    db.init_db(conn)
    after_second = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE row_key = '60500002100|X2'"
    ).fetchone()[0]
    conn.close()
    # No NEW entries written by the no-op re-ingest
    assert after_second == after_first


def test_manual_override_blocks_csv_audit(tmp_path, isolated_db):
    """A manually-overridden row's CSV-driven changes are skipped entirely
    (manual_override path only refreshes last_seen) so no audit row is written."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    # Seed a row, then mark it manual_override via direct DB edit
    csv1 = inbox / "seed.csv"
    write_csv(csv1, [
        {"entry_summary_number": "60500002200", "claim_number": "X3",
         "status": "Failed", "error_description": "UNABLE TO CALCULATE DUTY"},
    ])
    claims_csv_ingest.process_inbox(inbox)

    conn = db.connect()
    db.init_db(conn)
    conn.execute(
        "UPDATE claims SET manual_override = 1 "
        "WHERE entry_summary_number = '60500002200' AND claim_number = 'X3'"
    )
    conn.close()

    # Capture audit count after the seed insert (NULL -> Failed = 1 entry)
    conn = db.connect()
    db.init_db(conn)
    after_seed = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE row_key = '60500002200|X3'"
    ).fetchone()[0]
    conn.close()

    # Now the upstream CSV would correct it — should be ignored
    csv2 = inbox / "would_correct.csv"
    write_csv(csv2, [
        {"entry_summary_number": "60500002200", "claim_number": "X3",
         "status": "Entry Summary Updated", "error_description": ""},
    ])
    claims_csv_ingest.process_inbox(inbox)

    conn = db.connect()
    db.init_db(conn)
    after_would_correct = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE row_key = '60500002200|X3'"
    ).fetchone()[0]
    # Status preserved at Failed
    status = conn.execute(
        "SELECT status FROM claims "
        "WHERE entry_summary_number = '60500002200' AND claim_number = 'X3'"
    ).fetchone()[0]
    conn.close()
    # The manual-override path skipped the update entirely → no NEW audit row
    assert after_would_correct == after_seed
    assert status == "Failed"


def test_unwrap_excel_text_strips_wrapper():
    from CAPEView.claims_csv_ingest import _unwrap_excel_text
    assert _unwrap_excel_text('="60576069342"') == "60576069342"
    assert _unwrap_excel_text('  ="100000241223"  ') == "100000241223"
    assert _unwrap_excel_text("60576072486") == "60576072486"  # already clean
    assert _unwrap_excel_text("") == ""
    assert _unwrap_excel_text(None) == ""


def test_parse_csv_strips_excel_text_wrapper(tmp_path, isolated_db):
    """ACE Portal exports use ``="..."`` to force-text numeric strings.
    The parser must unwrap them so DB keys match clean rows."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    csv = inbox / "ace_export.csv"
    csv.write_text(
        'ENTRY_NUMBER,CLAIM_NUMBER,STATUS,ERROR_DESCRIPTION\n'
        '="60576069342",="100000241223",Failed,HTS RELATIONSHIP/SEQUENCE MISMATCH\n',
        encoding="utf-8",
    )
    summary = claims_csv_ingest.process_inbox(inbox)
    assert summary["inserted"] == 1

    conn = db.connect()
    db.init_db(conn)
    row = conn.execute(
        "SELECT entry_summary_number, claim_number, status, error_description "
        "FROM claims"
    ).fetchone()
    conn.close()
    assert row[0] == "60576069342"
    assert row[1] == "100000241223"
    assert row[2] == "Failed"
    assert row[3] == "HTS RELATIONSHIP/SEQUENCE MISMATCH"


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
