"""The result of a transcription."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Transcript:
    text: str
    engine: str  # which engine produced it, e.g. "openai" or "local"
    model: str
    language: str | None = None
    audio_seconds: float | None = None  # length of the audio, when the engine reports it
