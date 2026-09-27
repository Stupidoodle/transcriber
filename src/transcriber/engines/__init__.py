"""Transcription engines."""

from pathlib import Path
from typing import Protocol

from transcriber.transcript import Transcript


class Engine(Protocol):
    name: str

    def transcribe(self, path: Path) -> Transcript: ...
