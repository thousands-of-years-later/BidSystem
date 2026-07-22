"""Trace propagation and correlation context tests."""

from opentelemetry.sdk.trace import TracerProvider

from bid_system.platform.telemetry.tracing import (
    CorrelationContext,
    bind_correlation_context,
    current_correlation_context,
    request_span,
)


def test_correlation_context_is_nested_and_restored_after_failure() -> None:
    outer = CorrelationContext(request_id="request-1", trace_id="1" * 32, span_id="1" * 16)
    inner = CorrelationContext(request_id="request-2", trace_id="2" * 32, span_id="2" * 16)

    try:
        with bind_correlation_context(outer):
            assert current_correlation_context() == outer
            with bind_correlation_context(inner):
                assert current_correlation_context() == inner
                raise RuntimeError("expected")
    except RuntimeError:
        pass

    assert current_correlation_context() is None


def test_request_span_preserves_valid_remote_trace_id() -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    trace_id = "0123456789abcdef0123456789abcdef"

    with request_span(
        request_id="request-1",
        headers={"traceparent": f"00-{trace_id}-0123456789abcdef-01"},
        tracer=tracer,
    ) as correlation:
        assert correlation.trace_id == trace_id
        assert len(correlation.span_id) == 16
        assert current_correlation_context() == correlation

    assert current_correlation_context() is None


def test_request_span_replaces_invalid_remote_context() -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer("test")

    with request_span(
        request_id="request-1",
        headers={"traceparent": "00-invalid-invalid-01"},
        tracer=tracer,
    ) as correlation:
        assert len(correlation.trace_id) == 32
        assert correlation.trace_id != "0" * 32
        assert len(correlation.span_id) == 16
