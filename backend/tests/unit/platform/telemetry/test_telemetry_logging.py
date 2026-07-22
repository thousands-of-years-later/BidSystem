"""Structured runtime and audit logging tests."""

import json
import logging
import sys

from bid_system.platform.telemetry.logging import (
    JsonFormatter,
    LogChannel,
    SensitiveDataFilter,
    get_logger,
)


def test_json_formatter_emits_stable_fields_and_correlation_context() -> None:
    record = logging.LogRecord(
        name="bid_system.runtime",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.event_name = "http.request.completed"
    record.request_id = "request-1"
    record.trace_id = "0123456789abcdef0123456789abcdef"
    record.span_id = "0123456789abcdef"
    record.duration_ms = 12.5

    payload = json.loads(
        JsonFormatter(service_name="bid-system", environment="test").format(record)
    )

    assert payload["severity"] == "INFO"
    assert payload["service_name"] == "bid-system"
    assert payload["environment"] == "test"
    assert payload["event_name"] == "http.request.completed"
    assert payload["log_type"] == "runtime"
    assert payload["request_id"] == "request-1"
    assert payload["trace_id"] == "0123456789abcdef0123456789abcdef"
    assert payload["span_id"] == "0123456789abcdef"
    assert payload["duration_ms"] == 12.5


def test_sensitive_filter_redacts_message_mapping_and_exception() -> None:
    try:
        raise RuntimeError("token=private-token")
    except RuntimeError:
        exception_info = sys.exc_info()

    record = logging.LogRecord(
        name="bid_system.runtime",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg={"authorization": "Bearer private-token"},
        args=(),
        exc_info=exception_info,
    )

    assert SensitiveDataFilter().filter(record)
    rendered = JsonFormatter(service_name="bid-system", environment="test").format(record)

    assert "private-token" not in rendered
    assert "***" in rendered


def test_runtime_and_audit_loggers_use_distinct_channels() -> None:
    runtime_logger = get_logger(LogChannel.RUNTIME, "http")
    audit_logger = get_logger(LogChannel.AUDIT, "reviews")

    assert runtime_logger.name == "bid_system.runtime.http"
    assert audit_logger.name == "bid_system.audit.reviews"
    assert runtime_logger.name != audit_logger.name
