"""Engine stand-ins that need no model or network."""

from pathlib import Path

from transcriber.transcript import Transcript


class FakeEngine:
    def __init__(
        self,
        name: str,
        text: str | None = None,
        error: Exception | None = None,
        audio_seconds: float | None = None,
    ) -> None:
        self.name = name
        self._text = text
        self._error = error
        self._audio_seconds = audio_seconds
        self.calls: list[Path] = []

    def transcribe(self, path: Path) -> Transcript:
        self.calls.append(path)
        if self._error is not None:
            raise self._error
        return Transcript(
            text=self._text or "",
            engine=self.name,
            model=f"{self.name}-model",
            audio_seconds=self._audio_seconds,
        )
