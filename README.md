# transcriber

Speech-to-text for short voice notes, as a small local HTTP service. It tries
OpenAI's transcription API first (`gpt-4o-transcribe`) and falls back to
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) on the CPU
(`small`, int8; `large-v3-turbo` is more accurate on a CPU with AVX2) when the API fails. German, Swiss German and English;
a language guess outside de/en is retried as German.

```
POST /transcribe {"path": "/abs/path/note.ogg"}  ->  {"text", "engine", "model", "language"}
GET  /health                                     ->  {"ok", "engines"}
```

It listens on 127.0.0.1:8090 and only reads files under `TRANSCRIBER_ALLOWED_ROOT`
(default: the home directory). Settings come from the environment or `.env`:
`OPENAI_API_KEY`, `TRANSCRIBER_OPENAI_MODEL`, `TRANSCRIBER_LOCAL_MODEL`,
`TRANSCRIBER_CPU_THREADS`, `TRANSCRIBER_HOST`, `TRANSCRIBER_PORT`.

```
uv run transcriber      # serve
uv run pytest           # tests (no model or network needed)
```

Logs are JSON lines on stdout (`LOG_LEVEL`, default `info`): the engine, the duration and
the file's suffix and size, never its path or the transcript. Telemetry is off unless
`OTEL_EXPORTER_OTLP_ENDPOINT` is set; then traces, metrics and logs go out over OTLP/HTTP
as service `transcriber` (namespace `dm`). A `POST /transcribe` span continues the
caller's `traceparent`, with one child span per engine try (`transcribe openai`,
`transcribe local`). Metrics: `dm.transcription.duration` (engine, outcome),
`dm.transcription.audio.duration` (engine, when the engine reports the length) and
`http.server.request.duration`. `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER` and
`OTEL_LOGS_EXPORTER` set to `none` leave a signal out; the nexi unit sets the endpoint,
`deployment.environment.name=prod`, a 15 s metric interval and no OTLP logs (the journal
has them).

`deploy/nexi/` has the systemd user units: the service, and a 15-minute timer that
deploys a moved `main`. A daily GitHub Action upgrades the locked dependencies and
pushes only when the tests pass.
