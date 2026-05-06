# CAPEView

Auto-updating desktop application for tracking CAPE Phase-1 entries, claim filings, and importer compliance status.

CAPEView replaces the manually-maintained `CAPE ESTIMATE` Excel workbook with a SQLite-backed application that:

- Ingests daily claim CSV exports automatically (no more rerunning VLOOKUPs)
- Pulls importer status (ACE, ACH, Self Filer, 4811 Client, 4811 PSCs) from upstream systems
- Tracks rejected-claim actions as a compliance trail
- Exports the legacy `CAPE ESTIMATE` workbook on demand for downstream consumers
- Auto-updates on launch via GitHub Releases

## Stack

- Python 3.12 + PyQt5
- SQLite (shared on `\\192.168.115.99\scans\cape.db`)
- openpyxl for xlsx I/O
- PyInstaller for single-exe distribution
- Inno Setup for the Windows installer
- Auto-updater modeled on the proven [open-tariffmill](https://github.com/ProcessLogicLabs/open-tariffmill) pattern

## Theme

Muted cyan base palette — see `CAPEView/theme.py`.

## Layout

```
CAPEView/
├── CAPEView/                # application package
│   ├── cape_view.py         # main GUI
│   ├── animated_splash.py   # muted-cyan splash widget
│   ├── auto_update.py       # GitHub Releases auto-updater
│   ├── theme.py             # MUTED_CYAN palette + button styles
│   ├── cape_database.py     # SQLite schema + queries
│   ├── claims_csv_ingest.py # daily CSV → claims table
│   ├── workbook_export.py   # generate legacy CAPE ESTIMATE xlsx
│   ├── version.py
│   ├── views/               # one .py per tab
│   └── Resources/           # icons, splash bitmap
├── scripts/
│   └── migrate_workbook.py  # one-time xlsx → cape.db migration
├── tests/
├── .github/workflows/
├── CAPEView.spec
├── CAPEView_setup.iss
├── pyproject.toml
└── requirements.txt
```

## Build

```powershell
pip install -r requirements.txt
pyinstaller CAPEView.spec
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" CAPEView_setup.iss
```

## Release

```powershell
git tag v0.0.2
git push origin v0.0.2
```

CI (`.github/workflows/release.yml`) builds the installer and publishes a GitHub Release. Running clients pick up the new version on next launch.
