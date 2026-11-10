# Changelog

All notable changes to aai-cli. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.4.0

### Fixed
- `transcribe --interval` was ignored for local files; polling always ran every 3 seconds.
- `sync` posted to the wrong path. It now uses `POST /v1/transcribe`, accepts `--region global|us|eu`, rejects files over 256 MB, and guesses the content type from the file extension.
- `stream` sent audio files as fast as possible and waited for a `TurnIsFinal` message that Streaming v3 never sends. It now sends at real-time pace, validates `--chunk-ms` (50–1000), and handles `pcm_mulaw` chunk sizes.
- `usage` counted cache hits as billed audio. Cache hits now cost nothing and are reported as `cached_audio_seconds`.
- `batch --wait` could not be turned off; `--no-wait` and `--interval` are now available.
- Project URLs pointed to a repository that does not exist.

### Changed
- `stream` defaults to `universal-3-6-pro`, the current Streaming v3 default.
- Help text and README reflect the current API: `speech_models` defaults to Universal-3.5 Pro with Universal-2 fallback, Sync handles 80 ms–20 min, and summaries go through Speech Understanding.
- Help and README show that `--set` sends non-JSON values as plain strings, so `--set language_code=ar` works without extra quotes.
- Local files are hashed once per transcription instead of two or three times.

### Added
- `aai --version`.
- Ctrl-C during `stream` sends `Terminate` so the server flushes the last turn.
- Offline test suite, CI on Python 3.9–3.14, and a tag-driven release that publishes to PyPI and attaches a single-file `aai.pyz` to the GitHub release.

## 0.3.0

- Queue exports for `transcribe --no-wait` and process them with `aai exports --run`.
- Interactive mode (`transcribe -i`); `transcribe` waits by default.
