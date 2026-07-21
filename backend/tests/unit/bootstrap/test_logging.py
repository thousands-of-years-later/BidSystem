"""Unit tests for bootstrap logging and redaction."""

import logging
import sys

from bid_system.bootstrap.logging import JsonFormatter, SensitiveDataFilter


def test_sensitive_data_filter_redacts_headers_urls_and_mapping_values() -> None:
    record = logging.LogRecord(
        name="bid_system.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg={
            "authorization": "Bearer private-token",
            "database_url": "postgresql://user:password@localhost/db",
        },
        args=(),
        exc_info=None,
    )

    assert SensitiveDataFilter().filter(record)
    rendered = str(record.msg)
    assert "private-token" not in rendered
    assert "password" not in rendered
    assert "***" in rendered


def test_json_formatter_keeps_traceback_but_redacts_exception_secrets() -> None:
    def fail_with_sensitive_diagnostic() -> None:
        raise RuntimeError(
            "database_url=postgresql://user:password@localhost/db token=private-token"
        )

    try:
        fail_with_sensitive_diagnostic()
    except RuntimeError:
        exception_info = sys.exc_info()

    record = logging.LogRecord(
        name="bid_system.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="unhandled_request_exception",
        args=(),
        exc_info=exception_info,
    )

    rendered = JsonFormatter().format(record)

    assert "RuntimeError" in rendered
    assert "fail_with_sensitive_diagnostic" in rendered
    assert "Traceback" in rendered
    assert "password" not in rendered
    assert "private-token" not in rendered
    assert "***" in rendered
