"""Tests for the Outlook OLE FileGroupDescriptor parser.

These verify the byte-format decoding without needing a QApplication —
synthetic FGD buffers built to mirror what Outlook puts on the clipboard
when an attachment is dragged.
"""

from __future__ import annotations

import struct

from CAPEView import outlook_drop


def _build_fgdw(filename: str, n_items: int = 1) -> bytes:
    """Build a synthetic FILEGROUPDESCRIPTORW byte buffer."""
    # Header: DWORD cItems
    header = struct.pack("<L", n_items)
    # FILEDESCRIPTORW: 592 bytes total. We don't care about the metadata
    # fields for parsing, just that cFileName at offset 72 holds the wide
    # null-terminated filename in a 260-wchar (520-byte) buffer.
    descriptor = bytearray(592)
    name_bytes = filename.encode("utf-16-le")
    descriptor[72:72 + len(name_bytes)] = name_bytes
    # Multi-item buffers append additional descriptors back-to-back.
    extra = bytearray(592 * (n_items - 1)) if n_items > 1 else b""
    return header + bytes(descriptor) + bytes(extra)


def _build_fgda(filename: str) -> bytes:
    """Build a synthetic ANSI FILEGROUPDESCRIPTOR byte buffer."""
    header = struct.pack("<L", 1)
    descriptor = bytearray(332)
    name_bytes = filename.encode("mbcs")
    descriptor[72:72 + len(name_bytes)] = name_bytes
    return header + bytes(descriptor)


def test_peek_filename_wide():
    fgd = _build_fgdw("claims_2026-05-07.csv")
    assert outlook_drop.peek_filename(fgd, None) == "claims_2026-05-07.csv"


def test_peek_filename_ansi_fallback():
    fgd = _build_fgda("legacy_claims.csv")
    assert outlook_drop.peek_filename(None, fgd) == "legacy_claims.csv"


def test_peek_filename_prefers_wide():
    """When both formats are present, the wide variant wins."""
    fgd_w = _build_fgdw("wide.csv")
    fgd_a = _build_fgda("ansi.csv")
    assert outlook_drop.peek_filename(fgd_w, fgd_a) == "wide.csv"


def test_peek_filename_rejects_multifile_drag():
    """We only support one-attachment drags, matching the URL-drop rule."""
    fgd = _build_fgdw("first.csv", n_items=2)
    assert outlook_drop.peek_filename(fgd, None) is None


def test_peek_filename_handles_unicode():
    fgd = _build_fgdw("résumé_claims_éàü.csv")
    assert outlook_drop.peek_filename(fgd, None) == "résumé_claims_éàü.csv"


def test_peek_filename_returns_none_for_empty_buffers():
    assert outlook_drop.peek_filename(None, None) is None
    assert outlook_drop.peek_filename(b"", b"") is None


def test_peek_filename_rejects_truncated_buffer():
    """A buffer too small to hold even one descriptor must not crash."""
    short = struct.pack("<L", 1) + b"\x00" * 100  # < 592 bytes
    assert outlook_drop.peek_filename(short, None) is None


def test_parse_attachment_returns_filename_and_contents():
    fgd = _build_fgdw("claims.csv")
    payload = b"ENTRY_NUMBER,CLAIM_NUMBER,STATUS,ERROR_DESCRIPTION\n1,2,3,4\n"
    result = outlook_drop.parse_attachment(fgd, None, payload)
    assert result is not None
    name, body = result
    assert name == "claims.csv"
    assert body == payload


def test_parse_attachment_returns_none_without_filecontents():
    fgd = _build_fgdw("claims.csv")
    assert outlook_drop.parse_attachment(fgd, None, None) is None


def test_parse_attachment_returns_none_without_descriptor():
    payload = b"some,csv,data\n"
    assert outlook_drop.parse_attachment(None, None, payload) is None
