"""Shared pytest fixtures and global test-suite guards.

Critical: the autouse ``_no_outlook_in_tests`` fixture below forces every
test into a state where the email-digest hook is a no-op — even tests
that don't explicitly patch it. This exists because:

- Many tests (test_claims_csv_ingest, test_email_digest) call
  ``claims_csv_ingest.process_inbox`` or ``process_single_file``, which
  in turn calls ``_maybe_send_digest``.
- ``_maybe_send_digest`` reads ``settings.json`` for ``email.enabled``.
  Without overriding the settings path, it picks up the developer's
  real settings file — and if email is enabled there (because the dev
  is testing the live feature), pytest sends real Outlook emails on
  every test run.
- Pre-commit runs pytest on every commit, multiplying the leak.

The fix has two layers:
1. Point ``CAPEVIEW_SETTINGS_PATH`` at a tmp empty settings file per
   test, so ``email.enabled`` defaults to False and the digest hook
   short-circuits before reaching Outlook.
2. As defense in depth, force ``email_digest._win32com_client`` to None
   so any code path that somehow bypasses the settings check still
   raises ``RuntimeError("pywin32 not installed")`` instead of dialing
   real Outlook COM.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_outlook_in_tests(tmp_path_factory, monkeypatch):
    tmp = tmp_path_factory.mktemp("capeview_test_settings")
    settings_file = tmp / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CAPEVIEW_SETTINGS_PATH", str(settings_file))

    from CAPEView import email_digest
    monkeypatch.setattr(email_digest, "_resolve_win32com_client",
                        lambda: None, raising=False)
