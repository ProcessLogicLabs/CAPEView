# CAPEView Changelog

All notable changes to CAPEView are tracked here. Format inspired by [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Initial scaffold: PyQt5 desktop app, muted-cyan theme, animated splash, GitHub-Releases auto-updater
- SQLite schema: `entries`, `entry_lines`, `claims`, `importer_status`, `entry_actions`, `audit_log`
- One-time migration script: legacy CAPE ESTIMATE xlsx -> cape.db (now also seeds `importer_status` from Entry Count flag columns)
- Daily claims-CSV ingestion job
- Legacy workbook export (regenerates the CAPE ESTIMATE xlsx for downstream consumers)
- CI / Release workflows (lint+tests on PR; tag -> PyInstaller -> GitHub Release)
- **Deadlines view** — replaces "Entry Count Pivot": entries by importer × CAPE LIQ deadline week, with Phase-1 / claim-filed / Self Filer / 4811 filters and urgency row colors
- **Refunds view** — replaces "Refund Amount Pivot": Σ Line Tariff Duty by importer × liq status × CAPE Phase 1, with importer-status filters
- **Protests view** — replaces "PROTEST FILING PIVOT": entries by importer × Final Liq + 180 week, filterable by claim status, DIV, Self Filer, 4811 Client
- Importer-status filter dropdowns and urgency row coloring on Entries / Claims / Compliance tabs
- `workbook_export.py` now also regenerates the three pivot tabs as static grids
- `scripts/xlsx_audit.py` — forensic XML audit of any legacy CAPE workbook (sheets, named ranges, pivots, formulas, conditional formats)
- **Settings menu** (File → Settings, Ctrl+,) — change the shared SQLite location at runtime, with a "Test" button that opens the chosen DB read-only and reports row counts, plus an "Initialize from another database" section that copies a local DB to the configured location for first-time admin seeding
- `scripts/copy_db.py` — CLI equivalent of the dialog's copy action; used to seed the shared share from a freshly migrated local DB
- Default shared DB path moved to `\\192.168.115.99\scans\Dev\CAPEView\Database\cape.db` (was `\\...\scans\cape.db`) so CAPEView data lives alongside the other Dev/* projects on the share
