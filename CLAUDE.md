# CAPEView — Claude project guide

CAPEView is a PyQt5 desktop application that replaces the legacy
`CAPE ESTIMATE with LIQUIDATION DATE` Excel workbook. The workbook tracked
CAPE Phase-1 entries, claim filings, and importer compliance status across
35K entries × 200K tariff lines. CAPEView migrates that data into SQLite,
auto-ingests daily claim CSVs, and surfaces the workbook's three pivots
(Refund Amount, Protest Filing, Entry Count) as live application views.

The repo lives at `git@github.com:ProcessLogicLabs/CAPEView.git`.
Sibling projects in the same DevHouston tree:
[`../open-tariffmill`](../open-tariffmill/) (the look-and-feel template),
PartsBuilder, CHPWorkViewer, OCRMill, XMLGenMill.

## Stack

- **Python 3.10+**, **PyQt5** (matches open-tariffmill — do **not** use PySide6)
- **SQLite** with WAL on `\\192.168.115.99\scans\Dev\CAPEView\Database\cape.db`
  (override via the `CAPEVIEW_DB_PATH` env var, or the in-app **File →
  Settings** dialog which writes `database.path` into `settings.json`).
  Resolution priority: env var > settings.json > shared share if reachable
  > `%LOCALAPPDATA%\CAPEView\cape.db` fallback.
- **openpyxl** for xlsx I/O — read-only mode for large sheets to avoid OOM
- **PyInstaller** + **Inno Setup** for distribution
- **GitHub Releases** auto-updater modeled on open-tariffmill's `auto_update.py`

Don't introduce new frameworks (no FastAPI, no React, no Power BI). The
"closest existing pattern" is always open-tariffmill — read it before
inventing something new.

## Layout

```
CAPEView/                 # Python package
├── cape_view.py          # Main GUI entry point
├── version.py            # __fallback_version__, set by CI on tag
├── animated_splash.py    # Muted-cyan splash widget
├── auto_update.py        # Targets ProcessLogicLabs/CAPEView releases
├── theme.py              # MUTED_CYAN palette + format helpers
├── cape_database.py      # SQLite connection, schema, queries, upserts
├── claims_csv_ingest.py  # Daily CSV drop-folder ingestion
├── settings_manager.py   # JSON settings store (settings.json)
├── settings_dialog.py    # File -> Settings dialog (DB path + seed copy)
├── workbook_export.py    # Regenerates the legacy CAPE ESTIMATE xlsx
└── views/
    ├── dashboard.py
    ├── reports.py
    └── table_view.py     # SQLTableView base + 7 concrete views
scripts/
├── migrate_workbook.py   # One-time xlsx -> cape.db
├── copy_db.py            # CLI: copy a local cape.db to the shared share
└── xlsx_audit.py         # Forensic audit (sheets/formulas/pivots/CF)
tests/                    # pytest, no Qt imports needed for most tests
.github/workflows/        # ci.yml + release.yml
CAPEView.spec, CAPEView_setup.iss, pyproject.toml, requirements.txt
```

## Conventions

### Database

- Schema is in `cape_database.SCHEMA_STATEMENTS` (idempotent CREATE TABLE
  IF NOT EXISTS) plus `COLUMN_ADDITIONS` (idempotent ALTER TABLE ADD COLUMN
  with duplicate-column errors swallowed). Add new columns to
  `COLUMN_ADDITIONS`, never break the existing schema list.
- All connections go through `cape_database.connect()` which sets WAL,
  `busy_timeout=30000`, foreign keys on. Don't open `sqlite3.connect()`
  directly elsewhere.
- Wrap multi-row writes in `with cape_database.transaction(conn):` — it
  uses an explicit BEGIN/COMMIT and rolls back on exception.
- Use `cape_database.now_iso()` for timestamps (UTC, seconds precision).

### Business rules — easy to get wrong

- **`cape_liq_deadline` is computed** in Python from `liquidation_date + 80
  days` and is `NULL` when liq is `NULL`. **Do not trust the workbook's Z
  column** (`=V+80`) — for unliquidated entries V is blank so the formula
  evaluates to `0+80 = 80` which Excel renders as `1900-03-20`. The
  migration's `_liq_plus_days` helper handles this correctly.
- **`final_liquidation_date`** in the workbook **is** correct (it's not a
  formula). Read it directly.
- **`claims.manual_override = 1`** locks user-edited rows from the daily
  CSV ingest. `upsert_claims` checks this flag and only updates `last_seen`
  for overridden rows. Every user edit also appends an `audit_log` row.
- **Importer-status flags** (`self_filer`, `ace_account`, `ach_details_in_ace`,
  `is_4811_client`, `psc_for_4811`) are stored as **INTEGER 0/1** for
  fast filtering; rendered as **Y/N** by `format_flag()` and the
  workbook export uses `CASE WHEN col=1 THEN 'Y' …` to match the legacy file.

### GUI / table views

- Tabular views inherit from `SQLTableView` (`views/table_view.py`).
  Subclasses set:
  - `title`, `headers`, `placeholder` (text filter prompt)
  - `status_filters: list[FilterSpec]` for combobox filters
  - `currency_columns: list[int]` to render USD via `format_usd`
  - `flag_columns: list[int]` to render 0/1 as Y/N via `format_flag`
  - `row_limit` (default 1000; pivot views use 5000)
- Override `build_query(filter_text, status_filters)` returning a
  `(sql, params)` tuple. Use `_apply_importer_filters` for the standard
  importer-status combos.
- Override `color_row(row)` to return a `QColor` for urgency tinting.
  `deadline_urgency(iso_date_str)` is the standard mapping (overdue = red,
  ≤30d = amber, ≤60d = pale amber, else neutral).
- Date display: every cell goes through `format_cell()`, which converts
  ISO `YYYY-MM-DD` → `M/D/YYYY` and ISO timestamps → `M/D/YYYY HH:MM`.
- Header QSS is set explicitly on every table — Qt's native Windows
  style ignores `QPalette` for `QHeaderView`, which produces invisible
  white-on-white headers without the override.

### Editable claims

- `update_claim_field(conn, esn, claim, field, value, user_id)` is the
  **only** way to user-edit a claim. Allowed fields: `status`,
  `error_description`, `notes`. Other fields raise `ValueError`.
- `ClaimsView` hooks `QTableWidget.itemChanged` and calls
  `update_claim_field` per edit. The `_suppress_changes` guard prevents
  the bulk-repopulate in `refresh()` from firing one save per cell.
- User identity for `audit_log.user_id` currently comes from
  `getpass.getuser()`. Replace with auth-managed identity once auth is
  wired (the open-tariffmill `auth_users.json` pattern is the planned
  source).

### Tests

- 60+ tests, all passing. Run with `python -m pytest -q`.
- Most tests **don't import PyQt5** — `cape_database`, `claims_csv_ingest`,
  and the SQL-building methods on view classes are all pure Python and
  reachable without Qt. Tests that need PyQt5 use `pytest.importorskip`.
- Don't write Qt-instantiation tests for views (they need a `QApplication`
  fixture that's brittle in CI). Test the SQL via the `_run_view` helper
  pattern in `tests/test_pivot_queries.py`: build a fake object, call
  `view_cls.build_query(fake, filter_text, filters_dict)`, run the SQL.
- All `format_*` helpers (`format_cell`, `format_usd`, `format_flag`) have
  parametrized test coverage. Add cases when extending them.

### CI / releases

- `.github/workflows/ci.yml`: lint (ruff) + test (pytest) on PR.
- `.github/workflows/release.yml`: tag `v*` triggers PyInstaller build,
  Inno Setup install build, and a GitHub Release with `.exe` and
  `SHA256SUMS.txt`. **The release.yml injects `__fallback_version__` into
  `version.py` from the tag** before running PyInstaller — don't try to
  bump `version.py` manually.
- Asset naming convention: `CAPEView_Setup_<version>.exe` (the
  `INSTALLER_PREFIX` constant in `auto_update.py` looks for `CAPEView_Setup`
  in the asset name).
- `v0.0.1` has not been tagged yet. When tagging, push tags to `main`
  via `git push origin v0.0.x`.

## Patterns to copy from open-tariffmill

The closest neighbor with the most reusable code is
[`../open-tariffmill/Tariffmill/`](../open-tariffmill/Tariffmill/). Files
adapted into CAPEView:

- `tariffmill.py` → `cape_view.py` (main GUI shell, splash wiring, init steps)
- `animated_splash.py` → `animated_splash.py` (re-skinned to muted cyan)
- `auto_update.py` → `auto_update.py` (retargeted at `ProcessLogicLabs/CAPEView`)
- `tariffmill.spec` → `CAPEView.spec`
- `tariffmill_setup.iss` → `CAPEView_setup.iss`
- `version.py` → `version.py`

When adding a new app-level feature (settings dialog, keyboard shortcuts,
menu items, etc.), check open-tariffmill first — it likely has a working
pattern that just needs adapting.

## Common operations

```powershell
# Install deps
pip install -r requirements.txt

# Migrate the legacy workbook into a local DB
$env:CAPEVIEW_DB_PATH = "$env:LOCALAPPDATA\CAPEView\cape.db"
python scripts/migrate_workbook.py

# Seed the shared share from that local DB (admin one-time)
python scripts/copy_db.py `
    --source "$env:LOCALAPPDATA\CAPEView\cape.db" `
    --target "\\192.168.115.99\scans\Dev\CAPEView\Database\cape.db"

# Run the app against that DB
python -m CAPEView

# Run the daily claims ingester once over a folder
python -m CAPEView.claims_csv_ingest --once --inbox C:\path\to\inbox

# Regenerate the legacy CAPE ESTIMATE xlsx from cape.db
python -m CAPEView.workbook_export --out export.xlsx

# Forensic audit of any CAPE ESTIMATE workbook
python scripts/xlsx_audit.py --xlsx path\to\workbook.xlsx

# Build the .exe (and installer)
pyinstaller --noconfirm --clean CAPEView.spec
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /dMyAppVersion=0.0.x CAPEView_setup.iss
```

## Watch-outs

- `data_only=False` on a 200K-row `Main Report` workbook OOMs (8+ GB).
  Use `read_only=True` whenever possible; `xlsx_audit.py` does sampled
  formula scanning on the read-only loader for this reason.
- The legacy workbook's `Claim details` reports `max_row=16881` via
  openpyxl but only **9,984** rows are populated. The high `max_row` is
  artifact of stale formulas/format extents. Iterate skipping blanks; do
  **not** treat the reported max as authoritative.
- The autofilter range on Entry Count is set to row 70,805 even though
  only 35,415 are populated. Same reason. Don't trust autofilter ranges
  as row counts.
- The legacy workbook has **3 PivotTables, 1 Table, 0 macros, 0 Power
  Query**, 0 conditional formats, 0 data validations. Every "calculation"
  in the file is either a VLOOKUP or `=V+80`. CAPEView replaces all of it.

## Files of last resort

If something is unclear, the audit script writes a complete inventory:

```powershell
python scripts/xlsx_audit.py > audit.txt
```

That gives you sheets, named ranges, pivot definitions, pivot caches,
slicers, charts, macros, conditional formats, data validations, autofilter
ranges, and sampled formulas — everything CAPEView replaces.
