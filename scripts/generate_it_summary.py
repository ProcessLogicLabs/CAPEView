"""Generate a one-page IT-department summary PDF for CAPEView.

Re-runnable: each invocation rewrites docs/CAPEView_IT_Summary.pdf so the
PDF stays in sync with the latest version + feature set when changes ship.

Requires: fpdf2 (``pip install fpdf2``). Not added to requirements.txt
because PDF generation is a tooling concern, not a runtime dependency.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from CAPEView.version import get_version

# ---------------------------------------------------------------------------
# Palette - muted cyan, matching the app theme
PRIMARY = (78, 140, 155)        # #4E8C9B  cyan section bar
DARK_TEXT = (28, 50, 58)         # #1C323A  body text
MUTED_TEXT = (90, 112, 121)      # #5A7079  small captions
ACCENT_BG = (240, 248, 250)      # #F0F8FA  light cyan side note bg


SECTIONS: list[tuple[str, list[str]]] = [
    (
        "Executive Summary",
        [
            "CAPEView is a Windows desktop application used by Customs/Brokerage operations "
            "staff to track CAPE Phase-1 entries, claim filings, refund estimates, and "
            "importer compliance status. It replaces a 60 MB manually-maintained Excel "
            "workbook (\"CAPE ESTIMATE with LIQUIDATION DATE\") with a multi-user-safe SQLite "
            "database and a purpose-built UI. Same business data, faster, and editable "
            "concurrently without conflicts."
        ],
    ),
    (
        "Functional Overview",
        [
            "Nine tabs: Dashboard (live counts), Deadlines, Entries, Claims, Compliance, "
            "Refunds, Protests, Importers, Reports.",
            "Claims is the only editable tab (status, error description, notes); every edit "
            "is appended to an audit log keyed by entry+claim with the user's domain "
            "identity, timestamp, and old/new values.",
            "Drag-and-drop ingest of ACE Portal Claim Status CSVs directly from File "
            "Explorer or Outlook attachments.",
            "Per-tab export to xlsx or csv (Ctrl+E), preserving the user's filters and "
            "sort. Reports tab also regenerates the legacy CAPE ESTIMATE workbook on demand.",
        ],
    ),
    (
        "Architecture & Technology",
        [
            "Python 3.10+ application; PyQt5 GUI; SQLite (WAL) database; openpyxl for "
            "Excel I/O. No server, no listening ports - the app runs entirely client-side "
            "on each user's PC.",
            "Distributed as a single-EXE Windows installer built with PyInstaller + Inno "
            "Setup. Per-user install, no admin rights required.",
            "Source repository: github.com/ProcessLogicLabs/CAPEView (private). Releases "
            "are published as signed GitHub Release assets including a SHA256SUMS.txt "
            "checksum file.",
        ],
    ),
    (
        "Network Footprint",
        [
            "Inbound: none. The app does not listen on any port.",
            "Outbound HTTPS only:",
            "    - api.github.com - auto-update version checks and signed installer "
            "downloads from the public ProcessLogicLabs/CAPEView Releases.",
            "Internal LAN only:",
            "    - SMB to \\\\192.168.115.99\\scans\\Dev\\CAPEView\\Database\\cape.db "
            "(shared SQLite database) and auth_users.json (access allowlist) at the "
            "same path. Standard SMB over the existing office network.",
        ],
    ),
    (
        "Identity & Access Control",
        [
            "Identity is captured passively from the Windows session (USERDOMAIN\\USERNAME). "
            "No application login prompt - every domain user is already Kerberos-"
            "authenticated by Windows on logon, and that identity is what the app records "
            "for audit attribution.",
            "Authorization is gated by a small JSON allowlist (auth_users.json) on the "
            "shared CAPEView folder. Maintained by app admins through an in-app dialog "
            "(Ctrl+Shift+A) - adding or removing a user takes seconds and does not require "
            "IT involvement, AD group changes, or password resets.",
            "Bootstrap mode: when the allowlist is empty (fresh install), the first user "
            "to launch is treated as admin so they can lock down access from inside the app. "
            "Once at least one admin is set, the gate enforces the list on every launch.",
            "Audit: every user edit appends to an audit_log table with DOMAIN\\username, "
            "timestamp, table+row+field, and old/new values. CSV-driven status changes are "
            "also logged with user_id='csv_ingest' for clear separation.",
        ],
    ),
    (
        "Data",
        [
            "Source: CBP CAPE Phase-1 program data (entries, lines, importer compliance) "
            "originally exported from ACE Portal; ongoing claim status updates ingested "
            "from ACE Portal CSV exports.",
            "Storage: a single SQLite file (cape.db, currently ~50 MB; expected to grow "
            "modestly as claim history accumulates).",
            "Classification: business operational data - customs trade information. No "
            "PII, no payment instrument data, no regulatory restrictions beyond standard "
            "customs trade data handling.",
            "Backup: file-level. The shared cape.db should be included in the LAN share's "
            "existing backup rotation. The file is fully portable - copying it to a new "
            "location is a complete restore.",
        ],
    ),
    (
        "Deployment & Updates",
        [
            "Installer: CAPEView_Setup_<version>.exe published with each GitHub Release. "
            "User runs once; per-user install at %LOCALAPPDATA%\\Programs\\CAPEView. "
            "Wizard prompts for the database folder location during install.",
            "Updates: the app checks api.github.com on launch for newer releases and "
            "prompts the user to install. Update payload is verified against the published "
            "SHA256SUMS.txt before execution.",
            "Rollback: previous releases remain available in GitHub Releases; reinstalling "
            "an older Setup .exe is a complete downgrade.",
        ],
    ),
    (
        "Asks of IT",
        [
            "Confirm the LAN share \\\\192.168.115.99\\scans\\Dev\\CAPEView\\Database is "
            "included in the backup rotation.",
            "Confirm outbound HTTPS to api.github.com is permitted for the user "
            "population (typically already the case).",
            "No firewall rules, AD group provisioning, certificate issuance, or "
            "directory-service changes are required to deploy or operate the app.",
        ],
    ),
]


# ---------------------------------------------------------------------------
class SummaryPDF(FPDF):
    def header(self):
        # Title bar
        self.set_fill_color(*PRIMARY)
        self.rect(0, 0, self.w, 14, style="F")
        self.set_y(2)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, "CAPEView - IT Department Summary", align="L")
        self.set_xy(self.w - 50, 2)
        self.set_font("Helvetica", "", 10)
        self.cell(40, 10, get_version(), align="R")
        self.set_text_color(*DARK_TEXT)
        self.set_y(20)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MUTED_TEXT)
        self.cell(
            0, 8,
            f"CAPEView {get_version()}  -  ProcessLogicLabs, LLC  -  Page {self.page_no()}",
            align="C",
        )

    def section(self, title: str, paragraphs: list[str]):
        # Section heading bar
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*PRIMARY)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        # Thin underline
        self.set_draw_color(*PRIMARY)
        self.set_line_width(0.4)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(1.5)

        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*DARK_TEXT)
        for p in paragraphs:
            self.multi_cell(0, 4.6, p)
            self.ln(1.2)
        self.ln(2)


def build_pdf(out_path: Path) -> Path:
    pdf = SummaryPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=18, top=20, right=18)
    pdf.add_page()

    for title, paras in SECTIONS:
        pdf.section(title, paras)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return out_path


def main():
    repo_root = Path(__file__).resolve().parent.parent
    out = repo_root / "docs" / "CAPEView_IT_Summary.pdf"
    written = build_pdf(out)
    print(f"Wrote {written.relative_to(repo_root)}  ({written.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
