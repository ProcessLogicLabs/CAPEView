"""Reports tab — regenerate the legacy CAPE ESTIMATE workbook on demand."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from CAPEView import workbook_export
from CAPEView.theme import style as button_style


_BUTTON_LABEL = "Export CAPE ESTIMATE workbook..."


class _ExportWorker(QThread):
    """Runs ``workbook_export.export_cape_estimate`` off the GUI thread so
    the window stays responsive during the 5–30s xlsx generation."""

    finished_ok = pyqtSignal(dict, str)
    failed = pyqtSignal(str)

    def __init__(self, target: Path, parent=None):
        super().__init__(parent)
        self._target = target

    def run(self):
        try:
            stats = workbook_export.export_cape_estimate(self._target)
        except Exception as e:
            self.failed.emit(str(e))
        else:
            self.finished_ok.emit(stats, str(self._target))


class ReportsView(QWidget):
    """Buttons that drive xlsx exports."""

    # (message, timeout_ms) — main window connects to QStatusBar.showMessage
    status_message = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        title = QLabel("Reports")
        title.setFont(QFont("Segoe UI", 18, QFont.DemiBold))
        title.setStyleSheet("color: #1C323A;")
        outer.addWidget(title)

        explainer = QLabel(
            "Export the legacy CAPE ESTIMATE workbook from the live database. "
            "Use this for downstream consumers who still expect the Excel file."
        )
        explainer.setWordWrap(True)
        explainer.setStyleSheet("color: #28323A;")
        outer.addWidget(explainer)

        button_row = QHBoxLayout()
        self.export_button = QPushButton(_BUTTON_LABEL)
        self.export_button.setStyleSheet(button_style("primary"))
        self.export_button.clicked.connect(self._on_export)
        button_row.addWidget(self.export_button)
        button_row.addStretch()
        outer.addLayout(button_row)

        # Indeterminate busy bar — visible only while a worker is running.
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(8)
        self.progress.setStyleSheet(
            "QProgressBar { background: #E6F0F2; border: 1px solid #C9DEE2; border-radius: 4px; }"
            "QProgressBar::chunk { background: #5FA5B4; border-radius: 4px; }"
        )
        outer.addWidget(self.progress)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignLeft)
        self.status.setStyleSheet("color: #5A7079; font-size: 12px;")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        outer.addStretch()

        self._worker: _ExportWorker | None = None

    # ------------------------------------------------------------------
    def _on_export(self):
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Save CAPE ESTIMATE workbook",
            str(Path.home() / "Documents" / "CAPE_ESTIMATE_export.xlsx"),
            "Excel Workbook (*.xlsx)",
        )
        if not target:
            return

        self._set_running_state(target)

        self._worker = _ExportWorker(Path(target), self)
        self._worker.finished_ok.connect(self._on_export_done)
        self._worker.failed.connect(self._on_export_failed)
        # Tear down the QThread once it has emitted its result
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _set_running_state(self, target: str):
        self.export_button.setEnabled(False)
        self.export_button.setText("Exporting...")
        self.progress.setVisible(True)
        self.status.setStyleSheet("color: #1C323A; font-size: 12px;")
        self.status.setText(
            f"Generating workbook to {target}\n"
            f"This can take 5–30 seconds for the full live database."
        )
        self.status_message.emit("Exporting CAPE ESTIMATE workbook...", 0)

    def _set_idle_state(self):
        self.export_button.setEnabled(True)
        self.export_button.setText(_BUTTON_LABEL)
        self.progress.setVisible(False)

    def _on_export_done(self, stats: dict, target: str):
        self._set_idle_state()
        msg = (
            f"Exported to {target} — "
            f"entries: {stats['entries']}, lines: {stats['entry_lines']}, "
            f"claims: {stats['claims']}"
        )
        self.status.setStyleSheet("color: #1F5A2F; font-size: 12px;")
        self.status.setText("✔  " + msg)
        self.status_message.emit(msg, 8000)

    def _on_export_failed(self, msg: str):
        self._set_idle_state()
        self.status.setStyleSheet("color: #A4515A; font-size: 12px;")
        self.status.setText(f"Export failed: {msg}")
        self.status_message.emit(f"Export failed: {msg}", 8000)
