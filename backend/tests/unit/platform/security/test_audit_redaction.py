"""Security audit context and redaction facade tests."""

from datetime import UTC, datetime

from bid_system.platform.security.audit import AuditContext, SecurityAuditEvent
from bid_system.platform.security.redaction import REDACTED, redact_response


def test_security_audit_event_contains_context_but_not_credentials() -> None:
    context = AuditContext(
        request_id="request-1",
        trace_id="trace-1",
        actor_id="user-1",
        tenant_id="tenant-1",
        occurred_at=datetime(2026, 7, 22, tzinfo=UTC),
        client_ip="127.0.0.1",
    )

    event = SecurityAuditEvent(
        context=context,
        event_name="security.login.succeeded",
        action="login",
        target_type="session",
        target_id="session-1",
        outcome="success",
    )

    assert event.context.tenant_id == "tenant-1"
    assert not hasattr(event, "token")


def test_response_redaction_recurses_and_preserves_safe_fields() -> None:
    result = redact_response(
        {
            "user_id": "user-1",
            "authorization": "Bearer private-token",
            "nested": {"password": "private-password", "status": "ok"},
        }
    )

    assert result == {
        "user_id": "user-1",
        "authorization": REDACTED,
        "nested": {"password": REDACTED, "status": "ok"},
    }
