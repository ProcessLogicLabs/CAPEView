"""Dashboard tab — high-level CAPE program metrics.

Lightweight summary of the entries, claims, and protest workload. Pulls live
counts from cape.db on each refresh.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from CAPEView import cape_database as db
from CAPEView.theme import style as button_style


class StatCard(QFrame):
    """A single card showing a label + a big number."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #C9DEE2; border-radius: 6px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #5A7079; font-size: 11px; letter-spacing: 1px;")
        self.value_label = QLabel("—")
        f = QFont("Segoe UI", 22, QFont.DemiBold)
        self.value_label.setFont(f)
        self.value_label.setStyleSheet("color: #1C323A;")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(str(value) if value is not None else "—")


class DashboardView(QWidget):
    """Top-level dashboard tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("CAPE Phase-1 Dashboard")
        title.setFont(QFont("Segoe UI", 18, QFont.DemiBold))
        title.setStyleSheet("color: #1C323A;")
        header.addWidget(title)
        header.addStretch()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setStyleSheet(button_style("primary"))
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        outer.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards = {
            "entries":              StatCard("ENTRIES TRACKED"),
            "eligible":             StatCard("CAPE PHASE-1 ELIGIBLE"),
            "claims":               StatCard("CLAIMS ON FILE"),
            "claims_failed":        StatCard("CLAIMS WITH ERRORS"),
            "liq_due_30":           StatCard("LIQ DEADLINE ≤ 30 DAYS"),
            "rejected_open":        StatCard("REJECTED ENTRIES OPEN"),
        }
        items = list(self.cards.values())
        for i, card in enumerate(items):
            grid.addWidget(card, i // 3, i % 3)
        outer.addLayout(grid)

        outer.addStretch()

        # Status text used for transient errors only (success path leaves it empty)
        self._status = QLabel()
        self._status.setAlignment(Qt.AlignRight)
        self._status.setStyleSheet("color: #A4515A; font-size: 11px;")
        outer.addWidget(self._status)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        try:
            conn = db.connect()
            db.init_db(conn)
            self._status.setText("")

            self.cards["entries"].set_value(self._scalar(conn, "SELECT COUNT(*) FROM entries"))
            self.cards["eligible"].set_value(
                self._scalar(conn,
                             "SELECT COUNT(*) FROM entries WHERE UPPER(cape_phase1_eligible) = 'Y'")
            )
            self.cards["claims"].set_value(self._scalar(conn, "SELECT COUNT(*) FROM claims"))
            self.cards["claims_failed"].set_value(
                self._scalar(conn,
                             "SELECT COUNT(*) FROM claims WHERE error_description IS NOT NULL "
                             "AND TRIM(error_description) <> ''")
            )
            self.cards["liq_due_30"].set_value(
                self._scalar(conn,
                             "SELECT COUNT(*) FROM entries "
                             "WHERE cape_liq_deadline IS NOT NULL "
                             "AND date(cape_liq_deadline) BETWEEN date('now') AND date('now', '+30 day')")
            )
            self.cards["rejected_open"].set_value(
                self._scalar(conn,
                             "SELECT COUNT(*) FROM claims c "
                             "WHERE UPPER(COALESCE(c.status,'')) = 'FAILED' "
                             "AND NOT EXISTS (SELECT 1 FROM entry_actions a "
                             "                WHERE a.entry_summary_number = c.entry_summary_number "
                             "                AND a.action_type = 'REJECTION_ACTIONED')")
            )
            conn.close()
        except Exception as e:
            for card in self.cards.values():
                card.set_value("—")
            self._status.setText(f"Database error: {e}")

    @staticmethod
    def _scalar(conn, sql: str):
        cur = conn.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None
