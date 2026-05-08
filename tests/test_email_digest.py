"""Tests for the Compliance digest email module.

Outlook COM is mocked throughout — these tests run on any platform with
no pywin32 install required.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from CAPEView import cape_database as db
from CAPEView import email_digest


# ---------------------------------------------------------------------------
# Fixtures

@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    """Synthetic DB with two failed claims and one updated claim. The two
    failed claims have known cape_liq_deadline + duty values so summary
    aggregation is testable."""
    path = tmp_path / "cape.db"
    monkeypatch.setenv("CAPEVIEW_DB_PATH", str(path))
    conn = db.connect(path)
    db.init_db(conn)

    base = date.today()
    entries = [
        # esn,    importer_no,  importer,        div,         cape, liq_status,    liq, cape_liq, final_liq, total_duty
        ("E001", "11-1111111", "ACME INC",       "HOUSTON",   "Y", "Liquidated",
         base.isoformat(), (base + timedelta(days=10)).isoformat(),
         (base + timedelta(days=110)).isoformat(),  500.00),
        ("E002", "22-2222222", "WIDGETCO",       "LOS ANGELES","Y", "Liquidated",
         base.isoformat(), (base + timedelta(days=45)).isoformat(),
         (base + timedelta(days=145)).isoformat(),  300.00),
        ("E003", "33-3333333", "FRANKLIN INC",   "HOUSTON",   "Y", "Liquidated",
         base.isoformat(), (base + timedelta(days=80)).isoformat(),
         (base + timedelta(days=180)).isoformat(),  120.00),
    ]
    for esn, imp_no, imp_name, div_, cape, liq_status, liq, cape_liq, final_liq, duty in entries:
        conn.execute(
            "INSERT INTO entries (entry_summary_number, importer_number, importer_name, div, "
            " cape_phase1_eligible, liquidation_status, liquidation_date, cape_liq_deadline, "
            " final_liquidation_date, total_liquidated_duty, last_imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (esn, imp_no, imp_name, div_, cape, liq_status, liq, cape_liq, final_liq, duty),
        )

    # Two failed (E001, E003), one updated (E002)
    db.upsert_claims(conn, [
        {"entry_summary_number": "E001", "claim_number": "C001",
         "status": "Failed", "error_description": "UNABLE TO CALCULATE DUTY"},
        {"entry_summary_number": "E002", "claim_number": "C002",
         "status": "Entry Summary Updated", "error_description": ""},
        {"entry_summary_number": "E003", "claim_number": "C003",
         "status": "Failed", "error_description": "PROTEST ON ENTRY"},
    ])
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# build_digest

def test_build_digest_returns_only_currently_failed(seeded_db):
    digest = email_digest.build_digest(seeded_db)
    esns = [r[0] for r in digest["rows"]]
    assert set(esns) == {"E001", "E003"}
    assert "E002" not in esns


def test_build_digest_summary_stats(seeded_db):
    digest = email_digest.build_digest(seeded_db)
    s = digest["summary"]
    assert s["total_failed"] == 2
    # E001 = 500.00 + E003 = 120.00
    assert s["total_duty"] == pytest.approx(620.00)
    # E001 -> HOUSTON; E003 -> HOUSTON; both rows from HOUSTON
    assert s["by_div"] == {"HOUSTON": 2}


def test_build_digest_sorted_by_deadline_asc(seeded_db):
    digest = email_digest.build_digest(seeded_db)
    deadlines = [r[5] for r in digest["rows"]]
    # E001 deadline (today+10) is sooner than E003 (today+80)
    assert deadlines[0] < deadlines[1]


# ---------------------------------------------------------------------------
# render_html

def test_render_html_contains_summary_and_top10(seeded_db):
    digest = email_digest.build_digest(seeded_db)
    body = email_digest.render_html(digest, "v1.2.3")
    assert "Compliance digest" in body
    assert "Total failed claims" in body
    assert "v1.2.3" in body
    assert "Top 10" in body or "Top 10 most-urgent rejects" in body
    # Currency formatting in body
    assert "$620.00" in body
    # E001's importer should be HTML-escaped and present
    assert "ACME INC" in body


def test_render_html_escapes_user_strings():
    """Importer name / error description with HTML-special chars must be escaped."""
    digest = {
        "summary": {"total_failed": 1, "total_duty": 100.0,
                    "by_div": {"HOUSTON": 1}},
        "rows": [
            ("E001", "C001", "Failed",
             "<script>alert('xss')</script>",
             "HOUSTON", "2026-12-01", 100.0,
             "<b>Bobby Tables & Co</b>"),
        ],
    }
    body = email_digest.render_html(digest, "v0.0.1")
    # The raw <script> must NOT appear; escaped form must
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body
    # Importer name escaped
    assert "&lt;b&gt;Bobby Tables &amp; Co" in body


def test_render_html_handles_zero_failed():
    digest = {"summary": {"total_failed": 0, "total_duty": 0,
                          "by_div": {}}, "rows": []}
    body = email_digest.render_html(digest, "v0.0.1")
    assert "All clear" in body
    assert "Top 10" not in body


# ---------------------------------------------------------------------------
# write_attachment

def test_write_attachment_produces_readable_xlsx(seeded_db, tmp_path):
    pytest.importorskip("openpyxl")
    from openpyxl import load_workbook

    digest = email_digest.build_digest(seeded_db)
    target = tmp_path / "digest.xlsx"
    email_digest.write_attachment(digest, target)

    wb = load_workbook(target)
    ws = wb.active
    assert ws.title == "Compliance"
    # Header row matches HEADERS
    assert [c.value for c in ws[1]] == email_digest.HEADERS
    # Data rows = 2 failed claims
    assert ws.max_row == 1 + 2


# ---------------------------------------------------------------------------
# Outlook COM transport (mocked)

def _make_disabled_settings():
    s = MagicMock()
    s.get.return_value = False
    return s


def _make_enabled_settings():
    s = MagicMock()
    s.get.return_value = True
    return s


def test_send_is_noop_when_disabled(seeded_db):
    result = email_digest.send_compliance_digest_to_self(
        seeded_db, "v0.0.1", settings=_make_disabled_settings(),
    )
    assert result == {"sent": False, "recipient": None, "rows": 0, "error": None}


def test_send_returns_error_when_no_recipient(seeded_db):
    """email.enabled=True but Outlook unreachable → graceful fail, no exception."""
    with patch.object(email_digest, "_get_current_user_email", return_value=""):
        result = email_digest.send_compliance_digest_to_self(
            seeded_db, "v0.0.1", settings=_make_enabled_settings(),
        )
    assert result["sent"] is False
    assert result["recipient"] is None
    assert "no recipient" in (result["error"] or "")


def test_send_via_outlook_invokes_correct_calls(seeded_db, tmp_path):
    """Mock win32com.client.Dispatch and verify the call sequence."""
    fake_dispatch = MagicMock()
    fake_outlook = MagicMock()
    fake_mail = MagicMock()
    fake_dispatch.return_value = fake_outlook
    fake_outlook.CreateItem.return_value = fake_mail

    fake_module = MagicMock()
    fake_module.client.Dispatch = fake_dispatch

    # Pre-create attachment so the path exists when Outlook would attach it
    attachment = tmp_path / "att.xlsx"
    attachment.write_bytes(b"fake xlsx")

    with patch.dict("sys.modules", {"win32com": fake_module,
                                     "win32com.client": fake_module.client}):
        email_digest._send_via_outlook(
            "Test Subject", "<p>body</p>", attachment, "user@example.com",
        )

    fake_outlook.CreateItem.assert_called_once_with(0)
    assert fake_mail.Subject == "Test Subject"
    assert fake_mail.HTMLBody == "<p>body</p>"
    assert fake_mail.To == "user@example.com"
    fake_mail.Attachments.Add.assert_called_once_with(str(attachment))
    fake_mail.Send.assert_called_once()


def test_send_compliance_digest_end_to_end_mocked(seeded_db, tmp_path):
    """Full pipeline with Outlook mocked: builds, renders, writes xlsx, calls send."""
    with patch.object(email_digest, "_get_current_user_email",
                      return_value="heath@example.com"), \
         patch.object(email_digest, "_send_via_outlook") as mock_send:
        result = email_digest.send_compliance_digest_to_self(
            seeded_db, "v0.0.1", settings=_make_enabled_settings(),
        )

    assert result["sent"] is True
    assert result["recipient"] == "heath@example.com"
    assert result["rows"] == 2
    assert result["error"] is None
    mock_send.assert_called_once()
    args, _ = mock_send.call_args
    subject, _html_body, attachment_path, to_address = args
    assert "Compliance digest" in subject
    assert "2 failed claims" in subject
    assert to_address == "heath@example.com"
    assert attachment_path.exists()


# ---------------------------------------------------------------------------
# Ingest hook

def test_ingest_calls_digest_when_rows_changed(tmp_path, monkeypatch):
    """process_inbox should call _maybe_send_digest after a successful ingest."""
    from CAPEView import claims_csv_ingest

    # Isolate the DB
    db_path = tmp_path / "cape.db"
    monkeypatch.setenv("CAPEVIEW_DB_PATH", str(db_path))

    # Spy on the digest-send function
    captured = {"called": False, "rows_at_call": None}

    def fake_send(conn, version, settings=None):
        captured["called"] = True
        # Connection should be live; rows should reflect the just-ingested state
        captured["rows_at_call"] = conn.execute(
            "SELECT COUNT(*) FROM claims"
        ).fetchone()[0]
        return {"sent": False, "recipient": None, "rows": 0, "error": None}

    monkeypatch.setattr(email_digest, "send_compliance_digest_to_self", fake_send)

    # Drop a CSV in
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    csv_file = inbox / "claims.csv"
    csv_file.write_text(
        "ENTRY_NUMBER,CLAIM_NUMBER,STATUS,ERROR_DESCRIPTION\n"
        "60500009000,X1,Failed,UNABLE TO CALCULATE DUTY\n",
        encoding="utf-8",
    )
    summary = claims_csv_ingest.process_inbox(inbox)

    assert summary["inserted"] == 1
    assert captured["called"] is True
    assert captured["rows_at_call"] == 1


def test_ingest_skips_digest_when_no_rows(tmp_path, monkeypatch):
    """An empty inbox produces a summary with 0 rows; digest should NOT fire."""
    from CAPEView import claims_csv_ingest

    db_path = tmp_path / "cape.db"
    monkeypatch.setenv("CAPEVIEW_DB_PATH", str(db_path))

    captured = {"called": False}

    def fake_send(*args, **kwargs):
        captured["called"] = True
        return {"sent": False, "recipient": None, "rows": 0, "error": None}

    monkeypatch.setattr(email_digest, "send_compliance_digest_to_self", fake_send)

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    summary = claims_csv_ingest.process_inbox(inbox)

    assert summary["inserted"] == 0
    assert captured["called"] is False
