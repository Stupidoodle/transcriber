"""Telemetry switches, resource and providers: off by default, OTLP when an endpoint is set."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from transcriber import telemetry
from transcriber.telemetry import build_providers, enabled, resource, shutdown_providers, signal_on

if TYPE_CHECKING:
    from collections.abc import Iterator

ENDPOINT = {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318"}


def test_off_without_an_endpoint() -> None:
    assert enabled({}) is False
    assert enabled({"OTEL_EXPORTER_OTLP_ENDPOINT": " "}) is False
    assert telemetry.configure_telemetry({}) is False
    assert telemetry.installed() is None
    telemetry.shutdown_telemetry()  # nothing installed: nothing to do


def test_on_with_an_endpoint_unless_disabled() -> None:
    assert enabled(ENDPOINT) is True
    assert enabled(ENDPOINT | {"OTEL_SDK_DISABLED": "true"}) is False


def test_each_signal_can_be_left_out() -> None:
    assert signal_on("logs", {"OTEL_LOGS_EXPORTER": "none"}) is False
    assert signal_on("metrics", {}) is True


def test_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    attributes = resource({}).attributes
    assert attributes["service.name"] == "transcriber"
    assert attributes["service.namespace"] == "dm"
    assert attributes["service.instance.id"]
    assert attributes["service.version"]
    monkeypatch.setenv("OTEL_SERVICE_NAME", "renamed")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment.name=prod")
    attributes = resource({"OTEL_SERVICE_NAME": "renamed"}).attributes
    assert attributes["service.name"] == "renamed"
    assert attributes["deployment.environment.name"] == "prod"


def test_test_processors_carry_the_resource() -> None:
    spans, reader = InMemorySpanExporter(), InMemoryMetricReader()
    providers = build_providers(
        env={"OTEL_LOGS_EXPORTER": "none"},
        span_processor=SimpleSpanProcessor(spans),
        metric_reader=reader,
    )
    assert providers.tracer is not None and providers.meter is not None
    assert providers.logger is None
    assert "ParentBased" in providers.tracer.sampler.get_description()
    providers.tracer.get_tracer("t").start_span("s").end()
    (span,) = spans.get_finished_spans()
    assert span.resource.attributes["service.name"] == "transcriber"
    shutdown_providers(providers)


def test_none_leaves_every_signal_out() -> None:
    env = {f"OTEL_{s}_EXPORTER": "none" for s in ("TRACES", "METRICS", "LOGS")}
    assert build_providers(env=env).all() == []


class _Collector(BaseHTTPRequestHandler):
    """A loopback OTLP collector: records what was posted, optionally hangs."""

    posts: ClassVar[list[str]] = []
    hang = 0.0

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self.posts.append(self.path)
        time.sleep(self.hang)
        self.send_response(200)
        self.send_header("content-length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the test output quiet."""


@pytest.fixture
def collector() -> Iterator[tuple[str, type[_Collector]]]:
    handler = type("Collector", (_Collector,), {"posts": [], "hang": 0.0})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", handler
    finally:
        server.shutdown()
        server.server_close()


def test_configure_installs_once_and_shuts_down(
    collector: tuple[str, type[_Collector]], monkeypatch: pytest.MonkeyPatch
) -> None:
    installed: list[object] = []
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", installed.append)
    monkeypatch.setattr(telemetry.metrics, "set_meter_provider", installed.append)
    monkeypatch.setattr(telemetry._logs, "set_logger_provider", installed.append)
    env = {"OTEL_EXPORTER_OTLP_ENDPOINT": collector[0]}
    assert telemetry.configure_telemetry(env) is True
    providers = telemetry.installed()
    assert telemetry.configure_telemetry(env) is True
    assert providers is not None and telemetry.installed() is providers
    assert installed == providers.all()
    telemetry.shutdown_telemetry()
    assert telemetry.installed() is None


_SCRIPT = """
import json, sys, time
from opentelemetry import _logs, metrics, trace
from transcriber import telemetry
on = telemetry.configure_telemetry()
provider = type(trace.get_tracer_provider()).__name__
trace.get_tracer("t").start_span("s").end()
metrics.get_meter("t").create_counter("c").add(1)
_logs.get_logger("t").emit(body="hello")
start = time.monotonic()
telemetry.shutdown_telemetry(timeout=float(sys.argv[1]))
print(json.dumps({"on": on, "provider": provider, "shutdown": time.monotonic() - start}))
"""


def _run(env: dict[str, str], timeout: float = 5.0) -> dict[str, Any]:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("OTEL_")}
    result = subprocess.run(  # our own interpreter and script, fixed argv
        [sys.executable, "-c", _SCRIPT, str(timeout)],
        env=clean | env,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    out: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return out


def test_a_process_without_an_endpoint_installs_nothing() -> None:
    out = _run({})
    assert (out["on"], out["provider"]) == (False, "ProxyTracerProvider")


def test_a_process_with_an_endpoint_exports_every_signal(
    collector: tuple[str, type[_Collector]],
) -> None:
    url, handler = collector
    out = _run({"OTEL_EXPORTER_OTLP_ENDPOINT": url})
    assert (out["on"], out["provider"]) == (True, "TracerProvider")
    assert set(handler.posts) == {"/v1/traces", "/v1/metrics", "/v1/logs"}


def test_a_dead_collector_does_not_hold_the_exit(
    collector: tuple[str, type[_Collector]],
) -> None:
    url, handler = collector
    handler.hang = 30.0
    out = _run({"OTEL_EXPORTER_OTLP_ENDPOINT": url}, timeout=1.0)
    assert out["on"] is True
    assert out["shutdown"] < 3.0
