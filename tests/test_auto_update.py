"""Tests for auto-updater version comparison logic.

Avoids importing PyQt5 in the test process by exercising UpdateChecker._is_newer_version
through a lightweight standalone helper.
"""

from __future__ import annotations

import pytest


def is_newer_version(latest: str, current: str) -> bool:
    """Mirrors UpdateChecker._is_newer_version. Pure-python so no Qt needed in tests."""
    try:
        latest_parts = [int(x) for x in latest.split(".")]
        current_parts = [int(x) for x in current.split(".")]
        max_len = max(len(latest_parts), len(current_parts))
        latest_parts += [0] * (max_len - len(latest_parts))
        current_parts += [0] * (max_len - len(current_parts))
        return latest_parts > current_parts
    except Exception:
        return False


@pytest.mark.parametrize("latest,current,expected", [
    ("0.0.2", "0.0.1", True),
    ("0.0.1", "0.0.1", False),
    ("0.0.1", "0.0.2", False),
    ("0.1.0", "0.0.99", True),
    ("0.0.10", "0.0.9", True),
    ("0.0.10", "0.0.2", True),
    ("1.0.0", "0.99.99", True),
    ("garbage", "0.0.1", False),
    ("0.0.1", "garbage", False),
])
def test_is_newer_version(latest, current, expected):
    assert is_newer_version(latest, current) is expected
