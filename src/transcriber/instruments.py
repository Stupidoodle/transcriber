"""The transcriber's metrics and tracer, created once on the global providers.

The OpenTelemetry API hands out proxy instruments until ``configure_telemetry``
installs a provider, so recording costs nothing while telemetry is off. Names and
attributes follow the DM platform's telemetry contract; attribute values come from
closed sets (``engine``: openai or local, ``outcome``: ok or error), never from a
path or a transcript.
"""

from opentelemetry import metrics, trace

HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
"""Seconds: one HTTP request to the service."""

TRANSCRIPTION_BUCKETS = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0, 600.0)
"""Seconds: one engine's attempt, or the length of the audio."""

meter = metrics.get_meter("transcriber")
tracer = trace.get_tracer("transcriber")

http_server_duration = meter.create_histogram(
    "http.server.request.duration",
    unit="s",
    description="Duration of HTTP server requests.",
    explicit_bucket_boundaries_advisory=HTTP_BUCKETS,
)
"""Attributes: http.request.method, http.route, http.response.status_code, error.type."""

transcription_duration = meter.create_histogram(
    "dm.transcription.duration",
    unit="s",
    description="One engine's attempt at a transcription, successful or not.",
    explicit_bucket_boundaries_advisory=TRANSCRIPTION_BUCKETS,
)
"""Attributes: engine, outcome."""

audio_duration = meter.create_histogram(
    "dm.transcription.audio.duration",
    unit="s",
    description="Length of the audio an engine transcribed, when the engine reports it.",
    explicit_bucket_boundaries_advisory=TRANSCRIPTION_BUCKETS,
)
"""Attributes: engine."""
