# transcriber

Speech-to-text for short voice notes, as a small local HTTP service. It tries
OpenAI's transcription API first (`gpt-4o-transcribe`) and falls back to
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) on the CPU
(`large-v3-turbo`, int8) when the API fails. German, Swiss German and English;
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

`deploy/nexi/` has the systemd user units: the service, and a 15-minute timer that
deploys a moved `main`. A daily GitHub Action upgrades the locked dependencies and
pushes only when the tests pass.
