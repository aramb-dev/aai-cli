import argparse
from .core import base, body, emit, request
from . import batteries, interactive, prerecorded, realtime, sync

FMT = argparse.RawDescriptionHelpFormatter
ALL_FIELDS = """All request fields: use --set KEY=JSON_VALUE (dots create nested objects), or --params JSON / @file.json.
Examples: --set speaker_labels=true  --set keyterms_prompt='["Acme","Kubernetes"]'
          --set speaker_options.min_speakers_expected=2
          --set speech_understanding.request.translation.target_languages='["es","de"]'
This escape hatch accepts every current and future API request property."""

def parser(sub, name, description):
    p = sub.add_parser(name, description=description, formatter_class=FMT, help=description.split("\n", 1)[0])
    p.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="preview this write command; do not call a write endpoint")
    return p

def add_payload(p):
    p.add_argument("--params", metavar="JSON|@FILE", help="complete JSON request object; @path reads a JSON file")
    p.add_argument("--set", action="append", default=[], metavar="KEY=JSON", help="set/override any JSON field; repeatable; supports dotted nested keys")

def stt(sub, name, description, optional_source=False):
    p = parser(sub, name, description + "\n\n" + ALL_FIELDS)
    p.add_argument("source", nargs="?" if optional_source else None, help="local audio/video path (uploaded as raw binary), or http(s) media URL")
    p.add_argument("--region", choices=["global", "eu"], default="global", help="data-residency endpoint (default: %(default)s)")
    add_payload(p)
    return p

def main():
    usage = """AssemblyAI command line client. Credentials come from ASSEMBLYAI_API_KEY.

Common workflows:
  aai transcribe meeting.mp3 --wait --set speaker_labels=true
  aai transcribe https://example.test/call.wav --wait --set prompt='"Names: Ada, Linus"'
  aai sync clip.wav --set language_code='"en"'
  aai chat --model MODEL --message system:'Be concise.' --message user:'Hello'
Run 'aai COMMAND --help' for detailed options and examples.

Automation: all successful structured results are JSON on stdout.  Use --compact for JSONL-friendly one-line output, --output FILE to avoid mixing data with shell output, and --json-errors for JSON error objects on stderr. A source/FILE value of '-' reads binary audio from stdin; --params - reads JSON from stdin."""
    root = argparse.ArgumentParser(prog="aai", description=usage, formatter_class=FMT)
    root.add_argument("--json", action="store_true", help="explicitly request JSON output (the default for structured results)")
    root.add_argument("--compact", action="store_true", help="emit structured JSON on exactly one line; suitable for JSONL/pipes")
    root.add_argument("--output", metavar="FILE", help="write final output to FILE instead of stdout")
    root.add_argument("--json-errors", action="store_true", help="emit failures as {ok:false,error:...} JSON on stderr")
    root.add_argument("--dry-run", action="store_true", help="preview a write command; command-level --dry-run is also accepted")
    sub = root.add_subparsers(dest="command", required=True, title="commands")

    p = stt(sub, "transcribe", "Async pre-recorded STT: upload/submit media and wait for the final transcript by default. Use -i for guided terminal mode.", optional_source=True)
    wait = p.add_mutually_exclusive_group(); wait.add_argument("--wait", dest="wait", action="store_true", default=True, help="wait/poll until completed (default)"); wait.add_argument("--no-wait", dest="wait", action="store_false", help="return queued job immediately")
    p.add_argument("-i", "--interactive", action="store_true", help="guided terminal workflow: choose source, profile, and automatic exports")
    p.add_argument("--interval", type=float, default=3, help="seconds between polling requests (default: %(default)s)")
    p.add_argument("--export", dest="exports", action="append", choices=["json", "text", "srt", "vtt", "paragraphs", "sentences"], default=[], help="save completed result beside input; repeatable")
    p.add_argument("--out-dir", help="directory for --export files (default: input directory; URLs use current directory)")
    cache = p.add_mutually_exclusive_group(); cache.add_argument("--cache", dest="cache", action="store_true", default=True, help="reuse/store completed local-file transcript cache (default)"); cache.add_argument("--no-cache", dest="cache", action="store_false", help="always submit local audio again")
    stt(sub, "submit", "Async pre-recorded STT: upload/submit media and print queued job immediately.")

    p = parser(sub, "upload", "Upload a local media file and return AssemblyAI's temporary upload_url.")
    p.add_argument("file", help="local audio/video file")
    p.add_argument("--region", choices=["global", "eu"], default="global", help="upload endpoint data residency (default: %(default)s)")
    for name, text in (("get", "Retrieve a transcript object, including text/status/errors."), ("delete", "Permanently delete a transcript.")):
        p = parser(sub, name, text); p.add_argument("id", help="AssemblyAI transcript UUID"); p.add_argument("--region", choices=["global", "eu"], default="global", help="endpoint data residency")
    p = parser(sub, "list", "List transcript jobs. Pagination URLs are returned in page_details.")
    p.add_argument("--limit", type=int, help="number of jobs to return (must be >= 1)"); p.add_argument("--status", help="filter status, e.g. queued, processing, completed, error"); p.add_argument("--created-on", help="filter by creation date accepted by the API"); p.add_argument("--region", choices=["global", "eu"], default="global", help="endpoint data residency")
    p = parser(sub, "export", "Retrieve a completed transcript's derived result.")
    p.add_argument("id", help="AssemblyAI transcript UUID"); p.add_argument("kind", choices=["sentences", "paragraphs", "srt", "vtt", "redacted-audio"], help="result type; srt/vtt are caption files")
    p.add_argument("--out", help="write srt or vtt bytes to this path instead of stdout"); p.add_argument("--region", choices=["global", "eu"], default="global", help="endpoint data residency")
    p = parser(sub, "search", "Find individual terms or phrases (up to five words each) in a completed transcript.")
    p.add_argument("id", help="AssemblyAI transcript UUID"); p.add_argument("words", nargs="+", help="one or more search terms"); p.add_argument("--region", choices=["global", "eu"], default="global", help="endpoint data residency")

    p = parser(sub, "sync", "Synchronous STT for a local 80 ms–120 s audio clip. Sends multipart audio + optional config.")
    p.add_argument("file", help="local audio file; remote URLs are not supported by Sync API"); p.add_argument("--model", default="universal-3-5-pro", help="required X-AAI-Model value (default: %(default)s)"); p.add_argument("--content-type", default="audio/wav", help="audio MIME type for multipart upload (default: %(default)s)"); add_payload(p)
    p = parser(sub, "token", "Mint a single-use Streaming v3 browser/mobile token; never expose the permanent key to clients.")
    p.add_argument("--expires", type=int, default=60, help="token expiry seconds (default: %(default)s)"); p.add_argument("--max-session", type=int, help="maximum downstream session duration in seconds (60–10800)"); p.add_argument("--region", choices=["global", "us", "eu"], default="global", help="streaming data residency")
    p = parser(sub, "chat", "Call the OpenAI-compatible AssemblyAI LLM Gateway /v1/chat/completions.\n\n" + ALL_FIELDS)
    p.add_argument("--model", required=True, help="gateway model identifier"); p.add_argument("--message", action="append", default=[], metavar="ROLE:TEXT", help="chat message; repeat for system/user/assistant messages"); p.add_argument("--region", choices=["us", "eu"], default="us", help="gateway endpoint; EU supports Claude/Gemini only"); add_payload(p)
    p = parser(sub, "request", "Raw escape hatch for any Pre-recorded STT REST endpoint.\n\nExample: aai request GET /v2/transcript/UUID\n" + ALL_FIELDS)
    p.add_argument("method", help="HTTP method, e.g. GET, POST, DELETE"); p.add_argument("path", help="API path, e.g. /v2/transcript/UUID"); p.add_argument("--query", action="append", default=[], metavar="KEY=VALUE", help="query string field; repeatable"); p.add_argument("--region", choices=["global", "eu"], default="global", help="endpoint data residency"); add_payload(p)
    p = parser(sub, "stream", "Streaming STT v3 over WebSocket. Requires: python3 -m pip install --user 'websockets>=12'\nInput must be raw signed 16-bit PCM (not a WAV container).")
    p.add_argument("--audio", help="raw PCM s16le input file; omit for a receive-only socket"); p.add_argument("--sample-rate", type=int, required=True, help="PCM samples per second, e.g. 16000"); p.add_argument("--speech-model", default="universal-3-5-pro", help="Streaming v3 speech model (default: %(default)s)"); p.add_argument("--encoding", default="pcm_s16le", help="audio encoding (default: %(default)s)"); p.add_argument("--chunk-ms", type=int, default=100, help="audio bytes per send in milliseconds (default: %(default)s)"); p.add_argument("--region", choices=["global", "us", "eu"], default="global", help="streaming data residency"); p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="any Streaming v3 connection query parameter; repeatable")
    p = parser(sub, "ws", "Generic authenticated WebSocket relay, including Voice Agent API and future WebSocket APIs.\nWith --stdin-json, forward newline-delimited JSON from stdin before printing server messages.")
    p.add_argument("url", help="WebSocket URL, e.g. wss://agents.assemblyai.com/v1/ws"); p.add_argument("--query", action="append", default=[], metavar="KEY=VALUE", help="URL query parameter; repeatable"); p.add_argument("--stdin-json", action="store_true", help="send newline-delimited JSON protocol events from stdin")
    p = parser(sub, "batch", "Transcribe every supported audio/video file under a directory with one shared config, content-hash cache, dry-run, progress, and usage ledger.\n\nExample: aai batch ~/projects/Any/media --glob '**/*.mp3' --wait --set speaker_labels=true\n" + ALL_FIELDS)
    p.add_argument("directory", help="directory to scan recursively or non-recursively according to --glob"); p.add_argument("--glob", default="**/*", help="path glob relative to directory (default: %(default)s)"); p.add_argument("--region", choices=["global", "eu"], default="global", help="endpoint data residency"); p.add_argument("--wait", action="store_true", default=True, help="wait for each result before next file (default)"); cache = p.add_mutually_exclusive_group(); cache.add_argument("--cache", dest="cache", action="store_true", default=True, help="reuse completed content/config cache (default)"); cache.add_argument("--no-cache", dest="cache", action="store_false", help="always submit matching local files again"); add_payload(p)
    p = parser(sub, "usage", "Report the local SQLite transcription ledger across every project. Only records calls made through aai.")
    p.add_argument("--month", help="ISO month filter, e.g. 2026-09; default: all recorded history")
    p = parser(sub, "doctor", "Validate ASSEMBLYAI_API_KEY against the API before a batch; does not transcribe audio.")
    p = parser(sub, "pricing", "Set the local estimated USD per audio hour used by dry-run and usage. This is not an AssemblyAI quote.")
    p.add_argument("usd_per_audio_hour", type=float, help="your chosen estimated USD per audio hour")
    p = parser(sub, "schema", "Print a machine-readable capability manifest for coding agents and tool runners.")
    p.add_argument("--compact", action="store_true", default=argparse.SUPPRESS, help="accepted after command too; output one JSON line")

    args = root.parse_args()
    if args.json_errors: __import__("os").environ["AAI_JSON_ERRORS"] = "1"
    if args.command == "transcribe" and args.interactive: args = interactive.run(args)
    if args.command == "transcribe" and not args.source: root.error("SOURCE is required unless using --interactive/-i")
    # A dry run is a hard no-write guarantee. transcribe/batch additionally inspect media/cost below.
    write_commands = {"upload", "submit", "delete", "sync", "chat", "stream", "ws"}
    is_write = args.command in write_commands or (args.command == "request" and args.method.upper() not in ("GET", "HEAD"))
    if args.dry_run and args.command not in ("transcribe", "batch") and is_write:
        result = {"ok": True, "dry_run": True, "command": args.command, "action": "No network write was made.", "next_step": "Remove --dry-run to execute after reviewing this command's arguments."}
        emit(result, compact=args.compact, output=getattr(args, "output", None), json_mode=args.json)
        return
    if args.command == "transcribe":
        if args.source.startswith(("http://", "https://", "-")):
            result = ({"ok": True, "dry_run": True, "source": args.source, "request": body(args), "action": "No upload or transcript submission was made; remote/stdin duration and cache key cannot be determined locally."} if args.dry_run else prerecorded.submit(args))
        else: result = batteries.one(args.source, body(args), args.region, args.wait, args.cache, args.dry_run)
        if not args.dry_run and args.wait:
            written = interactive.save_exports(result, args.source, args.exports, args.out_dir, args.region)
            if written: result["_aai_exports"] = written
    elif args.command == "submit": result = prerecorded.submit(args)
    elif args.command == "upload": result = prerecorded.upload(args.file, args.region)
    elif args.command in ("get", "list", "delete", "export", "search"): result = prerecorded.transcript(args)
    elif args.command == "sync": result = sync.transcribe(args)
    elif args.command == "token": result = realtime.token(args)
    elif args.command == "batch": result = batteries.batch(args)
    elif args.command == "usage": result = batteries.usage(args)
    elif args.command == "doctor": result = batteries.doctor()
    elif args.command == "pricing": result = batteries.setup_price(args)
    elif args.command == "stream": return realtime.stream(args)
    elif args.command == "ws": return realtime.generic_ws(args)
    elif args.command == "schema":
        result = {"name": "aai", "structured_output": "JSON stdout", "stdin": {"audio": "upload/transcribe/sync source '-'", "json": "--params -", "websocket": "ws --stdin-json"}, "commands": {"transcribe": "async STT with cache/dry-run", "batch": "directory batch STT", "usage": "local spend ledger", "doctor": "auth validation", "sync": "sync STT", "stream": "Streaming v3 WebSocket", "chat": "LLM Gateway", "ws": "Voice Agent/generic WebSocket", "request": "raw REST"}, "universal_request_fields": {"complete_body": "--params JSON or @file.json", "override": "--set dotted.key=JSON_VALUE"}}
    elif args.command == "chat":
        data = body(args); data["model"] = args.model
        if args.message:
            if any(":" not in item for item in args.message): root.error("--message must be ROLE:TEXT")
            data["messages"] = [{"role": item.split(":", 1)[0], "content": (__import__("sys").stdin.read() if item.split(":", 1)[1] == "-" else item.split(":", 1)[1])} for item in args.message]
        result = request("POST", "/v1/chat/completions", data, base_url="https://llm-gateway.eu.assemblyai.com" if args.region == "eu" else "https://llm-gateway.assemblyai.com")
    else: result = request(args.method.upper(), args.path, body(args) if (args.params or args.set) else None, query=dict(item.split("=", 1) for item in args.query), base_url=base(args.region))
    emit(result, compact=args.compact, output=getattr(args, "output", None), json_mode=args.json)
if __name__ == "__main__": main()
