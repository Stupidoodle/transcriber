"""Shared test setup: global in-memory telemetry, and no OTEL settings from the shell."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

# No test may export to a real collector.
for _name in [n for n in os.environ if n.startswith("OTEL_")]:
    del os.environ[_name]

import pytest  # noqa: E402
from opentelemetry import _logs, metrics, trace  # noqa: E402
from opentelemetry.sdk._logs import LoggerProvider  # noqa: E402
from opentelemetry.sdk._logs.export import (  # noqa: E402
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from tests.support.telemetry import Telemetry  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator


def _install_telemetry() -> Telemetry:
    """Global in-memory providers, installed once when the suite starts.

    The OpenTelemetry API takes one global provider per process; installing it up
    front gives every test the same state whatever the order.
    """
    spans, logs = InMemorySpanExporter(), InMemoryLogRecordExporter()
    reader = InMemoryMetricReader()
    tracer_provider = TracerProvider(shutdown_on_exit=False)
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    logger_provider = LoggerProvider(shutdown_on_exit=False)
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(logs))
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader], shutdown_on_exit=False))
    _logs.set_logger_provider(logger_provider)
    return Telemetry(spans, reader, logs)


_TELEMETRY = _install_telemetry()


@pytest.fixture
def telemetry() -> Iterator[Telemetry]:
    """The recorded spans and logs (this test's only) and metrics (the session's)."""
    _TELEMETRY.clear()
    yield _TELEMETRY
    _TELEMETRY.clear()
