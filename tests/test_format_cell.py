"""Tests for the table cell formatter (ISO dates -> MM/DD/YYYY)."""

import pytest

# Skip if PyQt5 isn't installed (CI installs it via requirements.txt)
pytest.importorskip("PyQt5")

from CAPEView.views.table_view import format_cell, format_usd


@pytest.mark.parametrize("value,expected", [
    (None,           ""),
    ("",             ""),
    ("2026-05-06",   "5/6/2026"),
    ("2026-12-31",   "12/31/2026"),
    ("2026-01-01",   "1/1/2026"),
    ("2026-05-06T16:04:49", "5/6/2026 16:04"),
    ("2026-05-06 16:04:49", "5/6/2026 16:04"),
    ("HOUSTON",      "HOUSTON"),
    ("60575980937",  "60575980937"),
    (1234,           "1234"),
    (1.5,            "1.5"),
    # Bogus serial-date values that the migration now NULLs out, but if any
    # leaks through we still render them safely:
    ("1900-03-20",   "3/20/1900"),
])
def test_format_cell(value, expected):
    assert format_cell(value) == expected


@pytest.mark.parametrize("value,expected", [
    (None,                ""),
    ("",                  ""),
    (0,                   "$0.00"),
    (0.0,                 "$0.00"),
    (1,                   "$1.00"),
    (1.5,                 "$1.50"),
    (1234.56,             "$1,234.56"),
    (26352732.57,         "$26,352,732.57"),
    ("13501457.17",       "$13,501,457.17"),
    (-100,                "-$100.00"),
    (-26352732.57,        "-$26,352,732.57"),
    ("not a number",      "not a number"),
])
def test_format_usd(value, expected):
    assert format_usd(value) == expected
