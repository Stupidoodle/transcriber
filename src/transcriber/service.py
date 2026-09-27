"""Try each engine in order; the first that works wins."""

import logging
from pathlib import Path

from transcriber.engines import Engine
from transcriber.transcript import Transcript

logger = logging.getLogger("transcriber")


class TranscriptionError(Exception):
    """Every engine failed."""


class Transcriber:
    def __init__(self, engines: list[Engine]) -> None:
        self.engines = engines

    def transcribe(self, path: Path) -> Transcript:
        errors: list[str] = []
        for engine in self.engines:
            try:
                return engine.transcribe(path)
            except Exception as exc:
                logger.warning("%s failed on %s: %s", engine.name, path.name, exc)
                errors.append(f"{engine.name}: {exc}")
        raise TranscriptionError("; ".join(errors))
