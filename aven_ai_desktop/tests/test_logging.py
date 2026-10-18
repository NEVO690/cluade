from __future__ import annotations

import logging

from app.logging_setup import RedactingFilter, redact


def test_redact_masks_common_key_formats() -> None:
    text = redact("key sk-ant-api03-ABCDEFGHIJKLMNOP and Authorization: Bearer abcdefghijklmnop api_key=secret123")
    assert "ABCDEFGHIJ" not in text
    assert "abcdefghijklmnop" not in text
    assert "secret123" not in text


def test_filter_rewrites_records() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "using %s", ("sk-test-1234567890",), None)
    RedactingFilter().filter(record)
    assert "1234567890" not in record.getMessage()
