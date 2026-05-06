"""SQLite database layer for CAPEView.

- Centralised connection factory (WAL mode for safe concurrent reads on SMB share)
- Schema migrations driven by ``schema_version`` PRAGMA
- Query helpers used by ingestion jobs and views

The database lives at SHARED_DB_PATH by default (``\\\\192.168.115.99\\scans\\cape.db``,
matching the existing tariffmill.db location). Override via the ``CAPEVIEW_DB_PATH``
environment variable for local testing.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SHARED_DB_PATH = r"\\192.168.115.99\scans\cape.db"
LOCAL_DB_PATH = Path.home() / "AppData" / "Local" / "CAPEView" / "cape.db"


SCHEMA_STATEMENTS = [
    # v1 - initial schema
    """
    CREATE TABLE IF NOT EXISTS entries (
        entry_summary_number          TEXT PRIMARY KEY,
        importer_number               TEXT,
        importer_name                 TEXT,
        div                           TEXT,
        cape_phase1_eligible          TEXT,
        entry_type_code               TEXT,
        port_of_entry_code            TEXT,
        entry_date                    TEXT,
        entry_summary_date            TEXT,
        initial_es_create_date        TEXT,
        reconciliation_indicator      TEXT,
        control_status                TEXT,
        psc_indicator                 TEXT,
        liquidation_date              TEXT,
        liquidation_status            TEXT,
        final_liquidation_date        TEXT,
        cape_liq_deadline             TEXT,
        protest_number                TEXT,
        protest_status                TEXT,
        review_team_number            TEXT,
        country_of_origin_code        TEXT,
        country_of_export_code        TEXT,
        total_liquidated_duty         REAL,
        last_imported_at              TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entry_lines (
        entry_summary_number          TEXT,
        line_number                   INTEGER,
        tariff_ordinal                INTEGER,
        hts_number                    TEXT,
        line_tariff_goods_value       REAL,
        line_tariff_duty              REAL,
        manufacturer_id               TEXT,
        foreign_exporter_id           TEXT,
        line_spi_code                 TEXT,
        country_of_origin_code        TEXT,
        country_of_export_code        TEXT,
        PRIMARY KEY (entry_summary_number, line_number, tariff_ordinal)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS claims (
        entry_summary_number          TEXT,
        claim_number                  TEXT,
        status                        TEXT,
        error_description             TEXT,
        first_seen                    TEXT,
        last_seen                     TEXT,
        PRIMARY KEY (entry_summary_number, claim_number)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS importer_status (
        importer_number               TEXT PRIMARY KEY,
        importer_name                 TEXT,
        self_filer                    INTEGER,
        ace_account                   INTEGER,
        ach_details_in_ace            INTEGER,
        is_4811_client                INTEGER,
        psc_for_4811                  INTEGER,
        last_synced_at                TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entry_actions (
        id                            INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_summary_number          TEXT,
        user_id                       TEXT,
        action_type                   TEXT,
        notes                         TEXT,
        created_at                    TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id                            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id                       TEXT,
        table_name                    TEXT,
        row_key                       TEXT,
        field                         TEXT,
        old_value                     TEXT,
        new_value                     TEXT,
        changed_at                    TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS import_runs (
        id                            INTEGER PRIMARY KEY AUTOINCREMENT,
        source                        TEXT,
        source_file                   TEXT,
        rows_inserted                 INTEGER,
        rows_updated                  INTEGER,
        started_at                    TEXT,
        finished_at                   TEXT,
        notes                         TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_entries_importer       ON entries(importer_number);",
    "CREATE INDEX IF NOT EXISTS idx_entries_liq_deadline   ON entries(cape_liq_deadline);",
    "CREATE INDEX IF NOT EXISTS idx_entries_liq_status     ON entries(liquidation_status);",
    "CREATE INDEX IF NOT EXISTS idx_lines_entry            ON entry_lines(entry_summary_number);",
    "CREATE INDEX IF NOT EXISTS idx_claims_entry           ON claims(entry_summary_number);",
    "CREATE INDEX IF NOT EXISTS idx_actions_entry          ON entry_actions(entry_summary_number);",
]


def resolve_db_path() -> Path:
    """Return the active DB path. Order: env var > shared share (if reachable) > local."""
    env = os.environ.get("CAPEVIEW_DB_PATH")
    if env:
        return Path(env)
    if Path(SHARED_DB_PATH).parent.exists():
        return Path(SHARED_DB_PATH)
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return LOCAL_DB_PATH


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL + foreign keys enabled."""
    path = Path(db_path) if db_path else resolve_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Context manager wrapping an explicit BEGIN/COMMIT (rolls back on exception)."""
    conn.execute("BEGIN")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Create tables and indices if missing. Idempotent."""
    own_conn = conn is None
    conn = conn or connect()
    try:
        with transaction(conn):
            for stmt in SCHEMA_STATEMENTS:
                conn.execute(stmt)
        return conn
    finally:
        if own_conn and conn is not None:
            # Caller didn't pass a connection — leave it open for them anyway.
            pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


# ----------------------------------------------------------------------
# Upsert helpers used by ingestion jobs
# ----------------------------------------------------------------------

def upsert_claims(conn: sqlite3.Connection, rows: list[dict]) -> tuple[int, int]:
    """Upsert claim rows. Returns (inserted, updated).

    Each row needs keys: entry_summary_number, claim_number, status, error_description.
    Preserves first_seen on update; bumps last_seen.
    """
    inserted = 0
    updated = 0
    ts = now_iso()
    with transaction(conn):
        for row in rows:
            existing = conn.execute(
                "SELECT 1 FROM claims WHERE entry_summary_number = ? AND claim_number = ?",
                (row["entry_summary_number"], row["claim_number"]),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE claims SET status = ?, error_description = ?, last_seen = ?
                       WHERE entry_summary_number = ? AND claim_number = ?""",
                    (row.get("status"), row.get("error_description"), ts,
                     row["entry_summary_number"], row["claim_number"]),
                )
                updated += 1
            else:
                conn.execute(
                    """INSERT INTO claims (entry_summary_number, claim_number, status,
                                           error_description, first_seen, last_seen)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (row["entry_summary_number"], row["claim_number"], row.get("status"),
                     row.get("error_description"), ts, ts),
                )
                inserted += 1
    return inserted, updated


def upsert_entries(conn: sqlite3.Connection, rows: list[dict]) -> tuple[int, int]:
    """Upsert entry rows by entry_summary_number."""
    inserted = 0
    updated = 0
    ts = now_iso()
    columns = [
        "entry_summary_number", "importer_number", "importer_name", "div",
        "cape_phase1_eligible", "entry_type_code", "port_of_entry_code",
        "entry_date", "entry_summary_date", "initial_es_create_date",
        "reconciliation_indicator", "control_status", "psc_indicator",
        "liquidation_date", "liquidation_status", "final_liquidation_date",
        "cape_liq_deadline", "protest_number", "protest_status",
        "review_team_number", "country_of_origin_code", "country_of_export_code",
        "total_liquidated_duty",
    ]
    placeholders = ", ".join(["?"] * (len(columns) + 1))
    update_cols = ", ".join(f"{c} = ?" for c in columns[1:])
    insert_sql = f"INSERT INTO entries ({', '.join(columns)}, last_imported_at) VALUES ({placeholders})"
    update_sql = f"UPDATE entries SET {update_cols}, last_imported_at = ? WHERE entry_summary_number = ?"

    with transaction(conn):
        for row in rows:
            esn = row.get("entry_summary_number")
            if not esn:
                continue
            existing = conn.execute(
                "SELECT 1 FROM entries WHERE entry_summary_number = ?", (esn,)
            ).fetchone()
            values = [row.get(c) for c in columns]
            if existing:
                update_values = values[1:] + [ts, esn]
                conn.execute(update_sql, update_values)
                updated += 1
            else:
                conn.execute(insert_sql, values + [ts])
                inserted += 1
    return inserted, updated


def record_import_run(
    conn: sqlite3.Connection,
    source: str,
    source_file: str,
    rows_inserted: int,
    rows_updated: int,
    started_at: str,
    notes: str = "",
) -> int:
    """Append a row to import_runs. Returns row id."""
    cur = conn.execute(
        """INSERT INTO import_runs (source, source_file, rows_inserted, rows_updated,
                                    started_at, finished_at, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source, source_file, rows_inserted, rows_updated, started_at, now_iso(), notes),
    )
    return cur.lastrowid
