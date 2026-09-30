"""Try each engine in order; the first that works wins."""

import contextlib
import logging
import time
from pathlib import Path

from opentelemetry.trace import StatusCode

from transcriber import instruments
from transcriber.engines import Engine
from transcriber.transcript import Transcript

logger = logging.getLogger("transcriber")


def _file(path: Path) -> dict[str, str | int]:
    """Log fields for an audio file: its suffix and, when readable, its size."""
    fields: dict[str, str | int] = {"suffix": path.suffix.lower()}
    with contextlib.suppress(OSError):
        fields["bytes"] = path.stat().st_size
    return fields


class TranscriptionError(Exception):
    """Every engine failed."""


class Transcriber:
    def __init__(self, engines: list[Engine]) -> None:
        self.engines = engines

    def transcribe(self, path: Path) -> Transcript:
        errors: list[str] = []
        for engine in self.engines:
            try:
                return self._attempt(engine, path)
            except Exception as exc:
                errors.append(f"{engine.name}: {exc}")
        raise TranscriptionError("; ".join(errors))

    def _attempt(self, engine: Engine, path: Path) -> Transcript:
        """One engine's try, in its own span, timed; the path and the text are never recorded."""
        start = time.perf_counter()
        with instruments.tracer.start_as_current_span(
            f"transcribe {engine.name}",
            attributes={"engine": engine.name},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                result = engine.transcribe(path)
            except Exception as exc:
                elapsed = time.perf_counter() - start
                span.set_attributes({"outcome": "error", "error.type": type(exc).__name__})
                span.set_status(StatusCode.ERROR)
                labels = {"engine": engine.name, "outcome": "error"}
                instruments.transcription_duration.record(elapsed, labels)
                # The file's suffix and size, never its path: it names the persona and chat.
                fields = _file(path) | {"engine": engine.name, "error_type": type(exc).__name__}
                logger.warning("Transcription engine failed", extra=fields)
                raise
            elapsed = time.perf_counter() - start
            span.set_attribute("outcome", "ok")
            instruments.transcription_duration.record(
                elapsed, {"engine": engine.name, "outcome": "ok"}
            )
            fields = _file(path) | {"engine": engine.name, "duration_ms": round(elapsed * 1000)}
            if result.audio_seconds is not None:
                instruments.audio_duration.record(result.audio_seconds, {"engine": engine.name})
                fields["audio_ms"] = round(result.audio_seconds * 1000)
            logger.info("Transcribed a voice note", extra=fields)
            return result
