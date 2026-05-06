"""Generic SQL-backed table view with pluggable filters and per-row coloring.

Subclasses set ``title`` / ``headers`` / ``placeholder`` and override:

- ``build_query(filter_text, status_filters)`` -> (sql, params)
- (optional) ``status_filters`` -> list of FilterSpec to render as combos in the toolbar
- (optional) ``color_row(row_values)`` -> QColor or None for an urgency tint

The base class wires everything: filter text, combos, refresh button, header
QSS (Qt's native Windows style ignores QPalette for QHeaderView), row coloring.
"""

from __future__ import annotations

import getpass
import re
from dataclasses import dataclass
from datetime import date

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QComboBox,
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

# ---------------------------------------------------------------------------
# Filter spec — combo box wired into the SQL query

@dataclass
class FilterSpec:
    """Describes a dropdown filter rendered in the toolbar above the table.

    ``label``         — text shown next to the combo
    ``key``           — stable identifier; build_query receives a dict keyed by this
    ``options``       — list of (display_text, value) pairs. Value is whatever
                        build_query expects to bind into the SQL (often "Y", "N",
                        None, or "" for "all").
    ``default``       — initial value (must match one of the options' values)
    """
    label: str
    key: str
    options: list[tuple[str, object]]
    default: object = None


# Common Y/N filter options used by importer-status flags
YN_OPTIONS = [("Any", None), ("Yes", 1), ("No", 0), ("Unknown", "__null__")]
YN_TEXT_OPTIONS = [("Any", None), ("Yes", "Y"), ("No", "N")]


# ---------------------------------------------------------------------------
# Urgency colors — palette consistent with theme.py

URGENCY_OVERDUE = QColor(245, 210, 215)   # soft red
URGENCY_DUE_30  = QColor(252, 235, 196)   # amber
URGENCY_DUE_60  = QColor(252, 246, 220)   # pale amber
URGENCY_OK      = QColor(220, 240, 226)   # soft green
URGENCY_NEUTRAL = None


def _current_user() -> str:
    """Best-effort user attribution for audit_log. Auth wiring will replace this."""
    try:
        return getpass.getuser() or "local"
    except Exception:
        return "local"


_ISO_DATE_RE     = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_DATETIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::\d{2})?")


def format_cell(value) -> str:
    """Render any value for display. ISO dates/timestamps -> MM/DD/YYYY."""
    if value is None:
        return ""
    s = str(value)
    m = _ISO_DATE_RE.match(s)
    if m:
        y, mo, d = m.groups()
        return f"{int(mo)}/{int(d)}/{y}"
    m = _ISO_DATETIME_RE.match(s)
    if m:
        y, mo, d, hh, mm = m.groups()
        return f"{int(mo)}/{int(d)}/{y} {hh}:{mm}"
    return s


def deadline_urgency(deadline_iso: str | None, today: date | None = None) -> QColor | None:
    """Return a tint based on how close ``deadline_iso`` (YYYY-MM-DD) is to ``today``."""
    if not deadline_iso:
        return None
    today = today or date.today()
    try:
        d = date.fromisoformat(str(deadline_iso)[:10])
    except ValueError:
        return None
    delta = (d - today).days
    if delta < 0:
        return URGENCY_OVERDUE
    if delta <= 30:
        return URGENCY_DUE_30
    if delta <= 60:
        return URGENCY_DUE_60
    return URGENCY_NEUTRAL


# ---------------------------------------------------------------------------
# Base widget

class SQLTableView(QWidget):
    """A read-only table that runs a SQL query and renders the results."""

    title = "Table"
    headers: list[str] = []
    placeholder = "Search..."
    status_filters: list[FilterSpec] = []  # subclasses may override
    row_limit = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        # Title row
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

        # Filter combos row (only rendered if status_filters non-empty)
        self._filter_widgets: dict[str, QComboBox] = {}
        if self.status_filters:
            filter_row = QHBoxLayout()
            filter_row.setSpacing(12)
            for spec in self.status_filters:
                lbl = QLabel(f"{spec.label}:")
                lbl.setStyleSheet("color: #28323A; font-size: 12px;")
                combo = QComboBox()
                combo.setMinimumWidth(140)
                for display, value in spec.options:
                    combo.addItem(display, userData=value)
                if spec.default is not None:
                    for i, (_disp, val) in enumerate(spec.options):
                        if val == spec.default:
                            combo.setCurrentIndex(i)
                            break
                combo.currentIndexChanged.connect(self.refresh)
                self._filter_widgets[spec.key] = combo
                filter_row.addWidget(lbl)
                filter_row.addWidget(combo)
            filter_row.addStretch()
            outer.addLayout(filter_row)

        # Table
        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setStyleSheet(
            "QHeaderView::section {"
            "  background-color: #4E8C9B;"
            "  color: #FFFFFF;"
            "  padding: 6px 8px;"
            "  border: 0px;"
            "  border-right: 1px solid #3C7080;"
            "  font-weight: 600;"
            "}"
            "QHeaderView::section:hover { background-color: #5FA5B4; }"
            "QTableWidget { gridline-color: #C9DEE2; }"
            "QTableWidget::item:selected { background-color: #5FA5B4; color: #FFFFFF; }"
        )
        outer.addWidget(self.table)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignRight)
        self.status.setStyleSheet("color: #5A7079; font-size: 11px;")
        outer.addWidget(self.status)

        self.refresh()

    # ----- subclass hooks -----------------------------------------------------
    def build_query(self, filter_text: str, status_filters: dict[str, object]) -> tuple[str, tuple]:
        raise NotImplementedError

    def color_row(self, row_values: tuple) -> QColor | None:
        """Optional per-row tint. Default: no coloring."""
        return None

    # ----- helpers for subclasses ---------------------------------------------
    @staticmethod
    def yn_clause(column: str, value: object) -> tuple[str, tuple]:
        """Build a SQL WHERE clause fragment for a Y/N filter combo value."""
        if value is None:
            return "", ()
        if value == "__null__":
            return f" AND {column} IS NULL", ()
        return f" AND {column} = ?", (value,)

    # ----- main refresh -------------------------------------------------------
    def current_status_filters(self) -> dict[str, object]:
        return {key: combo.currentData() for key, combo in self._filter_widgets.items()}

    def refresh(self):
        try:
            conn = db.connect()
            db.init_db(conn)
            sql, params = self.build_query(
                self.filter_edit.text().strip(),
                self.current_status_filters(),
            )
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                tint = self.color_row(tuple(row))
                for c, val in enumerate(row):
                    item = QTableWidgetItem(format_cell(val))
                    if tint is not None:
                        item.setBackground(QBrush(tint))
                    self.table.setItem(r, c, item)
            self.table.resizeColumnsToContents()
            self.status.setText(f"{len(rows)} row(s)")
            conn.close()
        except Exception as e:
            self.status.setText(f"Query error: {e}")


# ===========================================================================
# Concrete views
# ===========================================================================

# Common importer-status filter specs reused across views
def _importer_filters() -> list[FilterSpec]:
    return [
        FilterSpec("Self Filer",  "self_filer",         YN_OPTIONS),
        FilterSpec("ACE",         "ace_account",        YN_OPTIONS),
        FilterSpec("ACH",         "ach_details_in_ace", YN_OPTIONS),
        FilterSpec("4811 Client", "is_4811_client",     YN_OPTIONS),
        FilterSpec("PSC 4811",    "psc_for_4811",       YN_OPTIONS),
    ]


def _apply_importer_filters(sql: str, params: list, status_filters: dict) -> tuple[str, list]:
    """Append AND clauses for any active importer-status filters.

    Assumes the calling SQL has already JOINed importer_status as ``i``
    and includes a WHERE 1=1 placeholder (or starts with WHERE).
    """
    for col in ("self_filer", "ace_account", "ach_details_in_ace",
                "is_4811_client", "psc_for_4811"):
        clause, p = SQLTableView.yn_clause(f"i.{col}", status_filters.get(col))
        sql += clause
        params.extend(p)
    return sql, params


class EntriesView(SQLTableView):
    title = "Entries"
    headers = [
        "Entry Summary #", "DIV", "CAPE", "Importer Name", "Importer #",
        "Liq Status", "Liq Date", "CAPE LIQ Deadline", "Total Liq Duty",
    ]
    placeholder = "Filter by importer or entry #..."
    status_filters = [
        FilterSpec("CAPE Eligible", "cape_eligible", YN_TEXT_OPTIONS),
    ] + _importer_filters()

    def build_query(self, filter_text, status_filters):
        sql = (
            "SELECT e.entry_summary_number, e.div, e.cape_phase1_eligible, e.importer_name, "
            "       e.importer_number, e.liquidation_status, e.liquidation_date, "
            "       e.cape_liq_deadline, e.total_liquidated_duty "
            "FROM entries e "
            "LEFT JOIN importer_status i ON i.importer_number = e.importer_number "
            "WHERE 1=1 "
        )
        params: list = []
        if filter_text:
            sql += ("AND (e.entry_summary_number LIKE ? OR e.importer_name LIKE ? "
                    "     OR e.importer_number LIKE ?) ")
            like = f"%{filter_text}%"
            params.extend([like, like, like])
        cape_val = status_filters.get("cape_eligible")
        if cape_val is not None:
            sql += "AND UPPER(COALESCE(e.cape_phase1_eligible,'')) = ? "
            params.append(str(cape_val).upper())
        sql, params = _apply_importer_filters(sql, params, status_filters)
        sql += ("ORDER BY e.cape_liq_deadline IS NULL, e.cape_liq_deadline ASC "
                f"LIMIT {self.row_limit}")
        return sql, tuple(params)

    def color_row(self, row):
        return deadline_urgency(row[7])  # cape_liq_deadline column


class ClaimsView(SQLTableView):
    """Claims table — Status / Error Description / Notes are user-editable.

    Edits set ``manual_override = 1`` so the next CSV ingest preserves the
    edit instead of clobbering it. Every change appends an ``audit_log`` row
    keyed by ``entry_summary_number|claim_number``.
    """

    title = "Claims"
    headers = [
        "Entry Summary #", "Claim #", "Status", "Error Description",
        "Notes", "Manual", "First Seen", "Last Seen",
    ]
    placeholder = "Filter by entry, claim, or error..."
    status_filters = [
        FilterSpec(
            "Status", "status",
            [("Any", None),
             ("Updated", "Entry Summary Updated"),
             ("Failed", "Failed")],
        ),
        FilterSpec(
            "Manual edits", "manual_override",
            [("Any", None), ("Edited only", 1), ("Untouched only", 0)],
        ),
    ]

    # Column indices that are user-editable (Status, Error Description, Notes)
    EDITABLE_COLUMNS = (2, 3, 4)
    # Maps column index -> claims-table field name (for the SQL UPDATE)
    EDITABLE_FIELD = {2: "status", 3: "error_description", 4: "notes"}

    def __init__(self, parent=None):
        super().__init__(parent)
        # Hook the model edit signal AFTER the base class created self.table
        self.table.itemChanged.connect(self._on_item_changed)
        self._suppress_changes = False

    def build_query(self, filter_text, status_filters):
        sql = (
            "SELECT entry_summary_number, claim_number, status, error_description, "
            "       COALESCE(notes,''), "
            "       CASE WHEN manual_override = 1 THEN 'Y' ELSE '' END, "
            "       first_seen, last_seen "
            "FROM claims WHERE 1=1 "
        )
        params: list = []
        status_val = status_filters.get("status")
        if status_val is not None:
            sql += "AND status = ? "
            params.append(status_val)
        manual_val = status_filters.get("manual_override")
        if manual_val is not None:
            sql += "AND manual_override = ? "
            params.append(int(manual_val))
        if filter_text:
            sql += ("AND (entry_summary_number LIKE ? OR claim_number LIKE ? "
                    "     OR COALESCE(error_description,'') LIKE ? "
                    "     OR COALESCE(notes,'') LIKE ?) ")
            like = f"%{filter_text}%"
            params.extend([like, like, like, like])
        sql += f"ORDER BY last_seen DESC LIMIT {self.row_limit}"
        return sql, tuple(params)

    def color_row(self, row):
        status = (row[2] or "").upper()
        if status == "FAILED":
            return URGENCY_OVERDUE
        if status == "ENTRY SUMMARY UPDATED":
            return URGENCY_OK
        return None

    # ----- editable behavior --------------------------------------------------
    def refresh(self):
        """Suppress itemChanged while we repopulate the table; otherwise the
        bulk insertion would fire a write per cell."""
        self._suppress_changes = True
        try:
            super().refresh()
            for r in range(self.table.rowCount()):
                for c in range(self.table.columnCount()):
                    item = self.table.item(r, c)
                    if item is None:
                        continue
                    flags = item.flags()
                    if c in self.EDITABLE_COLUMNS:
                        item.setFlags(flags | Qt.ItemIsEditable)
                    else:
                        item.setFlags(flags & ~Qt.ItemIsEditable)
        finally:
            self._suppress_changes = False

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._suppress_changes:
            return
        col = item.column()
        if col not in self.EDITABLE_COLUMNS:
            return
        row = item.row()
        esn_item = self.table.item(row, 0)
        claim_item = self.table.item(row, 1)
        if esn_item is None or claim_item is None:
            return
        field = self.EDITABLE_FIELD[col]
        new_value = item.text() or None

        try:
            conn = db.connect()
            db.init_db(conn)
            updated = db.update_claim_field(
                conn,
                entry_summary_number=esn_item.text(),
                claim_number=claim_item.text(),
                field=field,
                new_value=new_value,
                user_id=_current_user(),
            )
            conn.close()
        except Exception as e:
            self.status.setText(f"Save failed: {e}")
            return

        if updated:
            self.status.setText(
                f"Saved {field} on {esn_item.text()}/{claim_item.text()} "
                f"(by {_current_user()})"
            )
            # Reflect manual_override='Y' immediately without a full refresh
            manual_item = self.table.item(row, 5)
            if manual_item is not None:
                self._suppress_changes = True
                manual_item.setText("Y")
                self._suppress_changes = False


class ComplianceView(SQLTableView):
    title = "Compliance — Rejected Claims Needing Action"
    headers = ["Entry Summary #", "Claim #", "Status", "Error Description", "Last Seen", "Importer Name"]
    placeholder = "Filter by entry, error, or importer..."
    status_filters = _importer_filters()

    def build_query(self, filter_text, status_filters):
        sql = (
            "SELECT c.entry_summary_number, c.claim_number, c.status, "
            "       c.error_description, c.last_seen, e.importer_name "
            "FROM claims c "
            "LEFT JOIN entries e ON e.entry_summary_number = c.entry_summary_number "
            "LEFT JOIN importer_status i ON i.importer_number = e.importer_number "
            "WHERE UPPER(COALESCE(c.status,'')) = 'FAILED' "
            "  AND NOT EXISTS (SELECT 1 FROM entry_actions a "
            "                  WHERE a.entry_summary_number = c.entry_summary_number "
            "                  AND a.action_type = 'REJECTION_ACTIONED') "
        )
        params: list = []
        if filter_text:
            sql += ("AND (c.entry_summary_number LIKE ? "
                    "     OR COALESCE(c.error_description,'') LIKE ? "
                    "     OR COALESCE(e.importer_name,'') LIKE ?) ")
            like = f"%{filter_text}%"
            params.extend([like, like, like])
        sql, params = _apply_importer_filters(sql, params, status_filters)
        sql += f"ORDER BY c.last_seen DESC LIMIT {self.row_limit}"
        return sql, tuple(params)

    def color_row(self, _row):
        return URGENCY_OVERDUE  # everything in this view needs action


class ImportersView(SQLTableView):
    title = "Importers"
    headers = [
        "Importer #", "Importer Name", "Self Filer", "ACE", "ACH", "4811 Client",
        "PSC for 4811", "Last Synced",
    ]
    placeholder = "Filter by importer name or number..."
    status_filters = _importer_filters()

    def build_query(self, filter_text, status_filters):
        sql = (
            "SELECT i.importer_number, i.importer_name, i.self_filer, i.ace_account, "
            "       i.ach_details_in_ace, i.is_4811_client, i.psc_for_4811, i.last_synced_at "
            "FROM importer_status i "
            "WHERE 1=1 "
        )
        params: list = []
        if filter_text:
            sql += "AND (i.importer_number LIKE ? OR i.importer_name LIKE ?) "
            like = f"%{filter_text}%"
            params.extend([like, like])
        sql, params = _apply_importer_filters(sql, params, status_filters)
        sql += f"ORDER BY i.importer_name ASC LIMIT {self.row_limit}"
        return sql, tuple(params)


# ===========================================================================
# Pivot-style views
# ===========================================================================

class DeadlinesView(SQLTableView):
    """Replaces 'Entry Count Pivot' — entries grouped by importer × CAPE LIQ deadline week.

    Each row: (week_start, importer_name, count, soonest_in_week). Filterable by
    Phase-1 eligibility, claim status, and importer-status flags. Color tint
    follows the soonest deadline in that week.
    """

    title = "Deadlines (CAPE LIQ + 80)"
    headers = ["Week starting", "Importer Name", "Entries", "Soonest deadline", "Has CAPE Claim"]
    placeholder = "Filter by importer name..."
    status_filters = [
        FilterSpec("CAPE Eligible", "cape_eligible", YN_TEXT_OPTIONS, default="Y"),
        FilterSpec("Claim filed",   "claim_filed",
                   [("Any", None), ("Yes", "Y"), ("No", "N")]),
        FilterSpec("Self Filer",    "self_filer",         YN_OPTIONS),
        FilterSpec("4811 Client",   "is_4811_client",     YN_OPTIONS),
    ]
    row_limit = 5000

    def build_query(self, filter_text, status_filters):
        sql = (
            "SELECT date(e.cape_liq_deadline, 'weekday 0', '-6 days') AS week_start, "
            "       e.importer_name, "
            "       COUNT(*) AS n, "
            "       MIN(e.cape_liq_deadline) AS soonest, "
            "       CASE WHEN COUNT(c.claim_number) > 0 THEN 'Y' ELSE 'N' END AS has_claim "
            "FROM entries e "
            "LEFT JOIN claims c ON c.entry_summary_number = e.entry_summary_number "
            "LEFT JOIN importer_status i ON i.importer_number = e.importer_number "
            "WHERE e.cape_liq_deadline IS NOT NULL "
        )
        params: list = []
        cape_val = status_filters.get("cape_eligible")
        if cape_val is not None:
            sql += "AND UPPER(COALESCE(e.cape_phase1_eligible,'')) = ? "
            params.append(str(cape_val).upper())
        if filter_text:
            sql += "AND e.importer_name LIKE ? "
            params.append(f"%{filter_text}%")
        for col in ("self_filer", "is_4811_client"):
            clause, p = SQLTableView.yn_clause(f"i.{col}", status_filters.get(col))
            sql += clause
            params.extend(p)
        sql += ("GROUP BY week_start, e.importer_name "
                "HAVING 1=1 ")
        claim_val = status_filters.get("claim_filed")
        if claim_val == "Y":
            sql += "AND has_claim = 'Y' "
        elif claim_val == "N":
            sql += "AND has_claim = 'N' "
        sql += f"ORDER BY week_start ASC, n DESC LIMIT {self.row_limit}"
        return sql, tuple(params)

    def color_row(self, row):
        return deadline_urgency(row[3])  # soonest deadline


class RefundsView(SQLTableView):
    """Replaces 'Refund Amount Pivot' — Σ Line Tariff Duty by importer × liq status.

    Restricted to CAPE-eligible entries by default since that's the refund universe.
    """

    title = "Refund Estimate (CAPE-eligible duty paid)"
    headers = ["Importer Name", "Liq Status", "CAPE Phase 1", "Σ Line Duty", "Entries", "Lines"]
    placeholder = "Filter by importer name..."
    status_filters = [
        FilterSpec("CAPE Eligible", "cape_eligible", YN_TEXT_OPTIONS, default="Y"),
    ] + _importer_filters()
    row_limit = 5000

    def build_query(self, filter_text, status_filters):
        sql = (
            "SELECT e.importer_name, "
            "       e.liquidation_status, "
            "       e.cape_phase1_eligible, "
            "       ROUND(SUM(COALESCE(l.line_tariff_duty, 0)), 2) AS total_duty, "
            "       COUNT(DISTINCT e.entry_summary_number) AS n_entries, "
            "       COUNT(l.line_number) AS n_lines "
            "FROM entries e "
            "LEFT JOIN entry_lines l ON l.entry_summary_number = e.entry_summary_number "
            "LEFT JOIN importer_status i ON i.importer_number = e.importer_number "
            "WHERE 1=1 "
        )
        params: list = []
        cape_val = status_filters.get("cape_eligible")
        if cape_val is not None:
            sql += "AND UPPER(COALESCE(e.cape_phase1_eligible,'')) = ? "
            params.append(str(cape_val).upper())
        if filter_text:
            sql += "AND e.importer_name LIKE ? "
            params.append(f"%{filter_text}%")
        sql, params = _apply_importer_filters(sql, params, status_filters)
        sql += ("GROUP BY e.importer_name, e.liquidation_status, e.cape_phase1_eligible "
                "ORDER BY total_duty DESC "
                f"LIMIT {self.row_limit}")
        return sql, tuple(params)


class ProtestsView(SQLTableView):
    """Replaces 'PROTEST FILING PIVOT' — entries by importer × Final Liq Date (LIQ+180) week.

    The protest deadline is 180 days after liquidation; this view shows the
    weekly distribution of entries reaching that mark, with filters mirroring
    the workbook's page filters.
    """

    title = "Protests (Final Liquidation + 180)"
    headers = ["Final-Liq week", "Importer Name", "Entries", "Soonest Final-Liq", "Has CAPE Claim"]
    placeholder = "Filter by importer name..."
    status_filters = [
        FilterSpec("Claim filed",  "claim_filed",
                   [("Any", None), ("Yes", "Y"), ("No", "N")]),
        FilterSpec("DIV",          "div",
                   [("Any", None), ("HOUSTON", "HOUSTON"), ("LOS ANGELES", "LOS ANGELES"),
                    ("ATLANTA", "ATLANTA")]),
        FilterSpec("Self Filer",   "self_filer",         YN_OPTIONS),
        FilterSpec("4811 Client",  "is_4811_client",     YN_OPTIONS),
    ]
    row_limit = 5000

    def build_query(self, filter_text, status_filters):
        sql = (
            "SELECT date(e.final_liquidation_date, 'weekday 0', '-6 days') AS week_start, "
            "       e.importer_name, "
            "       COUNT(*) AS n, "
            "       MIN(e.final_liquidation_date) AS soonest, "
            "       CASE WHEN COUNT(c.claim_number) > 0 THEN 'Y' ELSE 'N' END AS has_claim "
            "FROM entries e "
            "LEFT JOIN claims c ON c.entry_summary_number = e.entry_summary_number "
            "LEFT JOIN importer_status i ON i.importer_number = e.importer_number "
            "WHERE e.final_liquidation_date IS NOT NULL "
        )
        params: list = []
        if filter_text:
            sql += "AND e.importer_name LIKE ? "
            params.append(f"%{filter_text}%")
        div_val = status_filters.get("div")
        if div_val:
            sql += "AND UPPER(COALESCE(e.div,'')) = ? "
            params.append(str(div_val).upper())
        for col in ("self_filer", "is_4811_client"):
            clause, p = SQLTableView.yn_clause(f"i.{col}", status_filters.get(col))
            sql += clause
            params.extend(p)
        sql += "GROUP BY week_start, e.importer_name HAVING 1=1 "
        claim_val = status_filters.get("claim_filed")
        if claim_val == "Y":
            sql += "AND has_claim = 'Y' "
        elif claim_val == "N":
            sql += "AND has_claim = 'N' "
        sql += f"ORDER BY week_start ASC, n DESC LIMIT {self.row_limit}"
        return sql, tuple(params)

    def color_row(self, row):
        return deadline_urgency(row[3])
