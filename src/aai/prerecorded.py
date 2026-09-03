import sys, time
from pathlib import Path
from .core import base, body, fail, request

def upload(filename, region):
    if filename == "-": return request("POST", "/v2/upload", sys.stdin.buffer.read(), base_url=base(region))
    path = Path(filename).expanduser()
    if not path.is_file(): fail(f"not a file: {path}")
    return request("POST", "/v2/upload", path.read_bytes(), base_url=base(region))

def submit(args):
    data = body(args)
    data["audio_url"] = args.source if args.source.startswith(("http://", "https://")) else upload(args.source, args.region)["upload_url"]
    result = request("POST", "/v2/transcript", data, base_url=base(args.region))
    if not getattr(args, "wait", False): return result
    while result.get("status") not in ("completed", "error"):
        time.sleep(args.interval)
        result = request("GET", f"/v2/transcript/{result['id']}", base_url=base(args.region))
    return result

def transcript(args):
    if args.command == "get": return request("GET", f"/v2/transcript/{args.id}", base_url=base(args.region))
    if args.command == "delete": return request("DELETE", f"/v2/transcript/{args.id}", base_url=base(args.region))
    if args.command == "list":
        query = {key: value for key, value in (("limit", args.limit), ("status", args.status), ("created_on", args.created_on)) if value is not None}
        return request("GET", "/v2/transcript", query=query, base_url=base(args.region))
    if args.command == "search": return request("GET", f"/v2/transcript/{args.id}/word-search", query={"words": ",".join(args.words)}, base_url=base(args.region))
    binary = args.kind in ("srt", "vtt")
    result = request("GET", f"/v2/transcript/{args.id}/{args.kind}", base_url=base(args.region), binary=binary)
    if binary and args.out: Path(args.out).write_bytes(result); return f"wrote {args.out}"
    return result.decode() if binary else result
