"""Admin dialog — view & edit the access allowlist (auth_users.json).

Opened via Ctrl+Shift+A from the main window. Available to admins only,
or to anyone in bootstrap mode (no admins set yet). Saves directly to the
shared auth_users.json. Refuses to save a configuration that would lock
out the current user or leave the app with zero admins.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from CAPEView import auth
from CAPEView.theme import style as button_style


class AdminDialog(QDialog):
    """Editor for auth_users.json. Modal, table-driven."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CAPEView Access Administration")
        self.resize(620, 440)

        self._cfg = auth.load()
        self._current = auth.current_user()
        bootstrap = auth.is_bootstrap_mode(self._cfg)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(12)

        header_text = f"Logged in as <b>{self._current}</b>"
        if bootstrap:
            header_text += (
                "  &nbsp;&nbsp;<i style='color:#7A4A1B;'>"
                "(bootstrap mode — no admins set yet; save this dialog to lock down access)"
                "</i>"
            )
        header = QLabel(header_text)
        header.setStyleSheet("color: #1C323A; font-size: 12px;")
        outer.addWidget(header)

        # Add-row toolbar
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("New user (DOMAIN\\\\username):"))
        self._new_user = QLineEdit()
        self._new_user.setPlaceholderText("DMUSA\\\\jsmith")
        self._new_user.returnPressed.connect(self._add_user_clicked)
        add_row.addWidget(self._new_user, 1)
        self._add_admin_check = QCheckBox("admin")
        add_row.addWidget(self._add_admin_check)
        add_btn = QPushButton("Add")
        add_btn.setStyleSheet(button_style("secondary"))
        add_btn.clicked.connect(self._add_user_clicked)
        add_row.addWidget(add_btn)
        outer.addLayout(add_row)

        # User table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Domain User", "Admin", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # Explicit header QSS — Qt's native Windows style ignores QPalette here
        self.table.horizontalHeader().setStyleSheet(
            "QHeaderView::section {"
            "  background: #4E8C9B; color: #FFFFFF; padding: 6px 8px;"
            "  border: 0; font-weight: 600;"
            "}"
        )
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 100)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        admin_set = {auth._norm(a) for a in self._cfg.admins}
        for u in self._cfg.users:
            self._append_row(u, auth._norm(u) in admin_set)
        outer.addWidget(self.table, 1)

        # Save / Cancel
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(button_style("primary"))
        save_btn.clicked.connect(self._save_clicked)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(button_style("secondary"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

        # Footer
        footer = QLabel(f"<small style='color:#5A7079;'>Allowlist file: {auth.auth_path()}</small>")
        footer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(footer)

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------
    def _append_row(self, username: str, is_admin: bool):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(username))

        check = QCheckBox()
        check.setChecked(is_admin)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addStretch()
        wl.addWidget(check)
        wl.addStretch()
        self.table.setCellWidget(r, 1, wrap)

        remove_btn = QPushButton("Remove")
        remove_btn.setStyleSheet(button_style("secondary"))
        remove_btn.clicked.connect(lambda _, b=remove_btn: self._remove_row(b))
        self.table.setCellWidget(r, 2, remove_btn)

    def _row_admin_check(self, row: int) -> QCheckBox | None:
        wrap = self.table.cellWidget(row, 1)
        if wrap is None:
            return None
        return wrap.findChild(QCheckBox)

    def _remove_row(self, button):
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, 2) is button:
                self.table.removeRow(r)
                return

    def _add_user_clicked(self):
        name = self._new_user.text().strip()
        if not name:
            return
        # Reject duplicates (case-insensitive)
        existing = {auth._norm(self.table.item(r, 0).text()) for r in range(self.table.rowCount())}
        if auth._norm(name) in existing:
            QMessageBox.information(self, "Already added", f"{name} is already in the list.")
            return
        self._append_row(name, self._add_admin_check.isChecked())
        self._new_user.clear()
        self._add_admin_check.setChecked(False)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def _save_clicked(self):
        users: list[str] = []
        admins: list[str] = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            name = (item.text() if item else "").strip()
            if not name:
                continue
            users.append(name)
            check = self._row_admin_check(r)
            if check and check.isChecked():
                admins.append(name)

        # Validation: refuse a configuration that would lock everyone out
        if not admins:
            QMessageBox.warning(
                self, "Cannot save",
                "At least one user must be marked as admin. Otherwise nobody could "
                "edit this list again from inside the app.",
            )
            return

        cur_norm = auth._norm(self._current)
        if cur_norm not in {auth._norm(u) for u in users}:
            ans = QMessageBox.question(
                self, "Lock yourself out?",
                f"You ({self._current}) are not in the user list. Saving will "
                f"prevent you from launching CAPEView next time.\n\nContinue anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return

        try:
            auth.save(auth.AuthConfig(users=users, admins=admins))
        except OSError as e:
            QMessageBox.critical(
                self, "Save failed",
                f"Could not write the allowlist file:\n{e}\n\n"
                f"Path: {auth.auth_path()}",
            )
            return

        self.accept()
