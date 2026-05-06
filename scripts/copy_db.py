"""Copy a CAPEView SQLite database (plus its WAL/SHM siblings) to a new path.

Used to seed the shared share with data from a freshly migrated local DB:

  python scripts/copy_db.py ^
      --source "%LOCALAPPDATA%\\CAPEView\\cape.db" ^
      --target "\\\\192.168.115.99\\scans\\Dev\\CAPEView\\Database\\cape.db"

The script creates the target's parent directory if needed and refuses to
overwrite an existing target unless ``--force`` is passed. After the copy it
opens the destination read-only and prints major-table row counts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script without installing the package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from CAPEView.settings_dialog import _copy_db, _quick_counts  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True,
                    help="Source SQLite database to copy")
    ap.add_argument("--target", type=Path, required=True,
                    help="Destination path (parent dir created if missing)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing target")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"ERROR: source not found: {args.source}")

    if args.target.exists() and not args.force:
        sys.exit(f"ERROR: target exists (pass --force to overwrite): {args.target}")

    n = _copy_db(args.source, args.target)
    print(f"Copied {n} file(s) to {args.target}")

    counts = _quick_counts(args.target)
    print("Row counts at destination:")
    for table, count in counts.items():
        print(f"  {table:18} {count}")


if __name__ == "__main__":
    main()
