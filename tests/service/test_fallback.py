"""The service tries engines in order and falls back on failure."""

from pathlib import Path

import pytest

from tests.fakes.engines import FakeEngine
from transcriber.service import Transcriber, TranscriptionError

NOTE = Path("/tmp/note.ogg")


def test_the_first_engine_wins_when_it_works() -> None:
    api, local = FakeEngine("openai", "hallo"), FakeEngine("local", "unused")
    assert Transcriber([api, local]).transcribe(NOTE).engine == "openai"
    assert local.calls == []


def test_falls_back_when_the_api_fails() -> None:
    api = FakeEngine("openai", error=RuntimeError("quota exceeded"))
    local = FakeEngine("local", "grüezi mitenand")
    result = Transcriber([api, local]).transcribe(NOTE)
    assert (result.engine, result.text) == ("local", "grüezi mitenand")


def test_all_engines_failing_names_every_error() -> None:
    api = FakeEngine("openai", error=RuntimeError("quota exceeded"))
    local = FakeEngine("local", error=RuntimeError("model missing"))
    with pytest.raises(TranscriptionError, match=r"openai: quota exceeded.*local: model missing"):
        Transcriber([api, local]).transcribe(NOTE)
