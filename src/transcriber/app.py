"""HTTP API: POST /transcribe {"path": ...} and GET /health. Loopback only."""

import logging
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from transcriber.config import get_settings
from transcriber.engines import Engine
from transcriber.engines.local_whisper import LocalWhisperEngine
from transcriber.engines.openai_api import OpenAIEngine
from transcriber.service import Transcriber, TranscriptionError
from transcriber.telemetry import configure_telemetry, shutdown_telemetry


def build_app(transcriber: Transcriber, allowed_root: Path) -> Starlette:
    root = allowed_root.resolve()

    async def transcribe(request: Request) -> JSONResponse:
        body = await request.json()
        path = Path(str(body.get("path", ""))).resolve()
        if not path.is_relative_to(root):
            return JSONResponse({"error": "path outside the allowed root"}, status_code=403)
        if not path.is_file():
            return JSONResponse({"error": "no such file"}, status_code=404)
        try:
            result = await run_in_threadpool(transcriber.transcribe, path)
        except TranscriptionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        return JSONResponse(
            {
                "text": result.text,
                "engine": result.engine,
                "model": result.model,
                "language": result.language,
            }
        )

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "engines": [e.name for e in transcriber.engines]})

    return Starlette(
        routes=[Route("/transcribe", transcribe, methods=["POST"]), Route("/health", health)]
    )


def main() -> None:
    configure_telemetry()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    engines: list[Engine] = []
    if settings.openai_api_key:
        engines.append(
            OpenAIEngine(
                settings.openai_api_key.get_secret_value(), settings.transcriber_openai_model
            )
        )
    engines.append(
        LocalWhisperEngine(settings.transcriber_local_model, settings.transcriber_cpu_threads)
    )
    app = build_app(Transcriber(engines), settings.transcriber_allowed_root)
    try:
        uvicorn.run(app, host=settings.transcriber_host, port=settings.transcriber_port)
    finally:
        shutdown_telemetry()
