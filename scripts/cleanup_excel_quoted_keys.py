"""One-shot cleanup for claims rows whose entry_summary_number / claim_number
were stored with Excel's ``="..."`` text-format wrapper.

Run once after upgrading to the version that handles the wrapper at ingest
time. Idempotent — re-running is safe.

Usage:
    python -m scripts.cleanup_excel_quoted_keys
    # or, with an explicit DB path
    CAPEVIEW_DB_PATH=C:\\path\\to\\cape.db python -m scripts.cleanup_excel_quoted_keys
"""

from __future__ import annotations

from CAPEView import cape_database as db


def main() -> int:
    conn = db.connect()
    db.init_db(conn)
    try:
        result = db.cleanup_excel_quoted_keys(conn)
    finally:
        conn.close()

    if result["updated"] == 0 and result["deleted_duplicates"] == 0:
        print("No polluted rows found — claims table is already clean.")
        return 0

    print(
        f"Cleanup complete: "
        f"updated {result['updated']} rows, "
        f"deleted {result['deleted_duplicates']} duplicates that already had a clean equivalent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
