"""HTTP contract: POST /transcribe {path}, GET /health."""

from pathlib import Path

import httpx2
import pytest

from tests.fakes.engines import FakeEngine
from transcriber.app import build_app
from transcriber.service import Transcriber


def _client(tmp_path: Path, *engines: FakeEngine) -> httpx2.AsyncClient:
    app = build_app(Transcriber(list(engines)), allowed_root=tmp_path)
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://transcriber"
    )


@pytest.fixture
def note(tmp_path: Path) -> Path:
    path = tmp_path / "note.ogg"
    path.write_bytes(b"fake audio")
    return path


async def test_transcribes_a_file(tmp_path: Path, note: Path) -> None:
    async with _client(tmp_path, FakeEngine("openai", "hallo")) as client:
        resp = await client.post("/transcribe", json={"path": str(note)})
    assert resp.status_code == 200
    assert resp.json() == {
        "text": "hallo",
        "engine": "openai",
        "model": "openai-model",
        "language": None,
    }


async def test_a_missing_file_is_404(tmp_path: Path) -> None:
    async with _client(tmp_path, FakeEngine("openai", "x")) as client:
        resp = await client.post("/transcribe", json={"path": str(tmp_path / "nope.ogg")})
    assert resp.status_code == 404


async def test_a_path_outside_the_allowed_root_is_403(tmp_path: Path) -> None:
    async with _client(tmp_path, FakeEngine("openai", "x")) as client:
        resp = await client.post("/transcribe", json={"path": "/etc/passwd"})
    assert resp.status_code == 403


async def test_every_engine_failing_is_502(tmp_path: Path, note: Path) -> None:
    async with _client(tmp_path, FakeEngine("local", error=RuntimeError("boom"))) as client:
        resp = await client.post("/transcribe", json={"path": str(note)})
    assert resp.status_code == 502
    assert "boom" in resp.json()["error"]


async def test_health_lists_the_engines(tmp_path: Path) -> None:
    async with _client(tmp_path, FakeEngine("openai"), FakeEngine("local")) as client:
        resp = await client.get("/health")
    assert resp.json() == {"ok": True, "engines": ["openai", "local"]}
