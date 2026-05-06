"""Reports tab — regenerate the legacy CAPE ESTIMATE workbook on demand."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from CAPEView import workbook_export
from CAPEView.theme import style as button_style


class ReportsView(QWidget):
    """Buttons that drive xlsx exports."""

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
        self.export_button = QPushButton("Export CAPE ESTIMATE workbook...")
        self.export_button.setStyleSheet(button_style("primary"))
        self.export_button.clicked.connect(self._on_export)
        button_row.addWidget(self.export_button)
        button_row.addStretch()
        outer.addLayout(button_row)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignLeft)
        self.status.setStyleSheet("color: #5A7079; font-size: 12px;")
        outer.addWidget(self.status)
        outer.addStretch()

    def _on_export(self):
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Save CAPE ESTIMATE workbook",
            str(Path.home() / "Documents" / "CAPE_ESTIMATE_export.xlsx"),
            "Excel Workbook (*.xlsx)",
        )
        if not target:
            return
        try:
            stats = workbook_export.export_cape_estimate(Path(target))
            self.status.setText(
                f"Exported to {target}  -  "
                f"entries: {stats['entries']}, lines: {stats['entry_lines']}, claims: {stats['claims']}"
            )
        except Exception as e:
            self.status.setText(f"Export failed: {e}")
