"""Dashboard tab — high-level CAPE program metrics.

Lightweight summary of the entries, claims, and protest workload. Pulls live
counts from cape.db on each refresh. Also hosts the drag-and-drop zone for
ad-hoc claim CSV ingestion.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from CAPEView import cape_database as db
from CAPEView import claims_csv_ingest as ingest
from CAPEView import outlook_drop
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


class DropZone(QFrame):
    """Drag-and-drop target for a single Claim Status CSV file.

    Emits ``file_dropped(str)`` with the local path on a valid drop, or
    ``invalid_drop(str)`` with a user-facing reason otherwise.
    """

    file_dropped = pyqtSignal(str)
    invalid_drop = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(72)
        self._set_idle_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        self.label = QLabel("Drop a Claim Status CSV here to import")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #1C323A; font-size: 13px; background: transparent; border: none;")
        layout.addWidget(self.label)

    def _set_idle_style(self):
        self.setStyleSheet(
            "QFrame { background: #F0F8FA; border: 2px dashed #5FA5B4; border-radius: 8px; }"
        )

    def _set_hover_style(self):
        self.setStyleSheet(
            "QFrame { background: #D4ECF1; border: 2px dashed #2D7B8B; border-radius: 8px; }"
        )

    def dragEnterEvent(self, event):
        md = event.mimeData()
        # 1) Standard file drops from File Explorer
        if md.hasUrls():
            urls = md.urls()
            if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".csv"):
                self._set_hover_style()
                event.acceptProposedAction()
                return
        # 2) Outlook attachment drag — peek the filename from the OLE
        # FileGroupDescriptor without touching FileContents.
        name = self._peek_outlook_filename(md)
        if name and name.lower().endswith(".csv"):
            self._set_hover_style()
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_idle_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_idle_style()
        md = event.mimeData()

        # 1) Standard URL drops
        if md.hasUrls():
            urls = md.urls()
            if len(urls) > 1:
                self.invalid_drop.emit("Drop one file at a time.")
                event.ignore()
                return
            if urls:
                path = urls[0].toLocalFile()
                if not path.lower().endswith(".csv"):
                    self.invalid_drop.emit("Only .csv files are accepted.")
                    event.ignore()
                    return
                event.acceptProposedAction()
                self.file_dropped.emit(path)
                return

        # 2) Outlook attachment drop (OLE FileGroupDescriptor + FileContents)
        target = self._materialize_outlook_drop(md)
        if target is None:
            self.invalid_drop.emit("Drag did not include a recognizable file.")
            event.ignore()
            return
        if target.suffix.lower() != ".csv":
            self.invalid_drop.emit("Only .csv files are accepted.")
            event.ignore()
            return
        event.acceptProposedAction()
        self.file_dropped.emit(str(target))

    # ------------------------------------------------------------------
    # Outlook OLE helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _peek_outlook_filename(md) -> str | None:
        fgd_w = bytes(md.data(outlook_drop.FGD_W_FORMAT)) if md.hasFormat(outlook_drop.FGD_W_FORMAT) else None
        fgd_a = bytes(md.data(outlook_drop.FGD_A_FORMAT)) if md.hasFormat(outlook_drop.FGD_A_FORMAT) else None
        if not fgd_w and not fgd_a:
            return None
        return outlook_drop.peek_filename(fgd_w, fgd_a)

    @staticmethod
    def _materialize_outlook_drop(md) -> Path | None:
        fgd_w = bytes(md.data(outlook_drop.FGD_W_FORMAT)) if md.hasFormat(outlook_drop.FGD_W_FORMAT) else None
        fgd_a = bytes(md.data(outlook_drop.FGD_A_FORMAT)) if md.hasFormat(outlook_drop.FGD_A_FORMAT) else None
        if not md.hasFormat(outlook_drop.FC_FORMAT):
            return None
        contents = bytes(md.data(outlook_drop.FC_FORMAT))
        parsed = outlook_drop.parse_attachment(fgd_w, fgd_a, contents)
        if not parsed:
            return None
        filename, payload = parsed
        # Sanitize: strip path separators that some senders embed in cFileName
        safe_name = filename.replace("/", "_").replace("\\", "_") or "attachment.bin"
        tmpdir = Path(tempfile.mkdtemp(prefix="capeview_drop_"))
        target = tmpdir / safe_name
        target.write_bytes(payload)
        return target


class DashboardView(QWidget):
    """Top-level dashboard tab."""

    # (message, timeout_ms) — main window connects to QStatusBar.showMessage
    status_message = pyqtSignal(str, int)

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

        # Drop zone + result banner sit between the title and the cards
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._on_file_dropped)
        self.drop_zone.invalid_drop.connect(self._show_warning)
        outer.addWidget(self.drop_zone)

        self._banner = QLabel()
        self._banner.setAlignment(Qt.AlignCenter)
        self._banner.setVisible(False)
        outer.addWidget(self._banner)

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.timeout.connect(lambda: self._banner.setVisible(False))

        grid = QGridLayout()
        grid.setSpacing(12)
        # 4x2 layout: row 0 is volume/scope, row 1 is urgency/activity. The
        # corrections / regressions pair sits at the right of row 1 so the
        # complementary trend numbers read together.
        self.cards = {
            "entries":              StatCard("ENTRIES TRACKED"),
            "eligible":             StatCard("CAPE PHASE-1 ELIGIBLE"),
            "claims":               StatCard("CLAIMS ON FILE"),
            "claims_failed":        StatCard("CLAIMS WITH ERRORS"),
            "liq_due_30":           StatCard("LIQ DEADLINE ≤ 30 DAYS"),
            "rejected_open":        StatCard("REJECTED ENTRIES OPEN"),
            "corrections_7d":       StatCard("CORRECTIONS (7D)"),
            "regressions_7d":       StatCard("REGRESSIONS (7D)"),
        }
        items = list(self.cards.values())
        for i, card in enumerate(items):
            grid.addWidget(card, i // 4, i % 4)
        outer.addLayout(grid)

        outer.addStretch()

        # Status text used for transient errors only (success path leaves it empty)
        self._status = QLabel()
        self._status.setAlignment(Qt.AlignRight)
        self._status.setStyleSheet("color: #A4515A; font-size: 11px;")
        outer.addWidget(self._status)

        self.refresh()

    # ------------------------------------------------------------------
    # Drag-and-drop handlers
    # ------------------------------------------------------------------
    def _on_file_dropped(self, path: str):
        try:
            summary = ingest.process_single_file(Path(path))
        except Exception as e:
            self._show_warning(f"Ingest failed: {e}")
            return
        if summary["errors"]:
            self._show_warning("Ingest errors: " + "; ".join(summary["errors"]))
            return
        msg = (
            f"Imported {Path(path).name}: {summary['rows']} rows "
            f"({summary['inserted']} new, {summary['updated']} updated)"
        )
        self._show_success(msg)
        self.status_message.emit(msg, 8000)
        self.refresh()

    def _show_success(self, msg: str):
        self._banner.setText(msg)
        self._banner.setStyleSheet(
            "QLabel { background: #DBF0E2; color: #1F5A2F; "
            "border: 1px solid #7BB48A; border-radius: 6px; "
            "padding: 8px 12px; font-size: 12px; }"
        )
        self._banner.setVisible(True)
        self._banner_timer.start(8000)

    def _show_warning(self, msg: str):
        self._banner.setText(msg)
        self._banner.setStyleSheet(
            "QLabel { background: #FBE7CB; color: #7A4A1B; "
            "border: 1px solid #D9A763; border-radius: 6px; "
            "padding: 8px 12px; font-size: 12px; }"
        )
        self._banner.setVisible(True)
        self._banner_timer.start(6000)
        self.status_message.emit(msg, 6000)

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
            # Corrections in the last 7 days: distinct claims that the CSV
            # ingest transitioned out of a FAILED state. Source restricted to
            # csv_ingest so user edits in audit_log don't double-count.
            self.cards["corrections_7d"].set_value(
                self._scalar(conn,
                             "SELECT COUNT(DISTINCT row_key) FROM audit_log "
                             "WHERE table_name = 'claims' "
                             "  AND field = 'status' "
                             "  AND user_id = 'csv_ingest' "
                             "  AND UPPER(COALESCE(old_value,'')) = 'FAILED' "
                             "  AND UPPER(COALESCE(new_value,'')) <> 'FAILED' "
                             "  AND date(changed_at) >= date('now','-7 day')")
            )
            # Regressions: claims that transitioned INTO Failed in the last
            # 7 days — the inverse of CORRECTIONS, useful for spotting
            # upstream backsliding.
            self.cards["regressions_7d"].set_value(
                self._scalar(conn,
                             "SELECT COUNT(DISTINCT row_key) FROM audit_log "
                             "WHERE table_name = 'claims' "
                             "  AND field = 'status' "
                             "  AND user_id = 'csv_ingest' "
                             "  AND UPPER(COALESCE(old_value,'')) <> 'FAILED' "
                             "  AND UPPER(COALESCE(new_value,'')) = 'FAILED' "
                             "  AND date(changed_at) >= date('now','-7 day')")
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
