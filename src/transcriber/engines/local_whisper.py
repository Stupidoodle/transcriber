"""faster-whisper on the CPU, the fallback when the API is unavailable."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from transcriber.transcript import Transcript

# Voice notes are German, Swiss German or English. A different guess is usually
# Swiss German misdetected (e.g. as Dutch), so it is retried as German.
EXPECTED_LANGUAGES = {"de", "en"}


class LocalWhisperEngine:
    name = "local"

    def __init__(self, model: str, cpu_threads: int, load: Callable[[], Any] | None = None) -> None:
        self._model_name = model
        self._cpu_threads = cpu_threads
        self._load = load or self._load_faster_whisper
        self._model: Any = None
        # One transcription at a time: the model uses every core.
        self._lock = threading.Lock()

    def _load_faster_whisper(self) -> Any:
        from faster_whisper import WhisperModel  # heavy import, only when needed

        return WhisperModel(
            self._model_name, device="cpu", compute_type="int8", cpu_threads=self._cpu_threads
        )

    def transcribe(self, path: Path) -> Transcript:
        with self._lock:
            if self._model is None:
                self._model = self._load()
            text, language, seconds = self._run(path, language=None)
            if language not in EXPECTED_LANGUAGES:
                text, language, seconds = self._run(path, language="de")
        return Transcript(
            text=text,
            engine=self.name,
            model=self._model_name,
            language=language,
            audio_seconds=seconds,
        )

    def _run(self, path: Path, language: str | None) -> tuple[str, str, float | None]:
        segments, info = self._model.transcribe(
            str(path),
            language=language,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=5,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        seconds = getattr(info, "duration", None)
        return text, language or info.language, float(seconds) if seconds is not None else None
