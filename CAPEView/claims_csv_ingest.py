"""Daily claims CSV ingestion job.

Watches a drop folder (default: ``\\\\192.168.115.99\\scans\\CAPE\\claims_inbox``)
for new CSV files. Each file is parsed, deduped against existing claims, upserted,
and archived into ``processed/YYYY-MM-DD/``.

Usage (one-shot):
    python -m CAPEView.claims_csv_ingest --once

Usage (Windows Task Scheduler — run hourly or daily):
    python -m CAPEView.claims_csv_ingest --once --inbox "\\\\192.168.115.99\\scans\\CAPE\\claims_inbox"

The ingest is idempotent. Re-running on the same files (or the same rows in
multiple files) is safe — duplicates are detected by ``(entry_summary_number,
claim_number)`` and update the existing row's ``last_seen`` and ``status``.

Expected CSV schema (case-insensitive header match):
    ENTRY_NUMBER, CLAIM_NUMBER, STATUS, ERROR_DESCRIPTION

Aliases handled:
    entry_summary_number  ~ entry_number, entry, entry_no, entry summary number
    claim_number          ~ cape_claim_number, claim no, claim
    status                ~ filing_status, claim_status
    error_description     ~ error, error detail, cape_error_detail
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from CAPEView import cape_database as db

DEFAULT_INBOX = Path(r"\\192.168.115.99\scans\CAPE\claims_inbox")

logger = logging.getLogger("capeview.claims_ingest")


HEADER_ALIASES = {
    "entry_summary_number": {
        "entry_summary_number", "entry_number", "entry", "entry_no",
        "entry summary number",
    },
    "claim_number": {
        "claim_number", "cape_claim_number", "claim_no", "claim",
        "cape claim number",
    },
    "status": {
        "status", "filing_status", "claim_status", "filing status",
    },
    "error_description": {
        "error_description", "error", "error_detail", "error detail",
        "cape_error_detail", "cape error detail",
    },
}


def _norm(s: str) -> str:
    return s.strip().lower().replace("-", "_").replace(" ", "_")


def _unwrap_excel_text(value: str | None) -> str:
    """Strip the ``="..."`` wrapper Excel uses to force a CSV cell to text.

    ACE Portal exports the Claim Details CSV with this wrapper around
    entry numbers and claim numbers so Excel won't auto-convert them to
    scientific notation. csv.DictReader passes the raw cell through, so
    we need to undo the escape ourselves before persisting.
    """
    if not value:
        return ""
    s = value.strip()
    if len(s) >= 3 and s.startswith('="') and s.endswith('"'):
        return s[2:-1]
    return s


def _resolve_columns(fieldnames: list[str]) -> dict[str, str]:
    """Map our canonical names to the CSV's actual column names."""
    norm_to_actual = {_norm(c): c for c in fieldnames}
    resolved: dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        norm_aliases = {_norm(a) for a in aliases}
        for n_alias in norm_aliases:
            if n_alias in norm_to_actual:
                resolved[canonical] = norm_to_actual[n_alias]
                break
    return resolved


def parse_csv(path: Path) -> list[dict]:
    """Read a CSV file into a list of canonical-keyed dicts."""
    rows: list[dict] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return rows
        col_map = _resolve_columns(list(reader.fieldnames))
        if "entry_summary_number" not in col_map or "claim_number" not in col_map:
            raise ValueError(
                f"{path.name}: required columns missing (need entry & claim). "
                f"Found: {reader.fieldnames}"
            )
        for raw in reader:
            esn = _unwrap_excel_text(raw.get(col_map["entry_summary_number"]))
            claim = _unwrap_excel_text(raw.get(col_map["claim_number"]))
            if not esn or not claim:
                continue
            rows.append(
                {
                    "entry_summary_number": esn,
                    "claim_number": claim,
                    "status": _unwrap_excel_text(raw.get(col_map.get("status", ""))) or None,
                    "error_description": _unwrap_excel_text(
                        raw.get(col_map.get("error_description", ""))
                    ) or None,
                }
            )
    return rows


def archive_file(src: Path, processed_root: Path) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_dir = processed_root / today
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / src.name

    # Avoid clobbering: append an index if the target already exists
    if target.exists():
        stem, suffix = target.stem, target.suffix
        for i in range(1, 1000):
            candidate = target_dir / f"{stem}.{i}{suffix}"
            if not candidate.exists():
                target = candidate
                break
    shutil.move(str(src), str(target))
    return target


def process_inbox(inbox: Path, processed: Path | None = None) -> dict:
    """Process every *.csv in the inbox once. Returns summary dict."""
    inbox.mkdir(parents=True, exist_ok=True)
    processed = processed or (inbox / "processed")
    processed.mkdir(parents=True, exist_ok=True)

    summary = {"files": 0, "rows": 0, "inserted": 0, "updated": 0, "errors": []}
    files = sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    if not files:
        logger.info("No CSV files in inbox: %s", inbox)
        return summary

    conn = db.connect()
    db.init_db(conn)

    for f in files:
        started = db.now_iso()
        try:
            rows = parse_csv(f)
            inserted, updated = db.upsert_claims(conn, rows)
            db.record_import_run(
                conn, "claims_csv", str(f),
                inserted, updated, started,
                notes=f"{len(rows)} rows parsed",
            )
            summary["files"] += 1
            summary["rows"] += len(rows)
            summary["inserted"] += inserted
            summary["updated"] += updated
            archived = archive_file(f, processed)
            logger.info("Ingested %s: %d rows (insert=%d update=%d) -> %s",
                        f.name, len(rows), inserted, updated, archived)
        except Exception as e:
            summary["errors"].append(f"{f.name}: {e}")
            logger.exception("Failed to ingest %s", f.name)

    conn.close()
    _maybe_send_digest(summary)
    return summary


def process_single_file(src: Path, inbox: Path | None = None) -> dict:
    """Copy ``src`` into the inbox, ingest just that file, and archive it.

    Used by the Dashboard drag-and-drop zone. Mirrors ``process_inbox`` for a
    single file: it does *not* sweep the inbox for other waiting CSVs, which
    keeps the drag-and-drop path race-free against the cron-driven sweep.

    Returns a summary dict shaped like ``process_inbox``'s return value.
    """
    src = Path(src)
    inbox = inbox or DEFAULT_INBOX
    inbox.mkdir(parents=True, exist_ok=True)
    processed = inbox / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    # Copy into inbox; collision-resolve with a UTC timestamp suffix.
    target = inbox / src.name
    if target.exists():
        stem, suffix = target.stem, target.suffix
        ts_suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = inbox / f"{stem}.{ts_suffix}{suffix}"
    shutil.copy2(str(src), str(target))

    summary = {"files": 0, "rows": 0, "inserted": 0, "updated": 0, "errors": []}

    conn = db.connect()
    db.init_db(conn)
    started = db.now_iso()
    try:
        rows = parse_csv(target)
        inserted, updated = db.upsert_claims(conn, rows)
        db.record_import_run(
            conn, "claims_csv_drop", str(target),
            inserted, updated, started,
            notes=f"{len(rows)} rows parsed (drag-and-drop)",
        )
        summary["files"] = 1
        summary["rows"] = len(rows)
        summary["inserted"] = inserted
        summary["updated"] = updated
        archive_file(target, processed)
        logger.info("Drop-zone ingested %s: %d rows (insert=%d update=%d)",
                    target.name, len(rows), inserted, updated)
    except Exception as e:
        summary["errors"].append(f"{target.name}: {e}")
        logger.exception("Drop-zone failed to ingest %s", target.name)
    finally:
        conn.close()
    _maybe_send_digest(summary)
    return summary


def _maybe_send_digest(summary: dict) -> None:
    """Send the Compliance digest after a successful ingest if email is enabled.

    Fires only when at least one row was inserted/updated. Never raises —
    a digest-send failure must not fail the ingest. Opens its own DB
    connection (the ingest connection is already closed by the time this is
    called) and reads ``email.enabled`` from settings.json via
    ``email_digest.send_compliance_digest_to_self``.
    """
    if (summary.get("inserted", 0) + summary.get("updated", 0)) == 0:
        return
    try:
        from CAPEView import email_digest
        from CAPEView.version import get_version
        conn = db.connect()
        try:
            db.init_db(conn)
            result = email_digest.send_compliance_digest(conn, get_version())
        finally:
            conn.close()
        if result.get("sent"):
            logger.info("Compliance digest sent to %s (%d rows)",
                        ", ".join(result.get("recipients", [])),
                        result.get("rows", 0))
        elif result.get("error"):
            logger.warning("Compliance digest skipped: %s", result["error"])
    except Exception:
        logger.exception("Compliance digest hook crashed; ingest result unaffected")


def watch(inbox: Path, interval_seconds: int = 60):
    logger.info("Watching %s every %ss (Ctrl-C to stop)", inbox, interval_seconds)
    while True:
        try:
            process_inbox(inbox)
        except KeyboardInterrupt:
            return
        except Exception:
            logger.exception("Error during ingest cycle")
        time.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX,
                        help=f"Folder to watch (default: {DEFAULT_INBOX})")
    parser.add_argument("--once", action="store_true",
                        help="Process all pending files and exit")
    parser.add_argument("--interval", type=int, default=60,
                        help="Watch interval in seconds (default 60)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.once:
        summary = process_inbox(args.inbox)
        print(f"Files: {summary['files']}  Rows: {summary['rows']}  "
              f"Inserted: {summary['inserted']}  Updated: {summary['updated']}")
        if summary["errors"]:
            print("Errors:")
            for err in summary["errors"]:
                print(f"  - {err}")
            sys.exit(1)
    else:
        watch(args.inbox, args.interval)


if __name__ == "__main__":
    main()
