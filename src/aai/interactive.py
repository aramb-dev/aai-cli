"""Deliberately small terminal workflow for the common 'transcribe this file' case."""
import json, sys
from pathlib import Path
from .core import base, fail, request

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
