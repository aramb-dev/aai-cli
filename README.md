# aai-cli

> **Unofficial community CLI; not affiliated with or endorsed by AssemblyAI.**

`aai` is a modular Python command line client for AssemblyAI. It is deliberately independent of a particular project, package manager, or build system.

## Install

```sh
pipx install aai-cli                 # recommended, once published
# or, from a checkout:
pipx install .
# or: python3 -m pip install .

export ASSEMBLYAI_API_KEY='your-key' # put this in your shell secret manager, never Git
# Optional WebSocket commands:
python3 -m pip install 'aai-cli[websocket]'

aai doctor
```

The package installs one `aai` executable. It has no runtime dependency for ordinary HTTP commands; Streaming and WebSocket commands require the optional `websockets` extra.

## Architecture


| Module | Responsibility |
|---|---|
| `core.py` | authentication, HTTP, API errors, safe GET retry/backoff, JSON output |
| `prerecorded.py` | shared async upload, transcript submission, polling, retrieval, exports |
| `sync.py` | synchronous multipart STT |
| `realtime.py` | Streaming v3, temporary tokens, generic WebSocket relay |
| `batteries.py` | content-hash cache, media inspection, batch jobs, SQLite usage ledger, doctor |
| `main.py` | arguments, help, and command routing |

Run `aai --help` for the global contract and `aai COMMAND --help` for exhaustive command-specific options.

---

## Installation, authentication, and security

The credential is read only from `ASSEMBLYAI_API_KEY`. Export it through your shell secret manager, a mode-`0600` local env file that is ignored by Git, or your CI secret store. The CLI never writes credentials.

```sh
# Confirm credentials and connectivity before a large job. This does not upload audio.
aai doctor
```

Do **not** put the permanent key into browser code, mobile code, repositories, or command-line arguments. Use `aai token` to mint a short-lived Streaming v3 token for browser/mobile clients. Rotate the current key because it was pasted into chat.

---

## Output contract: humans, agents, and Unix pipelines

Output automatically selects its audience: when stdout is a terminal, `aai` renders readable tables (and transcript text below its metadata); when stdout is redirected or piped, it emits exactly one compact JSON object. Progress, retry messages, and errors always go to stderr, so stdout remains safe for another tool to consume.

```sh
# One compact JSON object: suitable for JSONL, jq, scripts, or agents
aai --compact transcribe meeting.mp3 --wait | jq -r '.text'

# Put the result in a file; stdout stays empty
aai --output transcript.json transcribe meeting.mp3 --wait

# Request JSON-formatted errors as well
aai --json-errors --compact transcribe missing.mp3 --wait

# Discover command/tool capabilities programmatically
aai --compact schema
```

`--json` forces JSON even on a terminal. `--compact` forces one-line JSON. `--output FILE` writes the final output to a file. `--json-errors` forces error JSON; errors are automatically JSON whenever stderr is redirected, so agents receive one parseable report. These global flags belong before the command; `--dry-run` works both globally and after every command.

### Exit-code and recovery contract

Failures have stable nonzero exit codes and a `next_step` hint. In agent mode the stderr object has `ok`, `error`, `exit_code`, `retryable`, and `next_step`; agents should obey `retryable` rather than retrying indiscriminately.

| Code | Meaning | Agent action |
|---:|---|---|
| 10 | credentials rejected/missing | run `aai doctor`, repair/rotate key; do not retry unchanged |
| 11 | resource/path not found | verify ID, endpoint, and region |
| 12 | invalid input/request | repair options or JSON body |
| 13 | rate limit exhausted | wait/back off before retrying |
| 14 | network failure on a safe read | retry after connectivity/DNS recovers |
| 15 | other API/operational failure | inspect error and `next_step`; never blindly repeat writes |


### stdin

`-` means stdin where documented:

```sh
# Binary audio input
ffmpeg -i clip.mp3 -f wav - | aai sync - --content-type audio/wav
cat audio.mp3 | aai transcribe - --wait       # no content-hash cache for stdin

# JSON request body from stdin
cat transcript-options.json | aai request POST /v2/transcript --params -

# Prompt supplied by another program
printf 'Summarize this transcript.' | aai chat --model MODEL --message user:-

# Voice Agent or another AssemblyAI WS protocol: newline-delimited JSON in/out
event-producer | aai ws wss://agents.assemblyai.com/v1/ws --stdin-json
```

---

## Pre-recorded asynchronous STT

For a local source, `transcribe` uploads raw binary to `/v2/upload`, creates `/v2/transcript`, and, with `--wait`, polls until `completed` or `error`. For an HTTPS source it submits the remote URL without uploading it.

```sh
# Smallest useful form
aai transcribe meeting.mp3 --wait

# Remote source, speaker diarization, and language
aai transcribe https://example.invalid/call.mp3 --wait \
  --set speaker_labels=true --set language_code='"en_us"'

# Medical transcription
aai transcribe consultation.wav --wait --set domain='"medical-v1"' \
  --set speaker_labels=true --set entity_detection=true

# Privacy/redaction
aai transcribe call.wav --wait --set redact_pii=true \
  --set redact_pii_policies='["phone_number","email_address","credit_card_number"]' \
  --set redact_pii_audio=true
```

### Every AssemblyAI request parameter

The CLI does not try to freeze an enormous API schema into its option list. Every documented and future JSON request property is available through either:

```sh
# Complete body inline or loaded from a file
aai transcribe input.mp3 --wait --params @request.json

# Repeatable overrides. Values are JSON: true, 12, "string", [], {}, null.
aai transcribe input.mp3 --wait \
  --set keyterms_prompt='["AssemblyAI","Kubernetes"]' \
  --set prompt='"Names include Ada Lovelace."' \
  --set speaker_options.min_speakers_expected=2 \
  --set speaker_options.max_speakers_expected=4 \
  --set speech_understanding.request.translation.target_languages='["es","de"]'
```

Dots construct nested objects. `--set` overrides fields loaded by `--params`. Consult the official API reference for valid combinations; the CLI sends your JSON unchanged after combining these inputs.

`aai submit SOURCE` is the same submission path but returns immediately. `aai get ID`, `aai list`, `aai delete ID`, `aai search ID TERM...`, and `aai export ID {sentences,paragraphs,srt,vtt,redacted-audio}` manage completed jobs.

### Captions and chapters

```sh
# Direct captions, without any custom word-alignment step
aai export TRANSCRIPT_ID srt --out captions.srt
aai export TRANSCRIPT_ID vtt --out captions.vtt

# Auto Chapters is a legacy Universal-2 feature; AssemblyAI recommends LLM Gateway
# for new chapter-generation work. It may not be compatible with other settings.
aai transcribe talk.mp3 --wait --set speech_models='["universal-2"]' --set auto_chapters=true
```

---

## Batteries: cache, dry runs, batches, usage, and retries

### Content-hash cache

For local `aai transcribe` and `aai batch`, the cache key is SHA-256(audio bytes) plus a canonicalized request configuration. A completed matching result is returned without upload/submission. Cache files are at `~/.cache/aai/`. Changing any request field creates a new key; this prevents, for example, a non-diarized result being returned for a diarized request.

```sh
aai transcribe narration.mp3 --wait             # cache enabled by default
aai transcribe narration.mp3 --wait --no-cache  # force a billable resubmission
```

Only successful completed responses are cached. Remote URLs and stdin cannot be content-hashed by this tool and therefore use the normal API path.

### Cost preview

`--dry-run` never uploads or submits. It uses `ffprobe` when installed, otherwise macOS `afinfo`, to inspect local duration. It is a hard no-write guarantee on every write command (`upload`, `submit`, `delete`, `sync`, `chat`, `request` writes, streaming/WebSocket connections, `transcribe`, and `batch`). Cost estimates require a consciously configured local rate because pricing can vary and the CLI must not invent a billing quote.

Local state follows the XDG base-directory convention: cache in `~/.cache/aai/`, usage ledger in `~/.local/share/aai/usage.sqlite3`, and pricing configuration in `~/.config/aai/config.json` (or their `XDG_*_HOME` overrides).

```sh
# Set YOUR expected USD/audio-hour figure once. 1.23 is only an example; use your own rate.
# This is local metadata, not an API change.
aai pricing 1.23

# Show files, duration, configured estimate, and final request configuration
aai transcribe narration.mp3 --dry-run --set speaker_labels=true
aai batch ~/projects/AnyProject/media --glob '**/*.mp3' --dry-run
```

### Batch transcription

`batch` is project-agnostic: point it at any directory. It filters known media extensions, processes deterministically one file at a time, writes progress to stderr, uses the shared cache, and returns one JSON summary containing per-file results.

```sh
# All supported media recursively
aai batch ~/projects/HistoryOfAI/media --wait

# Just a naming pattern
aai batch ~/projects/HistoryOfAI/media --glob 'paragraph-*.mp3' --wait \
  --set speaker_labels=true

# Agent/pipeline form
aai --compact batch ./media --glob '**/*.wav' --wait > batch-result.jsonl
```

Sequential execution is intentional: it gives predictable spend, avoids accidental rate spikes, and makes a failure attributable to one file. Re-run the same command to resume: completed equivalent files are cache hits.

### Usage ledger

Every local-file transcription through the caching/batch batteries is recorded in `~/.local/share/aai/usage.sqlite3`, including time, source path, hash, transcript ID, estimated media duration, cache status, config, and configured estimated cost.

```sh
aai usage
aai usage --month 2026-09
```

This is local usage visibility, not AssemblyAI’s authoritative invoice; it cannot see API calls made outside `aai`, and duration/cost are only as accurate as local inspection and the rate configured with `aai pricing`.

### Retry behavior

Safe GET requests (including polling) retry transient network errors, HTTP `429`, and HTTP `5xx` up to five attempts with capped exponential backoff, respecting `Retry-After` when supplied. POST upload/submit calls are **not** automatically retried because an ambiguous retry could create a duplicate billable transcript. Errors are explicit and machine-readable with `--json-errors`.

---

## Sync STT, LLM Gateway, streaming, and Voice Agents

```sh
# Sync STT: local audio only; documented 80 ms–120 s range
aai sync short.wav --content-type audio/wav --set language_code='"en"'

# LLM Gateway, OpenAI-compatible request shape
aai chat --model MODEL --message system:'Be concise.' --message user:'Summarize this.'
aai chat --model MODEL --params @chat-completion.json

# Streaming V3 requires a WebSocket package and raw signed-16-bit PCM input
python3 -m pip install --user 'websockets>=12'
aai stream --audio audio.pcm --sample-rate 16000 --set format_turns=true

# Browser/mobile temporary token
aai token --expires 60 --max-session 600
```

`aai request METHOD PATH` is the REST escape hatch for any pre-recorded endpoint not represented by a dedicated command. `aai ws URL` is the WebSocket equivalent for Voice Agent or future protocols.

---

## Research sources

Implementation was checked against AssemblyAI primary documentation, fetched 2026-09-03:

- [Documentation index](https://assemblyai.com/docs/llms.txt)
- [Complete documentation content](https://assemblyai.com/docs/llms-full.txt)
- [Agent integration instructions](https://assemblyai.com/docs/agent-instructions.md)

These specify server-side environment-variable authentication; raw-binary async upload; async transcript creation/polling/exports; Sync multipart transcription; Streaming v3/token endpoints; LLM Gateway chat completions; and Voice Agent WebSocket endpoints.
