"""Tests for the pivot/aggregation queries used by Deadlines / Refunds / Protests views.

These run the actual SQL the views build (without Qt) and confirm the shape +
filter behavior is correct against a small in-memory dataset.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from CAPEView import cape_database as db


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    """Build a tiny but realistic dataset:
       - 2 importers (one self-filer, one not)
       - 4 entries spread across two CAPE LIQ deadline weeks
       - 2 claims (one Updated, one Failed)
    """
    path = tmp_path / "cape_test.db"
    monkeypatch.setenv("CAPEVIEW_DB_PATH", str(path))
    conn = db.connect(path)
    db.init_db(conn)

    # Importer status master
    conn.executemany(
        "INSERT INTO importer_status (importer_number, importer_name, self_filer, "
        " ace_account, ach_details_in_ace, is_4811_client, psc_for_4811, last_synced_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        [
            ("11-1111111", "ACME INC",   1, 1, 1, 0, 0),
            ("22-2222222", "WIDGETCO",   0, 1, 0, 1, 0),
        ],
    )

    base = date(2026, 5, 1)
    entries = [
        # esn,    importer,      importer_name, div,         cape, liq_status, liq_date, cape_liq, final_liq, duty
        ("E001", "11-1111111", "ACME INC",     "HOUSTON",    "Y", "Liquidated",
         (base).isoformat(),                (base + timedelta(days=80)).isoformat(),
         (base + timedelta(days=180)).isoformat(),  500.00),
        ("E002", "11-1111111", "ACME INC",     "HOUSTON",    "Y", "Liquidated",
         (base).isoformat(),                (base + timedelta(days=80)).isoformat(),
         (base + timedelta(days=180)).isoformat(),  300.00),
        ("E003", "22-2222222", "WIDGETCO",     "LOS ANGELES","Y", "Pending",
         (base + timedelta(days=7)).isoformat(),
         (base + timedelta(days=87)).isoformat(),
         (base + timedelta(days=187)).isoformat(),  100.00),
        ("E004", "22-2222222", "WIDGETCO",     "ATLANTA",    "N", "Liquidated",
         (base).isoformat(),                (base + timedelta(days=80)).isoformat(),
         (base + timedelta(days=180)).isoformat(), 9999.00),
    ]
    for esn, imp_no, imp_name, div_, cape, liq_status, liq, cape_liq, final_liq, duty in entries:
        conn.execute(
            "INSERT INTO entries (entry_summary_number, importer_number, importer_name, div, "
            " cape_phase1_eligible, liquidation_status, liquidation_date, cape_liq_deadline, "
            " final_liquidation_date, total_liquidated_duty, last_imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (esn, imp_no, imp_name, div_, cape, liq_status, liq, cape_liq, final_liq, duty),
        )

    # entry_lines mirroring the entries (one line each)
    for esn, *_rest, duty in entries:
        conn.execute(
            "INSERT INTO entry_lines (entry_summary_number, line_number, tariff_ordinal, "
            " hts_number, line_tariff_goods_value, line_tariff_duty) VALUES (?, 1, 1, ?, ?, ?)",
            (esn, "9903.01.25", duty * 10, duty),
        )

    # Claims
    conn.execute(
        "INSERT INTO claims (entry_summary_number, claim_number, status, error_description, "
        " first_seen, last_seen) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("E001", "C100", "Entry Summary Updated", None),
    )
    conn.execute(
        "INSERT INTO claims (entry_summary_number, claim_number, status, error_description, "
        " first_seen, last_seen) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
        ("E003", "C200", "Failed", "UNABLE TO CALCULATE DUTY"),
    )

    yield conn
    conn.close()


def _run_view(view_cls, conn, filter_text="", **status_overrides):
    """Build the SQL the view would build and run it directly against ``conn``."""
    # Default filter values come from the FilterSpec defaults (None unless overridden).
    status: dict = {spec.key: spec.default for spec in view_cls.status_filters}
    status.update(status_overrides)
    # We can't instantiate the view (needs Qt), but build_query is callable on a
    # zero-arg "fake" with the necessary attrs.
    fake = type("Fake", (), {"row_limit": 5000})()
    sql, params = view_cls.build_query(fake, filter_text, status)
    return conn.execute(sql, params).fetchall()


def test_refunds_view_sums_duty_per_importer(seeded_db):
    from CAPEView.views.table_view import RefundsView
    rows = _run_view(RefundsView, seeded_db)
    # Default cape_eligible='Y' -> only the 3 Y-eligible entries are aggregated.
    # ACME has 2 entries / 2 lines / 800 duty; WIDGETCO has 1 entry / 1 line / 100 duty.
    by_importer = {r[0]: r for r in rows}
    assert "ACME INC" in by_importer and "WIDGETCO" in by_importer
    # column order: importer_name, liq_status, cape, total_duty, entries, lines
    acme = by_importer["ACME INC"]
    assert acme[3] == 800.0
    assert acme[4] == 2
    widget = by_importer["WIDGETCO"]
    assert widget[3] == 100.0
    assert widget[4] == 1


def test_refunds_view_self_filer_filter(seeded_db):
    from CAPEView.views.table_view import RefundsView
    rows = _run_view(RefundsView, seeded_db, self_filer=1)
    importers = {r[0] for r in rows}
    assert importers == {"ACME INC"}  # only ACME is self_filer=1


def test_deadlines_view_groups_by_week(seeded_db):
    from CAPEView.views.table_view import DeadlinesView
    rows = _run_view(DeadlinesView, seeded_db)
    # Default cape_eligible='Y' -> 3 entries. ACME has 2 in HOUSTON same week,
    # WIDGETCO has 1 in LOS ANGELES the next week. Output columns:
    # (week_start, importer_name, div, n, soonest, has_claim)
    weeks = {r[0] for r in rows}
    assert len(weeks) == 2  # two distinct weeks
    by_imp = {r[1]: r for r in rows}
    assert by_imp["ACME INC"][3] == 2     # entry count
    assert by_imp["WIDGETCO"][3] == 1


def test_deadlines_claim_filed_filter(seeded_db):
    from CAPEView.views.table_view import DeadlinesView
    # Both seeded importers have at least one claim (ACME via E001, WIDGETCO via E003)
    # so claim_filed='Y' should keep both. claim_filed='N' should drop both.
    rows_yes = _run_view(DeadlinesView, seeded_db, claim_filed="Y")
    assert {r[1] for r in rows_yes} == {"ACME INC", "WIDGETCO"}

    rows_no = _run_view(DeadlinesView, seeded_db, claim_filed="N")
    assert rows_no == []  # no eligible importer-week groups have zero claims


def test_protests_view_groups_by_final_liq_week(seeded_db):
    from CAPEView.views.table_view import ProtestsView
    rows = _run_view(ProtestsView, seeded_db)
    # All 4 entries have a final_liq_date; the view groups by (week, importer)
    # so we sum the count column to verify total entries per importer.
    totals: dict[str, int] = {}
    for r in rows:
        totals[r[1]] = totals.get(r[1], 0) + r[2]
    assert totals.get("ACME INC") == 2
    assert totals.get("WIDGETCO") == 2  # E003 (week +87) + E004 (week +80)


def test_entries_view_div_filter(seeded_db):
    from CAPEView.views.table_view import EntriesView
    rows = _run_view(EntriesView, seeded_db, div="HOUSTON")
    esns = {r[0] for r in rows}
    assert esns == {"E001", "E002"}  # only the two HOUSTON entries

    rows = _run_view(EntriesView, seeded_db, div="LOS ANGELES")
    assert {r[0] for r in rows} == {"E003"}


def test_claims_view_div_filter_via_join(seeded_db):
    """Claims has no div column of its own — DIV filter applies via the
    LEFT JOIN to entries.div."""
    from CAPEView.views.table_view import ClaimsView
    rows = _run_view(ClaimsView, seeded_db, div="HOUSTON")
    # Only E001's claim is in HOUSTON (E001 -> ACME -> HOUSTON; E003 -> LOS ANGELES)
    esns = {r[0] for r in rows}
    assert esns == {"E001"}

    rows = _run_view(ClaimsView, seeded_db, div="LOS ANGELES")
    assert {r[0] for r in rows} == {"E003"}


def test_compliance_view_div_filter(seeded_db):
    from CAPEView.views.table_view import ComplianceView
    # Only E003 is Failed; it's in LOS ANGELES
    rows = _run_view(ComplianceView, seeded_db, div="LOS ANGELES")
    assert any(r[0] == "E003" for r in rows)
    rows = _run_view(ComplianceView, seeded_db, div="HOUSTON")
    assert rows == []  # no failed claims in HOUSTON


def test_importers_view_div_filter_uses_exists(seeded_db):
    """Importers has no DIV column itself; filter shows importers who have at
    least one entry in the chosen DIV."""
    from CAPEView.views.table_view import ImportersView
    rows = _run_view(ImportersView, seeded_db, div="HOUSTON")
    assert {r[1] for r in rows} == {"ACME INC"}  # only ACME ships through HOUSTON

    rows = _run_view(ImportersView, seeded_db, div="ATLANTA")
    assert {r[1] for r in rows} == {"WIDGETCO"}  # only WIDGETCO has an ATLANTA entry


def test_deadlines_view_div_filter(seeded_db):
    from CAPEView.views.table_view import DeadlinesView
    # ACME entries are HOUSTON; WIDGETCO E003 is LOS ANGELES (only LA entry that's CAPE-eligible)
    rows = _run_view(DeadlinesView, seeded_db, div="HOUSTON")
    assert {r[1] for r in rows} == {"ACME INC"}


def test_refunds_view_div_filter(seeded_db):
    from CAPEView.views.table_view import RefundsView
    rows = _run_view(RefundsView, seeded_db, div="HOUSTON")
    # ACME's HOUSTON entries: E001 ($500) + E002 ($300) = $800
    assert len(rows) == 1
    assert rows[0][0] == "ACME INC"
    assert rows[0][3] == 800.0


def test_protests_view_div_filter(seeded_db):
    from CAPEView.views.table_view import ProtestsView
    rows = _run_view(ProtestsView, seeded_db, div="LOS ANGELES")
    assert {r[1] for r in rows} == {"WIDGETCO"}  # E003 is the LA WIDGETCO entry


def test_compliance_view_excludes_actioned_rejections(seeded_db):
    from CAPEView.views.table_view import ComplianceView
    # Initially the only Failed claim is on E003 -> should appear
    rows = _run_view(ComplianceView, seeded_db)
    assert any("E003" in str(r[0]) for r in rows)

    # Mark the rejection actioned -> view should now hide it
    seeded_db.execute(
        "INSERT INTO entry_actions (entry_summary_number, user_id, action_type, "
        " notes, created_at) VALUES (?, ?, 'REJECTION_ACTIONED', ?, datetime('now'))",
        ("E003", "test", "fixed"),
    )
    rows2 = _run_view(ComplianceView, seeded_db)
    assert not any("E003" in str(r[0]) for r in rows2)
