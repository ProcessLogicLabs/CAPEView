# CAPEView Changelog

All notable changes to CAPEView are tracked here. Format inspired by [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Initial scaffold: PyQt5 desktop app, muted-cyan theme, animated splash, GitHub-Releases auto-updater
- SQLite schema: `entries`, `entry_lines`, `claims`, `importer_status`, `entry_actions`, `audit_log`
- One-time migration script: legacy CAPE ESTIMATE xlsx -> cape.db
- Daily claims-CSV ingestion job
- Legacy workbook export (regenerates the CAPE ESTIMATE xlsx for downstream consumers)
- CI / Release workflows (lint+tests on PR; tag -> PyInstaller -> GitHub Release)
