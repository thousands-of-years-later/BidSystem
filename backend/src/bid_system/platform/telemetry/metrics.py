"""Low-cardinality OpenTelemetry measurements for platform operations."""

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter_ns
from typing import Protocol

from opentelemetry import metrics
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from bid_system.platform.config import MetricsSettings

SUCCESS_OUTCOME = "success"
SUPPORTED_OUTCOMES = frozenset({SUCCESS_OUTCOME, "error", "cancelled", "retry"})
MIN_HTTP_STATUS_CODE = 100
MAX_HTTP_STATUS_CODE = 599
ERROR_HTTP_STATUS_CODE = 400
INSTRUMENTATION_NAME = "bid_system"
OTLP_METRICS_PATH = "/v1/metrics"
MILLISECONDS_PER_SECOND = 1_000
NANOSECONDS_PER_MILLISECOND = 1_000_000
DEPLOYMENT_ENVIRONMENT_ATTRIBUTE = "deployment.environment.name"
EXTERNAL_LOGGER = logging.getLogger("bid_system.external")
WORKER_LOGGER = logging.getLogger("bid_system.worker")


class GaugePort(Protocol):
    """Stable subset of the synchronous gauge API used by this recorder."""

    def set(
        self,
        amount: int | float,
        attributes: dict[str, str] | None = None,
        context: Context | None = None,
    ) -> None: ...


class MetricsSink(Protocol):
    """Metrics used by entrypoints and adapters without exposing an SDK provider."""

    def record_http_request(self, measurement: "HttpRequestMeasurement") -> None: ...

    def observe_database_pool(self, measurement: "DatabasePoolMeasurement") -> None: ...

    def record_external_call(self, measurement: "ExternalCallMeasurement") -> None: ...

    def record_worker_task(self, measurement: "WorkerTaskMeasurement") -> None: ...

    def observe_queue_backlog(self, measurement: "QueueBacklogMeasurement") -> None: ...

    def record_llm_usage(self, measurement: "LlmUsageMeasurement") -> None: ...


def _require_non_empty(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_non_negative(field_name: str, value: int | float | Decimal) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _validate_outcome(value: str) -> None:
    if value not in SUPPORTED_OUTCOMES:
        raise ValueError("outcome is unsupported")


@dataclass(frozen=True)
class HttpRequestMeasurement:
    """One completed HTTP server request."""

    method: str
    route: str
    status_code: int
    duration_ms: float

    def __post_init__(self) -> None:
        _require_non_empty("method", self.method)
        _require_non_empty("route", self.route)
        if not MIN_HTTP_STATUS_CODE <= self.status_code <= MAX_HTTP_STATUS_CODE:
            raise ValueError("status_code is outside the HTTP range")
        _require_non_negative("duration_ms", self.duration_ms)


@dataclass(frozen=True)
class DatabasePoolMeasurement:
    """Current SQLAlchemy connection pool state."""

    pool_name: str
    size: int
    checked_out: int
    overflow: int

    def __post_init__(self) -> None:
        _require_non_empty("pool_name", self.pool_name)
        _require_non_negative("size", self.size)
        _require_non_negative("checked_out", self.checked_out)
        # SQLAlchemy reports -pool_size before the first overflow connection is opened.
        if self.overflow < -self.size:
            raise ValueError("overflow is below the valid pool range")


@dataclass(frozen=True)
class ExternalCallMeasurement:
    """One completed HTTP or SDK provider operation."""

    provider: str
    operation: str
    outcome: str
    duration_ms: float

    def __post_init__(self) -> None:
        _require_non_empty("provider", self.provider)
        _require_non_empty("operation", self.operation)
        _validate_outcome(self.outcome)
        _require_non_negative("duration_ms", self.duration_ms)


@dataclass(frozen=True)
class WorkerTaskMeasurement:
    """One completed worker task attempt."""

    task_name: str
    queue_name: str
    outcome: str
    duration_ms: float
    retry_count: int

    def __post_init__(self) -> None:
        _require_non_empty("task_name", self.task_name)
        _require_non_empty("queue_name", self.queue_name)
        _validate_outcome(self.outcome)
        _require_non_negative("duration_ms", self.duration_ms)
        _require_non_negative("retry_count", self.retry_count)


@dataclass(frozen=True)
class QueueBacklogMeasurement:
    """Current number of messages waiting in one configured queue."""

    queue_name: str
    size: int

    def __post_init__(self) -> None:
        _require_non_empty("queue_name", self.queue_name)
        _require_non_negative("size", self.size)


@dataclass(frozen=True)
class LlmUsageMeasurement:
    """Provider-reported token usage and an optional externally calculated cost."""

    provider: str
    model: str
    outcome: str
    input_tokens: int
    output_tokens: int
    cost: Decimal | None
    currency: str | None

    def __post_init__(self) -> None:
        _require_non_empty("provider", self.provider)
        _require_non_empty("model", self.model)
        _validate_outcome(self.outcome)
        _require_non_negative("input_tokens", self.input_tokens)
        _require_non_negative("output_tokens", self.output_tokens)
        if self.cost is not None:
            _require_non_negative("cost", self.cost)
            if self.currency is None or not self.currency.strip():
                raise ValueError("currency is required when cost is known")


class TelemetryMetrics:
    """Own stable instruments and record validated measurements."""

    def __init__(self, meter: Meter) -> None:
        self._http_requests: Counter = meter.create_counter(
            "bid_system.http.server.requests", unit="{request}"
        )
        self._http_duration: Histogram = meter.create_histogram(
            "bid_system.http.server.duration", unit="ms"
        )
        self._http_errors: Counter = meter.create_counter(
            "bid_system.http.server.errors", unit="{error}"
        )
        self._database_pool_size: GaugePort = meter.create_gauge(
            "bid_system.database.pool.size", unit="{connection}"
        )
        self._database_pool_checked_out: GaugePort = meter.create_gauge(
            "bid_system.database.pool.checked_out", unit="{connection}"
        )
        self._database_pool_overflow: GaugePort = meter.create_gauge(
            "bid_system.database.pool.overflow", unit="{connection}"
        )
        self._external_requests: Counter = meter.create_counter(
            "bid_system.external.requests", unit="{request}"
        )
        self._external_duration: Histogram = meter.create_histogram(
            "bid_system.external.duration", unit="ms"
        )
        self._worker_tasks: Counter = meter.create_counter("bid_system.worker.tasks", unit="{task}")
        self._worker_duration: Histogram = meter.create_histogram(
            "bid_system.worker.duration", unit="ms"
        )
        self._worker_retries: Counter = meter.create_counter(
            "bid_system.worker.retries", unit="{retry}"
        )
        self._queue_backlog: GaugePort = meter.create_gauge(
            "bid_system.queue.backlog", unit="{message}"
        )
        self._llm_requests: Counter = meter.create_counter(
            "bid_system.llm.requests", unit="{request}"
        )
        self._llm_input_tokens: Counter = meter.create_counter(
            "bid_system.llm.input_tokens", unit="{token}"
        )
        self._llm_output_tokens: Counter = meter.create_counter(
            "bid_system.llm.output_tokens", unit="{token}"
        )
        self._llm_cost: Counter = meter.create_counter("bid_system.llm.cost", unit="1")

    def record_http_request(self, measurement: HttpRequestMeasurement) -> None:
        attributes: dict[str, str | int] = {
            "http.request.method": measurement.method,
            "http.route": measurement.route,
            "http.response.status_code": measurement.status_code,
        }
        self._http_requests.add(1, attributes)
        self._http_duration.record(measurement.duration_ms, attributes)
        if measurement.status_code >= ERROR_HTTP_STATUS_CODE:
            self._http_errors.add(1, attributes)

    def observe_database_pool(self, measurement: DatabasePoolMeasurement) -> None:
        attributes = {"db.pool.name": measurement.pool_name}
        self._database_pool_size.set(measurement.size, attributes)
        self._database_pool_checked_out.set(measurement.checked_out, attributes)
        self._database_pool_overflow.set(measurement.overflow, attributes)

    def record_external_call(self, measurement: ExternalCallMeasurement) -> None:
        attributes = {
            "server.address": measurement.provider,
            "operation.name": measurement.operation,
            "outcome": measurement.outcome,
        }
        self._external_requests.add(1, attributes)
        self._external_duration.record(measurement.duration_ms, attributes)

    def record_worker_task(self, measurement: WorkerTaskMeasurement) -> None:
        attributes = {
            "task.name": measurement.task_name,
            "messaging.destination.name": measurement.queue_name,
            "outcome": measurement.outcome,
        }
        self._worker_tasks.add(1, attributes)
        self._worker_duration.record(measurement.duration_ms, attributes)
        if measurement.retry_count:
            self._worker_retries.add(measurement.retry_count, attributes)

    def observe_queue_backlog(self, measurement: QueueBacklogMeasurement) -> None:
        self._queue_backlog.set(
            measurement.size,
            {"messaging.destination.name": measurement.queue_name},
        )

    def record_llm_usage(self, measurement: LlmUsageMeasurement) -> None:
        attributes = {
            "gen_ai.provider.name": measurement.provider,
            "gen_ai.request.model": measurement.model,
            "outcome": measurement.outcome,
        }
        self._llm_requests.add(1, attributes)
        self._llm_input_tokens.add(measurement.input_tokens, attributes)
        self._llm_output_tokens.add(measurement.output_tokens, attributes)
        if measurement.cost is not None and measurement.currency is not None:
            self._llm_cost.add(
                float(measurement.cost),
                {**attributes, "currency": measurement.currency.upper()},
            )


class NullTelemetryMetrics:
    """No-op sink used when metrics export is disabled."""

    def record_http_request(self, measurement: HttpRequestMeasurement) -> None:
        return None

    def observe_database_pool(self, measurement: DatabasePoolMeasurement) -> None:
        return None

    def record_external_call(self, measurement: ExternalCallMeasurement) -> None:
        return None

    def record_worker_task(self, measurement: WorkerTaskMeasurement) -> None:
        return None

    def observe_queue_backlog(self, measurement: QueueBacklogMeasurement) -> None:
        return None

    def record_llm_usage(self, measurement: LlmUsageMeasurement) -> None:
        return None


_ACTIVE_METRICS: MetricsSink = NullTelemetryMetrics()


def get_metrics_sink() -> MetricsSink:
    """Return the process-wide sink selected during bootstrap."""
    return _ACTIVE_METRICS


def configure_metrics(settings: MetricsSettings, *, environment: str) -> MeterProvider | None:
    """Configure periodic OTLP export and activate the process metrics sink."""
    global _ACTIVE_METRICS
    if not settings.enabled:
        _ACTIVE_METRICS = NullTelemetryMetrics()
        return None
    if settings.otlp_endpoint is None:
        raise ValueError("Metrics OTLP endpoint is required when metrics are enabled")
    endpoint = f"{settings.otlp_endpoint.rstrip('/')}{OTLP_METRICS_PATH}"
    exporter = OTLPMetricExporter(endpoint=endpoint)
    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=int(settings.export_interval_seconds * MILLISECONDS_PER_SECOND),
    )
    provider = MeterProvider(
        metric_readers=[reader],
        resource=Resource.create(
            {
                SERVICE_NAME: settings.service_name,
                DEPLOYMENT_ENVIRONMENT_ATTRIBUTE: environment,
            }
        ),
    )
    metrics.set_meter_provider(provider)
    _ACTIVE_METRICS = TelemetryMetrics(provider.get_meter(INSTRUMENTATION_NAME))
    return provider


def shutdown_metrics(provider: MeterProvider | None) -> None:
    """Flush and stop metric readers during process shutdown."""
    global _ACTIVE_METRICS
    try:
        if provider is not None:
            provider.shutdown()
    finally:
        _ACTIVE_METRICS = NullTelemetryMetrics()


@contextmanager
def observe_external_call(provider: str, operation: str) -> Iterator[None]:
    """Record one external operation without logging request or response content."""
    started_ns = perf_counter_ns()
    outcome = SUCCESS_OUTCOME
    error_type: str | None = None
    try:
        yield
    except BaseException as error:
        outcome = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
        error_type = type(error).__qualname__
        raise
    finally:
        duration_ms = (perf_counter_ns() - started_ns) / NANOSECONDS_PER_MILLISECOND
        measurement = ExternalCallMeasurement(
            provider=provider,
            operation=operation,
            outcome=outcome,
            duration_ms=duration_ms,
        )
        get_metrics_sink().record_external_call(measurement)
        EXTERNAL_LOGGER.info(
            "external_call_completed",
            extra={
                "event_name": "external.call.completed",
                "provider": provider,
                "operation": operation,
                "outcome": outcome,
                "error_type": error_type,
                "duration_ms": duration_ms,
            },
        )


@contextmanager
def observe_worker_task(
    *,
    task_name: str,
    queue_name: str,
    retry_count: int,
) -> Iterator[None]:
    """Record one worker attempt while correlation context is bound by the consumer."""
    started_ns = perf_counter_ns()
    outcome = SUCCESS_OUTCOME
    error_type: str | None = None
    try:
        yield
    except BaseException as error:
        outcome = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
        error_type = type(error).__qualname__
        raise
    finally:
        duration_ms = (perf_counter_ns() - started_ns) / NANOSECONDS_PER_MILLISECOND
        measurement = WorkerTaskMeasurement(
            task_name=task_name,
            queue_name=queue_name,
            outcome=outcome,
            duration_ms=duration_ms,
            retry_count=retry_count,
        )
        get_metrics_sink().record_worker_task(measurement)
        WORKER_LOGGER.info(
            "worker_task_completed",
            extra={
                "event_name": "worker.task.completed",
                "task_name": task_name,
                "queue_name": queue_name,
                "outcome": outcome,
                "error_type": error_type,
                "duration_ms": duration_ms,
            },
        )
