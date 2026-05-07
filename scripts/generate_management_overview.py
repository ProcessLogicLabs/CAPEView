"""Generate a management-review product overview PDF for CAPEView.

Audience: senior management evaluating CAPEView at a strategic level
(why this approach? what did it replace? what does it cost to run?).
Not a feature list, not a user guide. Output:
``docs/CAPEView_Management_Overview.pdf``.

Re-runnable; rewrites on each invocation. Requires fpdf2
(``pip install fpdf2``) — tooling-only, not in requirements.txt.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from CAPEView.version import get_version

PRIMARY = (78, 140, 155)
DARK_TEXT = (28, 50, 58)
MUTED_TEXT = (90, 112, 121)


SECTIONS: list[tuple[str, list[str]]] = [
    (
        "Executive Summary",
        [
            "CAPEView is a Windows desktop application that replaces the manually-"
            "maintained CAPE ESTIMATE Excel workbook used to track CAPE Phase-1 "
            "entries, claim filings, refund estimates, and importer compliance. "
            "Same business data, same business outcomes - delivered in a multi-"
            "user-safe SQLite database with a purpose-built interface, automatic "
            "CSV ingest from the ACE Portal, audit-logged changes, and one-click "
            "auto-updates.",
            "Built and maintained internally. Zero ongoing licensing or hosting "
            "cost.",
        ],
    ),
    (
        "The problem we solved",
        [
            "The original workbook accumulated four jobs over time - CAPE Phase-1 "
            "eligibility tracking, importer-status flags (ACE / ACH / Self Filer / "
            "4811 / PSC), claim-filing confirmation, and compliance evidence - "
            "and outgrew the format. The 60 MB file held 35,000 entries across "
            "200,000 tariff lines. Daily updates required manually rerunning "
            "VLOOKUPs across all 200K rows; the 16K-row Claim Details tab was "
            "hand-keyed; only one person could edit at a time; and there was no "
            "record of who changed what or when.",
        ],
    ),
    (
        "What CAPEView delivers",
        [
            "Multi-user concurrent access - everyone in the team works on the same "
            "live data without locking each other out.",
            "Automatic ACE Portal CSV ingest - drop a Claim Status file on the "
            "Dashboard, or schedule the cron job. No more manual VLOOKUPs.",
            "Audit trail - every status change is logged with the originating "
            "user (or CSV import) and timestamp.",
            "Built-in triage views - Compliance surfaces failed claims sorted by "
            "the IEEPA 80-day refund deadline, color-tinted by urgency, with the "
            "duty amount at stake on each row.",
            "Trend signals - Dashboard cards show CORRECTIONS (claims fixed in "
            "the last 7 days) and NEW REJECTS (claims newly failed in the last "
            "7 days), so the team sees upstream churn at a glance.",
            "One-click export - any filtered/sorted view can be saved to Excel "
            "or CSV for ad-hoc analysis or sharing.",
            "Auto-update - bug fixes and new features reach every user the next "
            "time they launch the app. No IT deploy cycle.",
        ],
    ),
    (
        "Why a desktop app and not a shared Excel workbook",
        [
            "Concurrent edits - the Excel workbook locks for a single user at a "
            "time; CAPEView allows the whole team to work simultaneously.",
            "Daily refresh - Excel required a manual VLOOKUP rerun across 200K "
            "rows; CAPEView ingests the day's CSV in seconds.",
            "Audit trail - Excel has none; CAPEView records every change.",
            "Open time - the 60 MB workbook took 30+ seconds to open; CAPEView "
            "loads any tab in under a second.",
            "Data integrity - Excel converts 11-digit entry numbers to "
            "scientific notation, dropping leading zeros and risking mis-keys; "
            "CAPEView stores them as exact text.",
            "Filtered views - in Excel each user maintains their own pivot or "
            "filter and they drift apart; CAPEView's tabs are pre-built and "
            "identical for every user.",
            "Pushing fixes - the workbook had to be re-emailed; CAPEView auto-"
            "updates on next launch.",
        ],
    ),
    (
        "Why a desktop app and not a web application",
        [
            "Infrastructure - a web app needs a server, hosting, monitoring, "
            "backups, and TLS certificates. CAPEView needs none of that. Each "
            "user's PC runs the app against a shared SQLite database file on "
            "the existing office LAN share.",
            "Ongoing cost - zero hosting bill, zero recurring license fee.",
            "IT setup - no DNS, firewall rules, certificates, or AD group "
            "provisioning required. The installer is a standard Windows .exe.",
            "Login UX - users sign in with their existing Windows session; no "
            "separate password to manage.",
            "Outlook integration - users drag CSV attachments straight from "
            "Outlook onto the Dashboard. A web app cannot do this natively.",
            "Data location - business data stays on the office LAN. Never "
            "traverses the public internet.",
            "Tradeoff: per-machine install rather than one-URL-for-everyone. "
            "Mitigated by the auto-update flow, which pushes new versions to "
            "every user with a single click.",
        ],
    ),
    (
        "Roadmap",
        [
            "Continued UI refinements driven by daily-user feedback from the "
            "customs brokerage team.",
            "Optional Microsoft Teams / SharePoint integration to surface read-"
            "only views to non-CAPEView users in the organization. Designed and "
            "parked pending demand.",
            "Optional web companion for off-network executive access. Designed "
            "and parked pending demand.",
        ],
    ),
]


class OverviewPDF(FPDF):
    def header(self):
        self.set_fill_color(*PRIMARY)
        self.rect(0, 0, self.w, 14, style="F")
        self.set_y(2)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, "CAPEView - Management Overview", align="L")
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
    pdf = OverviewPDF(orientation="P", unit="mm", format="Letter")
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
    out = repo_root / "docs" / "CAPEView_Management_Overview.pdf"
    written = build_pdf(out)
    print(f"Wrote {written.relative_to(repo_root)}  ({written.stat().st_size:,} bytes)")


if __name__ == "__main__":
    raise SystemExit(main())
