"""Typed metadata-only security audit contracts."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AuditContext:
    """Trusted correlation and actor metadata for one security operation."""

    request_id: str
    trace_id: str
    actor_id: str | None
    tenant_id: str | None
    occurred_at: datetime
    client_ip: str | None


@dataclass(frozen=True)
class SecurityAuditEvent:
    """Credential-free event suitable for an isolated audit sink."""

    context: AuditContext
    event_name: str
    action: str
    target_type: str
    target_id: str
    outcome: str
