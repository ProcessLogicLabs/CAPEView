"""Decode OLE drag-and-drop attachments dragged from Outlook (and similar
COM-aware Windows apps) into something the Dashboard drop zone can consume.

Outlook does not expose attachment drags as ``file://`` URLs — instead it
uses the legacy OLE clipboard formats:

- ``FileGroupDescriptorW`` — a header (``DWORD cItems``) followed by an array
  of ``FILEDESCRIPTORW`` structs (one per dragged item, 592 bytes each;
  the wide filename is at offset 72 within each descriptor).
- ``FileContents`` — the raw bytes of the (first) file. Multi-file drags
  expose subsequent files via an indexed ``IDataObject`` interface that Qt's
  ``QMimeData`` does not surface; this module supports single-attachment
  drags only.

PyQt5 surfaces these as Windows-MIME formats with the prefix
``application/x-qt-windows-mime;value="..."``. The functions below take raw
bytes (typically obtained via ``QMimeData.data(format).data()``) so the
parsing logic is pure Python and testable without a QApplication.
"""

from __future__ import annotations

import struct

# Qt-on-Windows MIME format names for OLE drag-drop
FGD_W_FORMAT = 'application/x-qt-windows-mime;value="FileGroupDescriptorW"'
FGD_A_FORMAT = 'application/x-qt-windows-mime;value="FileGroupDescriptor"'
FC_FORMAT = 'application/x-qt-windows-mime;value="FileContents"'

# FILEDESCRIPTORW (shlobj.h) — 592 bytes; cFileName at offset 72, 260 wchars (520 bytes)
_FILEDESCRIPTORW_SIZE = 592
# FILEDESCRIPTORA (legacy ANSI) — 332 bytes; cFileName at offset 72, 260 chars (260 bytes)
_FILEDESCRIPTORA_SIZE = 332
_FILENAME_OFFSET = 72
_FILENAME_W_BYTES = 520
_FILENAME_A_BYTES = 260


def peek_filename(fgd_w: bytes | None, fgd_a: bytes | None = None) -> str | None:
    """Return the first attachment's filename from the FileGroupDescriptor
    bytes, without touching FileContents. Used at ``dragEnterEvent`` time to
    decide whether to accept the drag based on extension.

    Pass the wide variant if available; falls back to ANSI. Returns None if
    the buffer is malformed or the drag contains more than one item (which
    we don't support, consistent with the URL-drag single-file rule).
    """
    if fgd_w:
        return _decode(fgd_w, wide=True)
    if fgd_a:
        return _decode(fgd_a, wide=False)
    return None


def parse_attachment(fgd_w: bytes | None, fgd_a: bytes | None,
                     file_contents: bytes) -> tuple[str, bytes] | None:
    """Return ``(filename, contents)`` for a single-attachment Outlook drag,
    or None if the buffers are missing/malformed/multi-file."""
    name = peek_filename(fgd_w, fgd_a)
    if not name:
        return None
    if file_contents is None:
        return None
    return name, bytes(file_contents)


def _decode(fgd: bytes, *, wide: bool) -> str | None:
    if len(fgd) < 4:
        return None
    n_items = struct.unpack_from("<L", fgd, 0)[0]
    if n_items != 1:
        # Multi-file drags require IDataObject indexing that QMimeData does
        # not expose. Reject — keeps parity with the existing one-file rule.
        return None
    descriptor_size = _FILEDESCRIPTORW_SIZE if wide else _FILEDESCRIPTORA_SIZE
    if len(fgd) < 4 + descriptor_size:
        return None
    if wide:
        name_bytes = fgd[4 + _FILENAME_OFFSET : 4 + _FILENAME_OFFSET + _FILENAME_W_BYTES]
        decoded = name_bytes.decode("utf-16-le", errors="replace")
    else:
        name_bytes = fgd[4 + _FILENAME_OFFSET : 4 + _FILENAME_OFFSET + _FILENAME_A_BYTES]
        decoded = name_bytes.split(b"\x00", 1)[0].decode("mbcs", errors="replace")
    # Wide string is null-terminated in a fixed 260-wchar buffer; trim.
    name = decoded.split("\x00", 1)[0].strip()
    return name or None
