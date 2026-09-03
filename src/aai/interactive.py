"""Deliberately small terminal workflow for the common 'transcribe this file' case."""
import json, os, sys, time
from pathlib import Path
from .core import base, fail, request

PENDING = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "aai" / "pending-exports.json"

def run(args):
    if not sys.stdin.isatty(): fail("--interactive requires a terminal", 12, False, "Pass SOURCE and explicit flags in non-interactive automation.")
    print("AssemblyAI interactive transcription", file=sys.stderr)
    args.source = input("Audio/video file or HTTPS URL: ").strip()
    if not args.source: fail("no source supplied", 12, False, "Re-run and provide a local path or HTTPS URL.")
    profile = input("Profile [1] plain, [2] meeting (speaker labels), [3] medical: ").strip() or "1"
    if profile == "2": args.set.append("speaker_labels=true")
    elif profile == "3": args.set.extend(["domain=\"medical-v1\"", "speaker_labels=true", "entity_detection=true"])
    elif profile != "1": fail("unknown profile", 12, False, "Choose 1, 2, or 3.")
    choice = input("Save exports [1] transcript JSON + TXT + SRT, [2] JSON only, [3] none: ").strip() or "1"
    args.exports = {"1": ["json", "text", "srt"], "2": ["json"], "3": []}.get(choice)
    if args.exports is None: fail("unknown export choice", 12, False, "Choose 1, 2, or 3.")
    args.wait = True
    return args

def _load_pending():
    return json.loads(PENDING.read_text()) if PENDING.exists() else []

def _save_pending(items):
    PENDING.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(items, indent=2) + "\n"); os.chmod(PENDING, 0o600)

def queue_exports(result, source, kinds, output_dir, region):
    """Persist requested exports when --no-wait returns a queued transcript."""
    if not kinds or not result.get("id"): return None
    items = _load_pending()
    item = {"transcript_id": result["id"], "source": source, "exports": kinds, "out_dir": output_dir, "region": region}
    items = [old for old in items if old["transcript_id"] != item["transcript_id"]] + [item]
    _save_pending(items)
    return item

def pending():
    """Read the durable queue without an API request."""
    return {"pending_file": str(PENDING), "pending": _load_pending()}

def process_pending(wait=False, interval=3):
    """Execute the durable queue. Completed entries are exported then removed."""
    items, remaining, processed = _load_pending(), [], []
    for item in items:
        result = request("GET", f"/v2/transcript/{item['transcript_id']}", base_url=base(item["region"]))
        while wait and result.get("status") not in ("completed", "error"):
            print(f"aai: pending export {item['transcript_id']} is {result.get('status')}; polling every {interval:g}s", file=sys.stderr)
            time.sleep(interval)
            result = request("GET", f"/v2/transcript/{item['transcript_id']}", base_url=base(item["region"]))
        if result.get("status") == "completed":
            processed.append({"transcript_id": item["transcript_id"], "exports": save_exports(result, item["source"], item["exports"], item.get("out_dir"), item["region"])})
        elif result.get("status") == "error": processed.append({"transcript_id": item["transcript_id"], "error": result.get("error", "transcription failed")})
        else: remaining.append({**item, "status": result.get("status")})
    if wait or processed: _save_pending([{k:v for k,v in item.items() if k != "status"} for item in remaining])
    return {"pending_file": str(PENDING), "pending": remaining, "processed": processed}

def save_exports(result, source, kinds, output_dir, region):
    """Write post-completion exports next to local input, or to --out-dir."""
    if not kinds or result.get("status") != "completed": return {}
    directory = Path(output_dir).expanduser() if output_dir else (Path(source).expanduser().parent if not source.startswith(("http://", "https://")) else Path.cwd())
    directory.mkdir(parents=True, exist_ok=True)
    stem = Path(source).stem if not source.startswith(("http://", "https://")) else result["id"]
    written = {}
    for kind in kinds:
        path = directory / f"{stem}.{ 'txt' if kind == 'text' else kind }"
        if kind == "json": path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        elif kind == "text": path.write_text(result.get("text", "") + "\n")
        else:
            data = request("GET", f"/v2/transcript/{result['id']}/{kind}", base_url=base(region), binary=kind in ("srt", "vtt"))
            if isinstance(data, bytes): path.write_bytes(data)
            else: path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        written[kind] = str(path)
    return written
