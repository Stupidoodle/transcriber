# Observability

What the transcriber reports, under which names, and how to read the OpenAI-first,
local-fallback chain from it. It follows the DM platform's telemetry contract (service
`transcriber`, namespace `dm`), like the WhatsApp and Instagram bridges that call it, so
one voice note is one trace across them. A rename is a breaking change for the dashboards.

Off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set (see the README for the switches).
`service.instance.id` is the hostname, `service.version` the package version.

## Privacy

Never in a span, a metric or a log line: the audio file's path (it names the persona and
the chat), the transcript, or an exception's message. Spans and logs carry the engine, the
outcome, the error class, durations, and the file's suffix and size.

## Metrics

| instrument | type, unit | attributes | Prometheus |
|---|---|---|---|
| `dm.transcription.duration` | histogram `s` | engine (`openai` `local`), outcome (`ok` `error`) | `dm_transcription_duration_seconds` |
| `dm.transcription.audio.duration` | histogram `s` | engine | `dm_transcription_audio_duration_seconds` |
| `http.server.request.duration` | histogram `s` (semconv) | http.request.method, http.route, http.response.status_code, error.type | `http_server_request_duration_seconds` |

- One `dm.transcription.duration` sample per engine attempt, successful or not. A request
  that falls back records two: `openai` with `outcome="error"`, then `local`.
- `dm.transcription.audio.duration` is the length of the audio an engine transcribed, when
  it reports one.
- Buckets (seconds): transcription and audio `0.5 1 2 5 10 20 30 60 120 300 600`; HTTP
  `0.005 0.01 0.025 0.05 0.1 0.25 0.5 1 2.5 5 10 30`.
- A histogram has no series until its first sample, so after a restart with no voice note
  yet, `dm_transcription_*` is absent: that is no traffic, not a fault. `/health` probes
  still show up in `http_server_request_duration_seconds{http_route="/health"}`.
- Exemplars: samples recorded inside a sampled span carry its trace id; click one in
  Grafana to open the trace.

## Traces

| span | kind | attributes |
|---|---|---|
| `POST /transcribe`, `GET /health` | SERVER, continues the caller's `traceparent` | `http.request.method`, `http.route`, `http.response.status_code`, `error.type` |
| `transcribe <engine>` | INTERNAL, one per attempt | `engine`, `outcome`, `error.type` on failure |

The bridge's event span (or the persona's tool call, for an on-demand transcription) is the
parent of `POST /transcribe`, so the attempts sit inside the message's trace.

## Logs

JSON lines on stdout: `time`, `level`, `msg`, `service`, `trace_id`/`span_id`, then
`engine`, `duration_ms`, `audio_ms`, `suffix`, `bytes`, `error_type`. `Transcribed a voice
note` at info per success; `Transcription engine failed` at warn per failed attempt (a
fallback follows when an engine is left). A request where every engine failed answers 502.

## Runbook hints

| question | query |
|---|---|
| How often does OpenAI fail over to local? | `sum(rate(dm_transcription_duration_seconds_count{engine="openai",outcome="error"}[1d])) / sum(rate(dm_transcription_duration_seconds_count{engine="openai"}[1d]))` |
| How slow is each engine? | `histogram_quantile(0.9, sum by (le, engine) (rate(dm_transcription_duration_seconds_bucket{outcome="ok"}[1d])))` |
| Real-time factor | `sum by (engine) (rate(dm_transcription_duration_seconds_sum{outcome="ok"}[1d])) / sum by (engine) (rate(dm_transcription_audio_duration_seconds_sum[1d]))` (below 1 is faster than real time) |
| Requests that failed outright | `sum(rate(http_server_request_duration_seconds_count{service_name="transcriber",http_route="/transcribe",http_response_status_code="502"}[1h]))` |
| Is it up? | `curl -s 127.0.0.1:8090/health` lists the engines it will try. |
