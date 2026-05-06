"""Generic SQL-backed table view used by Entries / Claims / Importers tabs."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from CAPEView import cape_database as db
from CAPEView.theme import style as button_style


class SQLTableView(QWidget):
    """A read-only table that runs a SQL query and renders the results.

    Subclasses provide a title, headers, and a SQL builder that returns a
    (sql, params) tuple given the current filter text.
    """

    title = "Table"
    headers: list[str] = []
    placeholder = "Search..."

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        header_row = QHBoxLayout()
        title_label = QLabel(self.title)
        title_label.setFont(QFont("Segoe UI", 16, QFont.DemiBold))
        title_label.setStyleSheet("color: #1C323A;")
        header_row.addWidget(title_label)
        header_row.addStretch()

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.placeholder)
        self.filter_edit.setFixedWidth(260)
        self.filter_edit.returnPressed.connect(self.refresh)
        header_row.addWidget(self.filter_edit)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setStyleSheet(button_style("info"))
        self.refresh_button.clicked.connect(self.refresh)
        header_row.addWidget(self.refresh_button)
        outer.addLayout(header_row)

        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        outer.addWidget(self.table)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignRight)
        self.status.setStyleSheet("color: #5A7079; font-size: 11px;")
        outer.addWidget(self.status)

        self.refresh()

    # Override in subclasses --------------------------------------------------
    def build_query(self, filter_text: str) -> tuple[str, tuple]:
        raise NotImplementedError

    # ------------------------------------------------------------------
    def refresh(self):
        try:
            conn = db.connect()
            db.init_db(conn)
            sql, params = self.build_query(self.filter_edit.text().strip())
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    item = QTableWidgetItem("" if val is None else str(val))
                    self.table.setItem(r, c, item)
            self.table.resizeColumnsToContents()
            self.status.setText(f"{len(rows)} row(s)")
            conn.close()
        except Exception as e:
            self.status.setText(f"Query error: {e}")


class EntriesView(SQLTableView):
    title = "Entries"
    headers = [
        "Entry Summary #", "DIV", "CAPE", "Importer Name", "Importer #",
        "Liq Status", "Liq Date", "CAPE LIQ Deadline", "Total Liq Duty",
    ]
    placeholder = "Filter by importer or entry #..."

    def build_query(self, filter_text: str) -> tuple[str, tuple]:
        base = (
            "SELECT entry_summary_number, div, cape_phase1_eligible, importer_name, "
            "       importer_number, liquidation_status, liquidation_date, "
            "       cape_liq_deadline, total_liquidated_duty "
            "FROM entries "
        )
        if filter_text:
            base += (
                "WHERE entry_summary_number LIKE ? OR importer_name LIKE ? "
                "      OR importer_number LIKE ? "
            )
            like = f"%{filter_text}%"
            params = (like, like, like)
        else:
            params = ()
        base += "ORDER BY cape_liq_deadline ASC NULLS LAST LIMIT 1000"
        # SQLite doesn't support NULLS LAST natively; emulate it.
        base = base.replace(
            "ORDER BY cape_liq_deadline ASC NULLS LAST",
            "ORDER BY cape_liq_deadline IS NULL, cape_liq_deadline ASC",
        )
        return base, params


class ClaimsView(SQLTableView):
    title = "Claims"
    headers = ["Entry Summary #", "Claim #", "Status", "Error Description", "First Seen", "Last Seen"]
    placeholder = "Filter by entry, claim, or error..."

    def build_query(self, filter_text: str) -> tuple[str, tuple]:
        base = (
            "SELECT entry_summary_number, claim_number, status, error_description, "
            "       first_seen, last_seen "
            "FROM claims "
        )
        if filter_text:
            base += (
                "WHERE entry_summary_number LIKE ? OR claim_number LIKE ? "
                "      OR COALESCE(error_description,'') LIKE ? "
                "      OR COALESCE(status,'') LIKE ? "
            )
            like = f"%{filter_text}%"
            params = (like, like, like, like)
        else:
            params = ()
        base += "ORDER BY last_seen DESC LIMIT 1000"
        return base, params


class ComplianceView(SQLTableView):
    title = "Compliance — Rejected Claims Needing Action"
    headers = ["Entry Summary #", "Claim #", "Status", "Error Description", "Last Seen"]
    placeholder = "Filter by entry or error..."

    def build_query(self, filter_text: str) -> tuple[str, tuple]:
        base = (
            "SELECT c.entry_summary_number, c.claim_number, c.status, "
            "       c.error_description, c.last_seen "
            "FROM claims c "
            "WHERE UPPER(COALESCE(c.status,'')) = 'FAILED' "
            "  AND NOT EXISTS (SELECT 1 FROM entry_actions a "
            "                  WHERE a.entry_summary_number = c.entry_summary_number "
            "                  AND a.action_type = 'REJECTION_ACTIONED') "
        )
        params: tuple = ()
        if filter_text:
            base += "AND (c.entry_summary_number LIKE ? OR COALESCE(c.error_description,'') LIKE ?) "
            like = f"%{filter_text}%"
            params = (like, like)
        base += "ORDER BY c.last_seen DESC LIMIT 1000"
        return base, params


class ImportersView(SQLTableView):
    title = "Importers"
    headers = [
        "Importer #", "Importer Name", "Self Filer", "ACE", "ACH", "4811 Client",
        "PSC for 4811", "Last Synced",
    ]
    placeholder = "Filter by importer name or number..."

    def build_query(self, filter_text: str) -> tuple[str, tuple]:
        base = (
            "SELECT importer_number, importer_name, self_filer, ace_account, "
            "       ach_details_in_ace, is_4811_client, psc_for_4811, last_synced_at "
            "FROM importer_status "
        )
        if filter_text:
            base += "WHERE importer_number LIKE ? OR importer_name LIKE ? "
            like = f"%{filter_text}%"
            params = (like, like)
        else:
            params = ()
        base += "ORDER BY importer_name ASC LIMIT 1000"
        return base, params
