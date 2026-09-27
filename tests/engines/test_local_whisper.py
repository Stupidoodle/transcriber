"""The local engine: text assembly and the German retry for odd language guesses."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from transcriber.engines.local_whisper import LocalWhisperEngine


class FakeModel:
    def __init__(self, guesses: list[str]) -> None:
        self.guesses = guesses
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, path: str, **kwargs: Any) -> tuple[Any, Any]:
        self.calls.append(kwargs)
        language = kwargs.get("language") or self.guesses[len(self.calls) - 1]
        segments = [SimpleNamespace(text=" hallo "), SimpleNamespace(text="zäme ")]
        return iter(segments), SimpleNamespace(language=language)


def _engine(model: FakeModel) -> LocalWhisperEngine:
    return LocalWhisperEngine("large-v3-turbo", cpu_threads=4, load=lambda: model)


def test_joins_segments_and_keeps_a_german_guess() -> None:
    model = FakeModel(["de"])
    result = _engine(model).transcribe(Path("/tmp/n.ogg"))
    assert (result.text, result.language, result.engine) == ("hallo zäme", "de", "local")
    assert len(model.calls) == 1
    assert model.calls[0]["vad_filter"] is True


def test_an_odd_language_guess_is_retried_as_german() -> None:
    # Swiss German is often misdetected (e.g. as Dutch); de/en are what we expect.
    model = FakeModel(["nl"])
    result = _engine(model).transcribe(Path("/tmp/n.ogg"))
    assert result.language == "de"
    assert [c.get("language") for c in model.calls] == [None, "de"]


def test_the_model_loads_once() -> None:
    loads: list[int] = []
    model = FakeModel(["en", "en"])
    engine = LocalWhisperEngine(
        "large-v3-turbo", cpu_threads=4, load=lambda: loads.append(1) or model
    )
    engine.transcribe(Path("/tmp/a.ogg"))
    engine.transcribe(Path("/tmp/b.ogg"))
    assert loads == [1]
