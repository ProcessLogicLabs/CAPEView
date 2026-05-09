"""Settings dialog for CAPEView.

Lets the user reconfigure the SQLite database location and seed a new
location with data from another existing database.

Layout
------
- "Database location" row: editable path + Browse + Test buttons.
- "Initialize from another database" group: pick a source path and copy
  the file (with WAL/SHM siblings) to the configured location. Useful for
  the first-time admin workflow of seeding the shared share from a
  freshly migrated local DB.

Save vs. apply
--------------
Saving rewrites ``settings.json``. The change requires a restart for any
already-open SQLite connections to pick up the new path; the dialog warns
about this on save.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from CAPEView import cape_database as db
from CAPEView.settings_manager import SettingsManager
from CAPEView.theme import style as button_style


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None,
                 settings: SettingsManager | None = None):
        super().__init__(parent)
        self.setWindowTitle("CAPEView Settings")
        self.resize(640, 360)
        self.settings = settings or SettingsManager()

        outer = QVBoxLayout(self)
        outer.setSpacing(14)

        outer.addWidget(self._build_database_group())
        outer.addWidget(self._build_seed_group())

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setStyleSheet(button_style("primary"))
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        outer.addStretch()
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    def _build_database_group(self) -> QGroupBox:
        group = QGroupBox("Database location")
        form = QFormLayout(group)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setText(self.settings.get("database.path", "") or "")
        self.path_edit.setPlaceholderText(
            r"e.g. \\192.168.115.99\scans\Dev\CAPEView\Database\cape.db"
        )
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        test_btn = QPushButton("Test")
        test_btn.setStyleSheet(button_style("info"))
        test_btn.clicked.connect(self._on_test)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_btn)
        path_row.addWidget(test_btn)
        form.addRow("Path:", path_row)

        self.resolved_label = QLabel(self._resolved_summary())
        self.resolved_label.setStyleSheet("color: #5A7079; font-size: 11px;")
        form.addRow("In effect:", self.resolved_label)

        helper = QLabel(
            "Leave blank to fall back to the shared share or local AppData. "
            "Override is per-user and lives in settings.json."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #5A7079; font-size: 11px;")
        form.addRow("", helper)
        return group

    def _build_seed_group(self) -> QGroupBox:
        group = QGroupBox("Initialize from another database (one-time seed)")
        form = QFormLayout(group)

        src_row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText(
            r"Source DB to copy from, e.g. %LOCALAPPDATA%\CAPEView\cape.db"
        )
        src_browse = QPushButton("Browse...")
        src_browse.clicked.connect(self._on_browse_source)
        src_row.addWidget(self.source_edit, 1)
        src_row.addWidget(src_browse)
        form.addRow("Source:", src_row)

        copy_btn = QPushButton("Copy now to the configured location")
        copy_btn.setStyleSheet(button_style("info"))
        copy_btn.clicked.connect(self._on_copy)
        form.addRow("", copy_btn)

        helper = QLabel(
            "Use this to seed a new shared database from your local one. "
            "The destination is the path above; any existing file there is "
            "overwritten after a confirmation prompt."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #5A7079; font-size: 11px;")
        form.addRow("", helper)
        return group

    # ------------------------------------------------------------------
    def _resolved_summary(self) -> str:
        try:
            return str(db.resolve_db_path())
        except Exception as e:  # pragma: no cover
            return f"(error: {e})"

    def _current_path(self) -> Path | None:
        text = self.path_edit.text().strip()
        return Path(text) if text else None

    # ----- handlers ----------------------------------------------------
    def _on_browse(self):
        start = self.path_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose database file",
            start,
            "SQLite database (*.db);;All files (*)",
            options=QFileDialog.DontConfirmOverwrite,
        )
        if path:
            self.path_edit.setText(path)

    def _on_browse_source(self):
        start = self.source_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pick source database",
            start,
            "SQLite database (*.db);;All files (*)",
        )
        if path:
            self.source_edit.setText(path)

    def _on_test(self):
        path = self._current_path()
        if path is None:
            QMessageBox.information(
                self, "Test connection",
                "No path set — leaving this blank uses the default fallback chain.",
            )
            return
        try:
            counts = _quick_counts(path)
            QMessageBox.information(
                self, "Test connection",
                f"OK — opened {path}\n\n"
                + "\n".join(f"  {k}: {v}" for k, v in counts.items()),
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Test connection",
                f"Could not open {path}:\n\n{e}",
            )

    def _on_copy(self):
        target = self._current_path()
        source_text = self.source_edit.text().strip()
        if target is None:
            QMessageBox.warning(self, "Copy database",
                                "Set a destination path first.")
            return
        if not source_text:
            QMessageBox.warning(self, "Copy database",
                                "Pick a source database to copy from.")
            return
        source = Path(source_text)
        if not source.exists():
            QMessageBox.critical(self, "Copy database",
                                 f"Source not found:\n{source}")
            return

        if target.exists():
            answer = QMessageBox.question(
                self, "Overwrite?",
                f"{target} already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            count = _copy_db(source, target)
            QMessageBox.information(
                self, "Copy database",
                f"Copied {count} file(s) from\n{source}\nto\n{target}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Copy failed", str(e))

    def _on_save(self):
        path_text = self.path_edit.text().strip()
        self.settings.set("database.path", path_text or None)

        try:
            self.settings.save()
        except Exception as e:
            QMessageBox.critical(self, "Save failed",
                                 f"Could not write settings:\n{e}")
            return
        QMessageBox.information(
            self, "Settings saved",
            "Settings updated.\n\nRestart CAPEView for any database-path "
            "change to take effect.",
        )
        self.accept()


# ---------------------------------------------------------------------------
# Helpers exported for the CLI utility too

def _quick_counts(path: Path) -> dict:
    """Open a DB read-only and return row counts of major tables."""
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        out = {}
        for table in ("entries", "entry_lines", "claims", "importer_status"):
            try:
                out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                out[table] = "—"
        return out
    finally:
        conn.close()


def _copy_db(source: Path, target: Path) -> int:
    """Copy a SQLite DB plus its WAL/SHM siblings to ``target``. Returns file count."""
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    for suffix in ("", "-wal", "-shm"):
        s = Path(str(source) + suffix)
        if not s.exists():
            continue
        d = Path(str(target) + suffix)
        shutil.copy2(s, d)
        count += 1
    if count == 0:
        raise FileNotFoundError(f"No source files found at {source}")
    return count
