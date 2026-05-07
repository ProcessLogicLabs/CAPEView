"""Generate a user-facing quick-start PDF for CAPEView.

Audience: customs brokerage staff who use CAPEView day-to-day. Goal is
"productive in 5 minutes". Output: docs/CAPEView_User_QuickStart.pdf.

Re-runnable; rewrites the PDF on each invocation. Requires fpdf2
(``pip install fpdf2``) — a tooling-only dependency, not in
requirements.txt.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from CAPEView.version import get_version

PRIMARY = (78, 140, 155)
DARK_TEXT = (28, 50, 58)
MUTED_TEXT = (90, 112, 121)
ACCENT = (245, 156, 70)


SECTIONS: list[tuple[str, list[str]]] = [
    (
        "Welcome",
        [
            "CAPEView replaces the old CAPE ESTIMATE Excel workbook. Same data, "
            "but it stays current automatically and several people can use it at "
            "once without stepping on each other's edits.",
            "All you need is a Windows login on the office network. The app uses "
            "your existing Windows identity - there is no separate password.",
        ],
    ),
    (
        "First launch",
        [
            "Open CAPEView from the Start menu. The first time you launch you'll "
            "see your name in the bottom status bar (e.g. \"signed in as "
            "DMUSA\\YourName\"). If you see an Access Denied message instead, ask "
            "your CAPEView admin to add you - they can do it in under 30 seconds "
            "from inside the app.",
        ],
    ),
    (
        "The Dashboard - at a glance",
        [
            "Eight summary cards in two rows give you the state of CAPE at a "
            "glance. Click Refresh in the top right to pull fresh counts.",
            "Row 1 (volumes): ENTRIES TRACKED, CAPE PHASE-1 ELIGIBLE, "
            "CLAIMS ON FILE, CLAIMS WITH ERRORS.",
            "Row 2 (urgency + activity): LIQ DEADLINE <= 30 DAYS, REJECTED "
            "ENTRIES OPEN (claims still in Failed status with no follow-up "
            "action recorded), CORRECTIONS (7D) (claims that moved out of "
            "Failed in the last week - upstream fixed them), NEW REJECTS (7D) "
            "(claims that moved INTO Failed in the last week - new problems).",
        ],
    ),
    (
        "Importing Claim Status CSVs",
        [
            "When ACE Portal sends you a Claim Details CSV (the file with "
            "ENTRY_NUMBER, CLAIM_NUMBER, STATUS, ERROR_DESCRIPTION columns), "
            "drop it into the dashed cyan zone at the top of the Dashboard tab.",
            "You can drag straight from File Explorer or from an Outlook "
            "attachment - no need to save the attachment to disk first.",
            "When the import finishes you'll see a green banner with the row "
            "counts (\"Imported claims_2026-05-07.csv: 247 rows (12 new, 235 "
            "updated)\") and the dashboard cards refresh themselves.",
            "Status changes between imports are recorded automatically - that's "
            "how CORRECTIONS (7D) and NEW REJECTS (7D) are calculated.",
        ],
    ),
    (
        "Reviewing Claims",
        [
            "The Claims tab is read-only. Status, Error Description, and the "
            "other claim fields come from the ACE Portal CSV imports - that's "
            "the single source of truth.",
            "If you want to track your own follow-up notes against specific "
            "claims, use Ctrl+E to export the current view to Excel and "
            "annotate there. The Notes column header is included in the "
            "export so you have a slot to fill in.",
        ],
    ),
    (
        "Tabs at a glance",
        [
            "Dashboard - summary cards and CSV drop zone.",
            "Deadlines - upcoming CAPE LIQ deadlines (entry liquidation + 80 "
            "days), grouped by importer and week.",
            "Entries - every entry in the system, filterable by importer status.",
            "Claims - editable claim status (the only place edits are saved).",
            "Compliance - the work queue: failed claims that haven't been "
            "actioned yet.",
            "Refunds - duty paid by importer, for the CAPE-eligible refund "
            "estimate.",
            "Protests - protest deadlines (final liquidation + 180 days).",
            "Importers - importer compliance flags (Self Filer, ACE, ACH, "
            "4811 Client, PSC).",
            "Reports - export the full CAPE ESTIMATE Excel workbook.",
        ],
    ),
    (
        "Filtering, sorting, and exporting",
        [
            "Each tab has filters across the top: a text box on the right, plus "
            "drop-downs (DIV, importer-status flags, etc.). Filters apply "
            "immediately - no Apply button.",
            "Click any column header to sort by that column. Click again to "
            "reverse direction. Currency, dates, and Y/N values sort correctly "
            "regardless of how they're displayed.",
            "Press Ctrl+E (or click the Export... button next to Refresh) to "
            "save the rows currently shown - filters and sort included - to "
            "Excel (.xlsx) or CSV. Pick the file extension in the Save dialog.",
        ],
    ),
    (
        "Reports - full workbook export",
        [
            "Reports tab > Export CAPE ESTIMATE workbook... regenerates the "
            "legacy multi-sheet Excel file (Entry Count, Main Report, Claim "
            "details, Refund Pivot, Protest Pivot, etc.) from the live data.",
            "Generation takes 5 to 30 seconds; a progress bar shows it's working "
            "and the rest of the app stays responsive while you wait.",
        ],
    ),
    (
        "Updates",
        [
            "CAPEView checks for new versions when you launch it. When an update "
            "is available you'll see a prompt - just click Yes. The app downloads "
            "the new version, replaces itself, and relaunches automatically. "
            "Your settings, edits, and database are preserved.",
        ],
    ),
    (
        "Keyboard shortcuts",
        [
            "Ctrl+E   Export the current tab's view to xlsx/csv.",
            "Ctrl+,   Open Settings (database location, etc.).",
            "Ctrl+Shift+A   Open the Access Administration dialog (admins only).",
        ],
    ),
    (
        "Need help?",
        [
            "Tell your CAPEView admin (currently Heath Payne, Project "
            "Contact). For urgent issues - locked out, can't see your importer's "
            "data, error on import - the admin can usually unblock you in a few "
            "minutes.",
        ],
    ),
]


class QuickStartPDF(FPDF):
    def header(self):
        self.set_fill_color(*PRIMARY)
        self.rect(0, 0, self.w, 14, style="F")
        self.set_y(2)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, "CAPEView - User Quick Start", align="L")
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
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*PRIMARY)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
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
    pdf = QuickStartPDF(orientation="P", unit="mm", format="Letter")
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
    out = repo_root / "docs" / "CAPEView_User_QuickStart.pdf"
    written = build_pdf(out)
    print(f"Wrote {written.relative_to(repo_root)}  ({written.stat().st_size:,} bytes)")


if __name__ == "__main__":
    raise SystemExit(main())
