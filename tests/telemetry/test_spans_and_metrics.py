"""The bridge's trace goes on here: /transcribe span, one span per engine try, durations."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import httpx2
import pytest
from opentelemetry.trace import SpanKind, StatusCode

from tests.fakes.engines import FakeEngine
from transcriber.app import build_app
from transcriber.engines.openai_api import OpenAIEngine
from transcriber.instruments import HTTP_BUCKETS, TRANSCRIPTION_BUCKETS
from transcriber.service import Transcriber

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.telemetry import Telemetry

TRACE = "0af7651916cd43dd8448eb211c80319c"
PARENT = f"00-{TRACE}-b7ad6b7169203331-01"
FOLDER = "christine-instagram"
SAID = "grüezi mitenand"


@pytest.fixture
def note(tmp_path: Path) -> Path:
    path = tmp_path / FOLDER / "340282366841700000000000000000000000077-i1.ogg"
    path.parent.mkdir()
    path.write_bytes(b"fake audio")
    return path


async def _post(tmp_path: Path, note: Path, *engines: FakeEngine) -> httpx2.Response:
    app = build_app(Transcriber(list(engines)), allowed_root=tmp_path)
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://transcriber") as client:
        return await client.post(
            "/transcribe", json={"path": str(note)}, headers={"traceparent": PARENT}
        )


def _recorded(telemetry: Telemetry) -> str:
    return json.dumps([[s.name, dict(s.attributes or {})] for s in telemetry.spans()])


async def test_the_bridges_trace_continues_through_the_fallback(
    tmp_path: Path, note: Path, telemetry: Telemetry
) -> None:
    api = FakeEngine("openai", error=RuntimeError(f"{note}: quota"))
    local = FakeEngine("local", SAID, audio_seconds=4.2)
    resp = await _post(tmp_path, note, api, local)
    assert resp.json()["engine"] == "local"
    (server,) = telemetry.named("POST /transcribe")
    assert server.kind is SpanKind.SERVER
    assert server.parent is not None and format(server.parent.trace_id, "032x") == TRACE
    assert dict(server.attributes or {})["http.route"] == "/transcribe"
    (openai,) = telemetry.named("transcribe openai")
    (fallback,) = telemetry.named("transcribe local")
    for attempt in (openai, fallback):
        assert attempt.parent is not None and attempt.parent.span_id == server.context.span_id
    assert dict(openai.attributes or {}) == {
        "engine": "openai",
        "outcome": "error",
        "error.type": "RuntimeError",
    }
    assert openai.status.status_code is StatusCode.ERROR and openai.events == ()
    assert dict(fallback.attributes or {}) == {"engine": "local", "outcome": "ok"}
    recorded = _recorded(telemetry)
    assert FOLDER not in recorded and SAID not in recorded and "quota" not in recorded


async def test_durations(tmp_path: Path, note: Path, telemetry: Telemetry) -> None:
    ok = {"engine": "openai", "outcome": "ok"}
    before = telemetry.total("dm.transcription.duration", **ok)
    audio = telemetry.total("dm.transcription.audio.duration", engine="openai")
    await _post(tmp_path, note, FakeEngine("openai", "hallo", audio_seconds=3.0))
    await _post(tmp_path, note, FakeEngine("openai", "hallo"))  # no length reported
    assert telemetry.total("dm.transcription.duration", **ok) == before + 2
    assert telemetry.total("dm.transcription.audio.duration", engine="openai") == audio + 1
    for name, buckets in (
        ("dm.transcription.duration", TRANSCRIPTION_BUCKETS),
        ("dm.transcription.audio.duration", TRANSCRIPTION_BUCKETS),
        ("http.server.request.duration", HTTP_BUCKETS),
    ):
        metric = telemetry.metric(name)
        assert metric is not None and metric.unit == "s"
        assert tuple(metric.data.data_points[0].explicit_bounds) == buckets  # type: ignore[union-attr]
    labels = {"http.route": "/transcribe", "http.request.method": "POST"}
    assert telemetry.total("http.server.request.duration", **labels) >= 2


async def test_every_engine_failing(tmp_path: Path, note: Path, telemetry: Telemetry) -> None:
    error = {"engine": "local", "outcome": "error"}
    before = telemetry.total("dm.transcription.duration", **error)
    resp = await _post(tmp_path, note, FakeEngine("local", error=RuntimeError("boom")))
    assert resp.status_code == 502
    assert telemetry.total("dm.transcription.duration", **error) == before + 1
    (server,) = telemetry.named("POST /transcribe")
    assert dict(server.attributes or {})["http.response.status_code"] == 502
    assert server.status.status_code is StatusCode.ERROR


@pytest.mark.parametrize(
    ("usage", "seconds"),
    [
        (SimpleNamespace(type="duration", seconds=7.5), 7.5),
        (SimpleNamespace(type="tokens", input_tokens=10), None),
        (None, None),
    ],
)
def test_openai_reports_the_audio_length_when_billed_by_it(
    note: Path, usage: object, seconds: float | None
) -> None:
    engine = OpenAIEngine(api_key="sk-test", model="gpt-4o-transcribe")
    engine._client = MagicMock()
    result = SimpleNamespace(text=" hallo ", usage=usage)
    engine._client.audio.transcriptions.create.return_value = result
    transcript = engine.transcribe(note)
    assert (transcript.text, transcript.audio_seconds) == ("hallo", seconds)
