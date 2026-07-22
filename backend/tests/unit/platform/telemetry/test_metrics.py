"""Typed telemetry metric recorder tests."""

from decimal import Decimal

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from bid_system.platform.telemetry.metrics import (
    DatabasePoolMeasurement,
    ExternalCallMeasurement,
    HttpRequestMeasurement,
    LlmUsageMeasurement,
    QueueBacklogMeasurement,
    TelemetryMetrics,
    WorkerTaskMeasurement,
)


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None
    return {
        metric.name
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }


def test_records_all_supported_operation_measurements() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    recorder = TelemetryMetrics(provider.get_meter("test"))

    recorder.record_http_request(
        HttpRequestMeasurement(method="GET", route="/health", status_code=200, duration_ms=1.5)
    )
    recorder.observe_database_pool(
        DatabasePoolMeasurement(pool_name="primary", size=5, checked_out=2, overflow=1)
    )
    recorder.record_external_call(
        ExternalCallMeasurement(
            provider="ocr", operation="parse", outcome="success", duration_ms=25.0
        )
    )
    recorder.record_worker_task(
        WorkerTaskMeasurement(
            task_name="publish_outbox",
            queue_name="default",
            outcome="success",
            duration_ms=10.0,
            retry_count=0,
        )
    )
    recorder.observe_queue_backlog(QueueBacklogMeasurement(queue_name="default", size=4))
    recorder.record_llm_usage(
        LlmUsageMeasurement(
            provider="openai-compatible",
            model="model-1",
            outcome="success",
            input_tokens=100,
            output_tokens=20,
            cost=Decimal("0.12"),
            currency="USD",
        )
    )

    assert {
        "bid_system.http.server.requests",
        "bid_system.http.server.duration",
        "bid_system.database.pool.size",
        "bid_system.database.pool.checked_out",
        "bid_system.database.pool.overflow",
        "bid_system.external.requests",
        "bid_system.external.duration",
        "bid_system.worker.tasks",
        "bid_system.worker.duration",
        "bid_system.queue.backlog",
        "bid_system.llm.requests",
        "bid_system.llm.input_tokens",
        "bid_system.llm.output_tokens",
        "bid_system.llm.cost",
    } <= _metric_names(reader)


def test_rejects_negative_measurements_and_cost_without_currency() -> None:
    with pytest.raises(ValueError, match="duration_ms"):
        HttpRequestMeasurement(method="GET", route="/", status_code=200, duration_ms=-1)

    with pytest.raises(ValueError, match="currency"):
        LlmUsageMeasurement(
            provider="provider",
            model="model",
            outcome="success",
            input_tokens=1,
            output_tokens=1,
            cost=Decimal("0.01"),
            currency=None,
        )
