"""OpenTelemetry spans and process-local correlation context propagation."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from secrets import token_hex

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from bid_system.platform.config import TracingSettings

INSTRUMENTATION_NAME = "bid_system"
HTTP_SERVER_SPAN_NAME = "http.server.request"
TRACE_ID_HEX_LENGTH = 32
SPAN_ID_HEX_LENGTH = 16
OTLP_TRACES_PATH = "/v1/traces"
DEPLOYMENT_ENVIRONMENT_ATTRIBUTE = "deployment.environment.name"


def _signal_endpoint(base_endpoint: str, signal_path: str) -> str:
    return f"{base_endpoint.rstrip('/')}{signal_path}"


def configure_tracing(settings: TracingSettings, *, environment: str) -> TracerProvider | None:
    """Configure process tracing only when an explicit OTLP destination is enabled."""
    if not settings.enabled:
        return None
    if settings.otlp_endpoint is None:
        raise ValueError("Tracing OTLP endpoint is required when tracing is enabled")
    resource = Resource.create(
        {
            SERVICE_NAME: settings.service_name,
            DEPLOYMENT_ENVIRONMENT_ATTRIBUTE: environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=_signal_endpoint(settings.otlp_endpoint, OTLP_TRACES_PATH))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def shutdown_tracing(provider: TracerProvider | None) -> None:
    """Flush and stop the configured provider during process shutdown."""
    if provider is not None:
        provider.shutdown()


@dataclass(frozen=True)
class CorrelationContext:
    """Identifiers safe to attach to logs and transport responses."""

    request_id: str
    trace_id: str
    span_id: str


_CORRELATION_CONTEXT: ContextVar[CorrelationContext | None] = ContextVar(
    "bid_system_correlation_context",
    default=None,
)


def current_correlation_context() -> CorrelationContext | None:
    """Return the identifiers bound to the current async execution context."""
    return _CORRELATION_CONTEXT.get()


@contextmanager
def bind_correlation_context(context: CorrelationContext) -> Iterator[None]:
    """Bind identifiers for one operation and always restore the prior context."""
    token = _CORRELATION_CONTEXT.set(context)
    try:
        yield
    finally:
        _CORRELATION_CONTEXT.reset(token)


def _hex_trace_id(value: int) -> str:
    return f"{value:0{TRACE_ID_HEX_LENGTH}x}"


def _hex_span_id(value: int) -> str:
    return f"{value:0{SPAN_ID_HEX_LENGTH}x}"


@contextmanager
def request_span(
    *,
    request_id: str,
    headers: Mapping[str, str],
    tracer: Tracer | None = None,
) -> Iterator[CorrelationContext]:
    """Start a server span from W3C headers and bind its correlation identifiers."""
    parent_context = TraceContextTextMapPropagator().extract(carrier=headers)
    parent_span_context = trace.get_current_span(parent_context).get_span_context()
    resolved_tracer = tracer or trace.get_tracer(INSTRUMENTATION_NAME)
    with resolved_tracer.start_as_current_span(
        HTTP_SERVER_SPAN_NAME,
        context=parent_context,
        kind=SpanKind.SERVER,
    ) as span:
        span_context = span.get_span_context()
        trace_id = (
            _hex_trace_id(span_context.trace_id)
            if span_context.is_valid
            else (
                _hex_trace_id(parent_span_context.trace_id)
                if parent_span_context.is_valid
                else token_hex(TRACE_ID_HEX_LENGTH // 2)
            )
        )
        span_id = (
            _hex_span_id(span_context.span_id)
            if span_context.is_valid
            else token_hex(SPAN_ID_HEX_LENGTH // 2)
        )
        correlation = CorrelationContext(
            request_id=request_id,
            trace_id=trace_id,
            span_id=span_id,
        )
        with bind_correlation_context(correlation):
            yield correlation
