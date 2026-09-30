"""Try each engine in order; the first that works wins."""

import contextlib
import logging
from pathlib import Path

from transcriber.engines import Engine
from transcriber.transcript import Transcript

logger = logging.getLogger("transcriber")


def _file(path: Path) -> dict[str, str | int]:
    """Log fields for an audio file: its suffix and, when readable, its size."""
    fields: dict[str, str | int] = {"suffix": path.suffix.lower()}
    with contextlib.suppress(OSError):
        fields["bytes"] = path.stat().st_size
    return fields


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
                # The file's suffix and size, never its path: it names the persona and chat.
                fields = _file(path) | {"engine": engine.name, "error_type": type(exc).__name__}
                logger.warning("Transcription engine failed", extra=fields)
                errors.append(f"{engine.name}: {exc}")
        raise TranscriptionError("; ".join(errors))
