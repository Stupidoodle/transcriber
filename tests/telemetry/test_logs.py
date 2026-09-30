"""JSON log lines: fields, trace ids, exceptions and engine failures without their text."""

from __future__ import annotations

import io
import json
import logging
import re
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from opentelemetry import _logs, trace

from tests.fakes.engines import FakeEngine
from transcriber import logs
from transcriber.app import setup_logging
from transcriber.service import Transcriber, TranscriptionError
from transcriber.telemetry import Providers

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.telemetry import Telemetry

pytestmark = pytest.mark.usefixtures("restore_logging")

FOLDER = "christine-instagram"
SAID = "grüezi mitenand"


def _setup(level: str = "INFO", **kwargs: Any) -> io.StringIO:
    stream = io.StringIO()
    logs.setup(level, service="transcriber", stream=stream, **kwargs)
    return stream


def _lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_fields_and_levels() -> None:
    stream = _setup("DEBUG")
    log = logging.getLogger("transcriber")
    log.debug("d")
    log.info("Transcribed a voice note", extra={"engine": "openai", "duration_ms": 812})
    log.warning("w")
    log.error("e")
    log.critical("c")
    lines = _lines(stream)
    assert [x["level"] for x in lines] == ["debug", "info", "warn", "error", "error"]
    line = lines[1]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d", line["time"])
    assert (line["msg"], line["service"], line["engine"], line["duration_ms"]) == (
        "Transcribed a voice note",
        "transcriber",
        "openai",
        812,
    )
    assert "trace_id" not in line


def test_trace_ids_inside_a_span(telemetry: Telemetry) -> None:
    stream = _setup()
    with trace.get_tracer("t").start_as_current_span("s") as span:
        logging.getLogger("transcriber").warning("m")
    (line,) = _lines(stream)
    assert line["trace_id"] == trace.format_trace_id(span.get_span_context().trace_id)
    assert line["span_id"] == trace.format_span_id(span.get_span_context().span_id)


def test_libraries_log_warnings_only_and_the_sdk_never_errors() -> None:
    stream = _setup("DEBUG")
    logging.getLogger("httpx").info("HTTP Request: POST /v1/audio/transcriptions")
    logging.getLogger("opentelemetry.exporter").error("Failed to export")
    assert [(x["logger"], x["level"]) for x in _lines(stream)] == [
        ("opentelemetry.exporter", "warn")
    ]


def test_records_go_out_over_otlp_with_the_trace(telemetry: Telemetry) -> None:
    _setup(provider=_logs.get_logger_provider())
    with trace.get_tracer("t").start_as_current_span("s") as span:
        logging.getLogger("transcriber").warning("Engine failed", extra={"engine": "local"})
    logging.getLogger("opentelemetry.sdk").warning("export failed")  # never looped back
    (record,) = [r.log_record for r in telemetry.logs.get_finished_logs()]
    assert (record.body, record.severity_text) == ("Engine failed", "WARN")
    assert record.attributes is not None and record.attributes["engine"] == "local"
    assert record.trace_id == span.get_span_context().trace_id


def test_a_failing_otlp_provider_does_not_raise() -> None:
    class Broken:
        def get_logger(self, _name: str) -> None:
            raise RuntimeError

    handler = logs.OtlpHandler(Broken())  # type: ignore[arg-type]
    record = logging.LogRecord("transcriber", logging.INFO, "", 0, "m", None, None)
    with patch.object(handler, "handleError") as handled:
        handler.emit(record)
    handled.assert_called_once_with(record)
    assert logs._attribute(["x"]) == "['x']"


def test_the_service_logs_to_stdout_and_ships_logs_when_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    providers = Providers(None, None, _logs.get_logger_provider())  # type: ignore[arg-type]
    with patch("transcriber.app.installed", return_value=providers):
        assert setup_logging("chatty") == "INFO"  # an unknown level falls back to INFO
    logging.getLogger("transcriber").info("up")
    logging.getLogger("transcriber").debug("hidden")
    captured = capsys.readouterr()
    assert [json.loads(x)["msg"] for x in captured.out.splitlines()] == ["up"]
    assert captured.err == ""
    assert any(isinstance(h, logs.OtlpHandler) for h in logging.getLogger().handlers)


def test_a_failing_engine_logs_no_path_and_no_text(tmp_path: Path) -> None:
    stream = _setup()
    note = tmp_path / FOLDER / "340282366841700000000000000000000000077-i1.ogg"
    note.parent.mkdir()
    note.write_bytes(b"x" * 321)
    engine = FakeEngine("openai", error=RuntimeError(f"{note} said {SAID}"))
    with pytest.raises(TranscriptionError):
        Transcriber([engine]).transcribe(note)
    output = stream.getvalue()
    assert FOLDER not in output and SAID not in output and "34028236684170" not in output
    (line,) = _lines(stream)
    assert line["msg"] == "Transcription engine failed"
    assert (line["engine"], line["error_type"], line["suffix"], line["bytes"]) == (
        "openai",
        "RuntimeError",
        ".ogg",
        321,
    )
