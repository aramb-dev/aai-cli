"""Local, reusable batteries: media inspection, cache, ledger, batch and diagnostics."""
import hashlib, json, os, shutil, sqlite3, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from .core import api_key, body, fail, request
from . import prerecorded

# XDG locations keep user data out of the installed package and out of source control.
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "aai"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "aai"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "aai" / "config.json"
DB = DATA_HOME / "usage.sqlite3"
MEDIA_EXTS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac", ".aac", ".aiff", ".mov"}

def config():
    if not CONFIG.exists(): return {"estimated_usd_per_audio_hour": None}
    try: return json.loads(CONFIG.read_text())
    except json.JSONDecodeError: fail(f"invalid JSON: {CONFIG}")

def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()

def duration(path):
    """Best effort only; returns seconds or None, never sends media to a service."""
    if shutil.which("ffprobe"):
        run = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True)
        try: return float(run.stdout.strip())
        except ValueError: pass
    if sys.platform == "darwin" and shutil.which("afinfo"):
        run = subprocess.run(["afinfo", str(path)], capture_output=True, text=True)
        import re
        match = re.search(r"estimated duration: ([0-9.]+)", run.stdout)
        if match: return float(match.group(1))
    return None

def key_for(path, request_body):
    normalized = dict(request_body); normalized.pop("audio_url", None)
    return hashlib.sha256((file_hash(path) + json.dumps(normalized, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()

def cache_get(key):
    path = CACHE / f"{key}.json"
    return json.loads(path.read_text()) if path.exists() else None

def cache_put(key, result):
    CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
    (CACHE / f"{key}.json").write_text(json.dumps(result, indent=2))

def db():
    DATA_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS transcriptions (at TEXT, source TEXT, sha256 TEXT, transcript_id TEXT, seconds REAL, estimated_usd REAL, status TEXT, cache_hit INTEGER, config_json TEXT)")
    return conn

def record(source, digest, result, seconds, cache_hit, request_body):
    rate = config().get("estimated_usd_per_audio_hour")
    cost = seconds / 3600 * rate if seconds is not None and isinstance(rate, (int, float)) else None
    with db() as conn: conn.execute("INSERT INTO transcriptions VALUES (?,?,?,?,?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), str(source), digest, result.get("id"), seconds, cost, result.get("status"), int(cache_hit), json.dumps(request_body, sort_keys=True)))
    return cost

def preview(path, request_body):
    seconds = duration(path); rate = config().get("estimated_usd_per_audio_hour")
    return {"source": str(path), "seconds": seconds, "minutes": round(seconds / 60, 3) if seconds is not None else None, "estimated_usd": round(seconds / 3600 * rate, 4) if seconds is not None and isinstance(rate, (int, float)) else None, "pricing_note": None if isinstance(rate, (int, float)) else f"Set estimated_usd_per_audio_hour in {CONFIG} to enable estimates.", "request": request_body}

def one(path, request_body, region="global", wait=True, cache=True, dry_run=False, progress=True):
    path = Path(path).expanduser()
    if not path.is_file(): fail(f"not a file: {path}")
    info = preview(path, request_body)
    if dry_run: return {"action": "dry_run", **info}
    cache_key = key_for(path, request_body)
    hit = cache_get(cache_key) if cache else None
    if hit:
        hit = {**hit, "_aai": {"cache_hit": True, "cache_key": cache_key}}
        record(path, file_hash(path), hit, info["seconds"], True, request_body)
        return hit
    if progress: print(f"aai: submitting {path.name}", file=sys.stderr)
    args = SimpleNamespace(source=str(path), region=region, params=json.dumps(request_body), set=[], wait=wait, interval=3)
    result = prerecorded.submit(args)
    result["_aai"] = {"cache_hit": False, "cache_key": cache_key}
    if result.get("status") == "completed": cache_put(cache_key, result)
    record(path, file_hash(path), result, info["seconds"], False, request_body)
    return result

def batch(args):
    root = Path(args.directory).expanduser()
    if not root.is_dir(): fail(f"not a directory: {root}")
    request_body = body(args); paths = sorted(p for p in root.glob(args.glob) if p.is_file() and p.suffix.lower() in MEDIA_EXTS)
    results = []
    for index, path in enumerate(paths, 1):
        print(f"aai: [{index}/{len(paths)}] {path.name}", file=sys.stderr)
        try: results.append(one(path, request_body, args.region, args.wait, args.cache, args.dry_run, False))
        except SystemExit as exc: results.append({"source": str(path), "ok": False, "exit_code": exc.code})
    return {"directory": str(root), "glob": args.glob, "count": len(paths), "completed": sum(1 for item in results if item.get("status") == "completed"), "failed": sum(1 for item in results if item.get("ok") is False or item.get("status") == "error"), "results": results}

def usage(args):
    clause, params = ("", []) if not args.month else (" WHERE at LIKE ?", [args.month + "%"])
    with db() as conn:
        count, seconds, cost, hits = conn.execute("SELECT count(*), coalesce(sum(seconds),0), sum(estimated_usd), coalesce(sum(cache_hit),0) FROM transcriptions" + clause, params).fetchone()
    return {"month": args.month, "transcriptions": count, "audio_seconds": seconds, "audio_minutes": round(seconds / 60, 2), "estimated_usd": round(cost, 4) if cost is not None else None, "cache_hits": hits, "ledger": str(DB), "pricing_note": None if cost is not None else f"Set estimated_usd_per_audio_hour in {CONFIG} to calculate spend."}

def doctor():
    result = request("GET", "/v2/transcript", query={"limit": 1})
    return {"ok": True, "api_key": "valid", "cache": str(CACHE), "ledger": str(DB), "pricing_config": str(CONFIG), "api_response": {"result_count": result.get("page_details", {}).get("result_count")}}

def setup_price(args):
    CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"estimated_usd_per_audio_hour": args.usd_per_audio_hour}, indent=2) + "\n"); os.chmod(CONFIG, 0o600)
    return {"ok": True, "config": str(CONFIG), "estimated_usd_per_audio_hour": args.usd_per_audio_hour, "note": "This is your local estimate, not an AssemblyAI quote."}
