"""OpenAI's transcription API, the primary engine."""

from pathlib import Path

from openai import OpenAI

from transcriber.transcript import Transcript


class OpenAIEngine:
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key, timeout=60.0, max_retries=1)
        self._model = model

    def transcribe(self, path: Path) -> Transcript:
        with path.open("rb") as audio:
            result = self._client.audio.transcriptions.create(model=self._model, file=audio)
        # Models billed by audio length report it; token-billed ones (gpt-4o-transcribe) don't.
        usage = getattr(result, "usage", None)
        by_length = getattr(usage, "type", "") == "duration"
        seconds: float | None = getattr(usage, "seconds", None) if by_length else None
        return Transcript(
            text=result.text.strip(), engine=self.name, model=self._model, audio_seconds=seconds
        )
