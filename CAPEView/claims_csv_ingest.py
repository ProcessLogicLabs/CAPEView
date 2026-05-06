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
            esn = (raw.get(col_map["entry_summary_number"]) or "").strip()
            claim = (raw.get(col_map["claim_number"]) or "").strip()
            if not esn or not claim:
                continue
            rows.append(
                {
                    "entry_summary_number": esn,
                    "claim_number": claim,
                    "status": (raw.get(col_map.get("status", "")) or "").strip() or None,
                    "error_description": (
                        raw.get(col_map.get("error_description", "")) or ""
                    ).strip() or None,
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
    return summary


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
