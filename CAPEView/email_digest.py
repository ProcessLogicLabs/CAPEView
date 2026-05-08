"""Compliance digest email — runs after a successful CSV ingest.

When email is enabled in settings, every successful CSV ingest sends a
summary of the current Compliance view to a configurable list of
recipients via Outlook COM. If the recipients list is empty the digest
falls back to the running user (so the user gets it in their own inbox
+ Sent folder by default).

Outlook COM (``win32com.client``) handles transport — no SMTP relay, no
password storage, no IT involvement. Tradeoff: Outlook must be installed
on the user's machine. CAPEView is Windows-desktop-only already, so this
is acceptable.

Settings keys (managed via the in-app Settings dialog):

    {
      "email.enabled": true,
      "email.recipients": ["eric@example.com", "team@example.com"]
    }

Default ``email.enabled = False`` so email is opt-in (no surprise sends).
Default ``email.recipients = []`` falls back to the running user.

The Compliance SQL is duplicated from ``views/table_view.ComplianceView.
build_query`` so this module stays Qt-free. Tests guard against drift.
"""

from __future__ import annotations

import html
import logging
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path

from CAPEView import export_view

logger = logging.getLogger(__name__)


# Mirror in-app urgency colors (Qt URGENCY_* constants in views/table_view.py).
# Hex values inlined here so this module has no Qt dependency.
URGENCY_OVERDUE_HEX = "#F5D2D7"
URGENCY_DUE_30_HEX = "#FCEBC4"
URGENCY_DUE_60_HEX = "#FCF6DC"


# Headers match the Compliance tab so the attachment is recognizable
HEADERS = [
    "Entry Summary #", "Claim #", "Status", "Error Description",
    "DIV", "CAPE LIQ Deadline", "Total Liq Duty", "Importer Name",
]


_COMPLIANCE_SQL = (
    "SELECT c.entry_summary_number, c.claim_number, c.status, "
    "       c.error_description, e.div, e.cape_liq_deadline, "
    "       e.total_liquidated_duty, e.importer_name "
    "FROM claims c "
    "LEFT JOIN entries e ON e.entry_summary_number = c.entry_summary_number "
    "WHERE UPPER(COALESCE(c.status,'')) = 'FAILED' "
    "  AND NOT EXISTS (SELECT 1 FROM entry_actions a "
    "                  WHERE a.entry_summary_number = c.entry_summary_number "
    "                  AND a.action_type = 'REJECTION_ACTIONED') "
    "ORDER BY e.cape_liq_deadline IS NULL, e.cape_liq_deadline ASC"
)


def build_digest(conn: sqlite3.Connection) -> dict:
    """Run the Compliance query and aggregate summary stats.

    Returns: ``{"rows": [tuple, ...], "summary": {...}}``.
    Each row tuple matches the HEADERS column order.
    """
    cur = conn.execute(_COMPLIANCE_SQL)
    rows = [tuple(r) for r in cur.fetchall()]

    total_failed = len(rows)
    total_duty = sum((r[6] or 0) for r in rows)
    by_div: dict[str, int] = {}
    for r in rows:
        div = r[4] or "(unknown)"
        by_div[div] = by_div.get(div, 0) + 1

    return {
        "rows": rows,
        "summary": {
            "total_failed": total_failed,
            "total_duty": total_duty,
            "by_div": by_div,
        },
    }


# ----------------------------------------------------------------------
# Inline formatters — duplicated from views.table_view to avoid pulling Qt
# into this module. Intentional duplication; trivial functions.
# ----------------------------------------------------------------------

def _format_usd(value) -> str:
    if value is None or value == "":
        return ""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if n < 0 else ""
    return f"{sign}${abs(n):,.2f}"


def _format_date(value) -> str:
    if not value:
        return ""
    s = str(value)[:10]
    try:
        y, m, d = s.split("-")
        return f"{int(m)}/{int(d)}/{y}"
    except ValueError:
        return s


def _urgency_color(deadline_iso, today: date | None = None) -> str | None:
    if not deadline_iso:
        return None
    today = today or date.today()
    try:
        d = date.fromisoformat(str(deadline_iso)[:10])
    except ValueError:
        return None
    delta = (d - today).days
    if delta < 0:
        return URGENCY_OVERDUE_HEX
    if delta <= 30:
        return URGENCY_DUE_30_HEX
    if delta <= 60:
        return URGENCY_DUE_60_HEX
    return None


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------

def render_html(digest: dict, version: str) -> str:
    """Inline-styled HTML body. No external CSS — must render in any mail client."""
    summary = digest["summary"]
    rows = digest["rows"]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    base_font = "font-family:Segoe UI,Arial,sans-serif;"

    if summary["total_failed"] == 0:
        return (
            f"<p style='{base_font}color:#1C323A;'>"
            f"<b>All clear, 0 failed claims.</b></p>"
            f"<p style='{base_font}color:#5A7079;font-size:12px;'>"
            f"CAPEView {html.escape(version)} &middot; {html.escape(timestamp)}</p>"
        )

    by_div_lines = "<br>".join(
        f"&nbsp;&nbsp;{html.escape(div)}: {n}"
        for div, n in sorted(summary["by_div"].items())
    )

    summary_block = (
        f"<table style='{base_font}color:#1C323A;font-size:13px;'>"
        f"<tr><td><b>Total failed claims:</b></td><td>{summary['total_failed']}</td></tr>"
        f"<tr><td><b>Total duty at stake:</b></td>"
        f"<td>{html.escape(_format_usd(summary['total_duty']))}</td></tr>"
        f"<tr><td valign='top'><b>By DIV:</b></td><td>{by_div_lines}</td></tr>"
        f"</table>"
    )

    header_html = "".join(
        f"<th style='background:#4E8C9B;color:#fff;padding:6px 8px;"
        f"text-align:left;'>{html.escape(h)}</th>"
        for h in HEADERS
    )

    top10 = rows[:10]
    row_html_parts = []
    for r in top10:
        color = _urgency_color(r[5])
        bg = f"background:{color};" if color else ""
        cells = [
            html.escape(str(r[0] or "")),
            html.escape(str(r[1] or "")),
            html.escape(str(r[2] or "")),
            html.escape(str(r[3] or "")),
            html.escape(str(r[4] or "")),
            html.escape(_format_date(r[5])),
            html.escape(_format_usd(r[6])),
            html.escape(str(r[7] or "")),
        ]
        cells_html = "".join(f"<td style='padding:4px 8px;'>{c}</td>" for c in cells)
        row_html_parts.append(f"<tr style='{bg}'>{cells_html}</tr>")

    table_html = (
        f"<table style='{base_font}font-size:12px;border-collapse:collapse;'>"
        f"<tr>{header_html}</tr>"
        f"{''.join(row_html_parts)}"
        f"</table>"
    )

    return (
        f"<p style='{base_font}color:#1C323A;'>"
        f"<b>CAPEView Compliance digest</b></p>"
        f"{summary_block}"
        f"<p style='{base_font}color:#1C323A;margin-top:16px;'>"
        f"<b>Top 10 most-urgent rejects</b></p>"
        f"{table_html}"
        f"<p style='{base_font}color:#5A7079;font-size:12px;margin-top:12px;'>"
        f"Full list attached. Forward this email to share with the team.</p>"
        f"<p style='{base_font}color:#5A7079;font-size:11px;'>"
        f"CAPEView {html.escape(version)} &middot; {html.escape(timestamp)}</p>"
    )


def write_attachment(digest: dict, path: Path) -> Path:
    """Write the full Compliance result to xlsx using export_view.write_xlsx
    so the styling matches per-tab Ctrl+E exports."""
    rows_for_xlsx: list[list[str]] = []
    row_colors: list[str | None] = []
    for r in digest["rows"]:
        rows_for_xlsx.append([
            str(r[0] or ""),
            str(r[1] or ""),
            str(r[2] or ""),
            str(r[3] or ""),
            str(r[4] or ""),
            _format_date(r[5]),
            _format_usd(r[6]),
            str(r[7] or ""),
        ])
        row_colors.append(_urgency_color(r[5]))

    export_view.write_xlsx(
        path, "Compliance", HEADERS, rows_for_xlsx, row_colors=row_colors,
    )
    return path


# ----------------------------------------------------------------------
# Outlook COM transport — lazy-imported so the module loads without
# pywin32 (helpful for tests on stub environments).
# ----------------------------------------------------------------------

# Module-level optional import. Tests patch this attribute directly via
# patch.object(email_digest, "_win32com_client", mock) so they never have to
# munge sys.modules — that pattern was leaking real Outlook calls when
# pre-commit pytest ran on a Windows machine with pywin32 installed.
try:
    import win32com.client as _win32com_client  # type: ignore
except ImportError:
    _win32com_client = None  # type: ignore[assignment]


def _get_current_user_email() -> str:
    """Return the running user's primary SMTP address via Outlook COM.
    Returns an empty string if Outlook can't be reached."""
    if _win32com_client is None:
        logger.warning("pywin32 not installed; cannot derive Outlook user email")
        return ""

    try:
        outlook = _win32com_client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        current = ns.CurrentUser
    except Exception as e:
        logger.warning("Could not reach Outlook to derive user email: %s", e)
        return ""

    # Exchange account → primary SMTP via GetExchangeUser
    try:
        exch = current.AddressEntry.GetExchangeUser()
        if exch is not None:
            smtp = exch.PrimarySmtpAddress
            if smtp:
                return str(smtp)
    except Exception:
        pass  # not an Exchange account; fall through

    # Fall back to AddressEntry.Address (works for SMTP-direct accounts)
    try:
        addr = current.AddressEntry.Address
        if addr and "@" in str(addr):
            return str(addr)
    except Exception:
        pass

    return ""


def _send_via_outlook(
    subject: str, html_body: str, attachment_path: Path, to_address: str,
) -> None:
    """Send a single email via Outlook COM. Raises on failure — caller is
    responsible for catching and logging."""
    if _win32com_client is None:
        raise RuntimeError("pywin32 not installed; cannot send via Outlook")

    outlook = _win32com_client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # 0 = olMailItem
    mail.Subject = subject
    mail.HTMLBody = html_body
    mail.To = to_address
    mail.Attachments.Add(str(attachment_path))
    mail.Send()


def _resolve_recipients(settings) -> list[str]:
    """Return the configured recipient list, falling back to the running user
    when the list is empty. Returns ``[]`` if neither is available."""
    raw = settings.get("email.recipients", []) or []
    cleaned = [str(addr).strip() for addr in raw if str(addr).strip()]
    if cleaned:
        return cleaned
    self_addr = _get_current_user_email()
    return [self_addr] if self_addr else []


def send_compliance_digest(
    conn: sqlite3.Connection, version: str, settings=None,
) -> dict:
    """Build and send the Compliance digest. No-op if email.enabled is false.

    Returns ``{"sent": bool, "recipients": list[str], "rows": int, "error": str|None}``.
    Never raises — failures are caught and reported via the return dict.
    """
    if settings is None:
        from CAPEView.settings_manager import SettingsManager
        settings = SettingsManager()

    if not settings.get("email.enabled", False):
        return {"sent": False, "recipients": [], "rows": 0, "error": None}

    try:
        digest = build_digest(conn)
    except Exception as e:
        logger.exception("Failed to build compliance digest")
        return {"sent": False, "recipients": [], "rows": 0,
                "error": f"build_digest: {e}"}

    recipients = _resolve_recipients(settings)
    if not recipients:
        msg = "no recipients (configured list is empty and Outlook user lookup failed)"
        logger.warning("Skipping compliance digest: %s", msg)
        return {"sent": False, "recipients": [],
                "rows": digest["summary"]["total_failed"], "error": msg}

    summary = digest["summary"]
    subject = (
        f"[CAPEView] Compliance digest — "
        f"{summary['total_failed']} failed claims, "
        f"total duty {_format_usd(summary['total_duty'])}"
    )
    html_body = render_html(digest, version)

    tmpdir = Path(tempfile.gettempdir()) / "CAPEView_email_digest"
    tmpdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    attachment = tmpdir / f"compliance_digest_{stamp}.xlsx"

    try:
        write_attachment(digest, attachment)
    except Exception as e:
        logger.exception("Failed to write compliance digest attachment")
        return {"sent": False, "recipients": recipients,
                "rows": summary["total_failed"], "error": f"write_attachment: {e}"}

    # Outlook accepts a semicolon-delimited string in MailItem.To
    to_address = "; ".join(recipients)
    try:
        _send_via_outlook(subject, html_body, attachment, to_address)
    except Exception as e:
        logger.exception("Failed to send compliance digest via Outlook")
        return {"sent": False, "recipients": recipients,
                "rows": summary["total_failed"], "error": f"send: {e}"}

    logger.info("Compliance digest sent to %s (%d rows)",
                ", ".join(recipients), summary["total_failed"])
    return {"sent": True, "recipients": recipients,
            "rows": summary["total_failed"], "error": None}
