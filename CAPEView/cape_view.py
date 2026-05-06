#!/usr/bin/env python3
# ==============================================================================
# CAPEView - CAPE Phase-1 Entry Tracking & Compliance
# ==============================================================================
# Copyright (c) 2026 Process Logic Labs, LLC
# Licensed under the MIT License. See LICENSE for details.
# ==============================================================================

import sys
import time

# Hide console window on Windows immediately at startup
if sys.platform == "win32":
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        user32.ShowWindow(hwnd, 0)

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from CAPEView import cape_database as db
from CAPEView.animated_splash import AnimatedMillSplash
from CAPEView.auto_update import AutoUpdateManager
from CAPEView.settings_dialog import SettingsDialog
from CAPEView.theme import apply_theme
from CAPEView.version import get_version
from CAPEView.views.dashboard import DashboardView
from CAPEView.views.reports import ReportsView
from CAPEView.views.table_view import (
    ClaimsView,
    ComplianceView,
    DeadlinesView,
    EntriesView,
    ImportersView,
    ProtestsView,
    RefundsView,
)

APP_NAME = "CAPEView"
VERSION = get_version()


class CAPEView(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1280, 800)

        self._build_menu()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)

        self.dashboard = DashboardView()
        self.deadlines = DeadlinesView()
        self.entries = EntriesView()
        self.claims = ClaimsView()
        self.compliance = ComplianceView()
        self.refunds = RefundsView()
        self.protests = ProtestsView()
        self.importers = ImportersView()
        self.reports = ReportsView()

        self.tabs.addTab(self.dashboard, "Dashboard")
        self.tabs.addTab(self.deadlines, "Deadlines")
        self.tabs.addTab(self.entries, "Entries")
        self.tabs.addTab(self.claims, "Claims")
        self.tabs.addTab(self.compliance, "Compliance")
        self.tabs.addTab(self.refunds, "Refunds")
        self.tabs.addTab(self.protests, "Protests")
        self.tabs.addTab(self.importers, "Importers")
        self.tabs.addTab(self.reports, "Reports")
        layout.addWidget(self.tabs)

        self.setCentralWidget(central)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._db_label = QLabel(f"DB: {db.resolve_db_path()}")
        self._db_label.setStyleSheet("color: #5A7079;")
        self.status_bar.addPermanentWidget(self._db_label)
        self.status_bar.showMessage(f"{APP_NAME} {VERSION} ready", 5000)

        self.update_manager = None

    # ------------------------------------------------------------------
    def _build_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menu_bar.addMenu("&Help")
        check_action = QAction("Check for updates...", self)
        check_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(check_action)
        about_action = QAction(f"About {APP_NAME}", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec_()
        # If they changed the DB path, refresh the status-bar display.
        self._db_label.setText(f"DB: {db.resolve_db_path()}")

    def _show_about(self):
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} {VERSION}</h3>"
            "<p>CAPE Phase-1 entry tracking and compliance tooling.</p>"
            "<p>Copyright (c) 2026 Process Logic Labs, LLC</p>",
        )

    # ------------------------------------------------------------------
    def check_for_updates(self, silent: bool = False):
        if self.update_manager is None:
            self.update_manager = AutoUpdateManager(self, VERSION)
        self.update_manager.check_for_updates(silent=silent)

    def check_for_updates_startup(self):
        """Called from a QTimer.singleShot a few seconds after the window is shown."""
        self.check_for_updates(silent=True)


# ==============================================================================
# Application entry point
# ==============================================================================

def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    apply_theme(app)
    app.setFont(QFont("Segoe UI", 10))

    splash = AnimatedMillSplash(APP_NAME, VERSION.lstrip("v"))
    splash.show()
    screen_geo = app.desktop().availableGeometry()
    splash.move(
        (screen_geo.width() - splash.width()) // 2,
        (screen_geo.height() - splash.height()) // 2,
    )
    splash.setText("Starting CAPEView...")
    app.processEvents()

    def animate_briefly():
        for _ in range(5):
            app.processEvents()
            time.sleep(0.016)

    init_steps = [
        ("Connecting to database...", 20),
        ("Applying schema...", 40),
        ("Building views...", 70),
        ("Almost ready...", 90),
    ]

    splash.setText(init_steps[0][0])
    splash.setProgress(init_steps[0][1])
    animate_briefly()
    conn = db.connect()
    db.init_db(conn)
    conn.close()

    splash.setText(init_steps[1][0])
    splash.setProgress(init_steps[1][1])
    animate_briefly()

    splash.setText(init_steps[2][0])
    splash.setProgress(init_steps[2][1])
    animate_briefly()
    win = CAPEView()
    animate_briefly()

    splash.setText(init_steps[3][0])
    splash.setProgress(init_steps[3][1])
    animate_briefly()

    splash.setText("Ready!")
    splash.setProgress(100)

    end = time.time() + 1.5
    while time.time() < end:
        app.processEvents()
        time.sleep(0.016)

    splash.fadeOut()

    win.move(
        (screen_geo.width() - win.width()) // 2,
        (screen_geo.height() - win.height()) // 2,
    )
    win.show()
    win.raise_()
    win.activateWindow()

    QTimer.singleShot(3000, win.check_for_updates_startup)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
