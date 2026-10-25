import json, os, sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from .core import api_key, body, fail

HOSTS = {"global": "sync.assemblyai.com", "us": "sync.us.assemblyai.com", "eu": "sync.eu.assemblyai.com"}
# Content types the Sync API accepts, keyed by file extension.
CONTENT_TYPES = {".wav": "audio/wav", ".pcm": "audio/pcm", ".raw": "audio/pcm", ".aac": "audio/aac", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac", ".webm": "audio/webm"}
MAX_BYTES = 256 * 1024 * 1024

def transcribe(args):
    if args.file == "-": name, audio = "stdin", sys.stdin.buffer.read()
    else:
        path = Path(args.file).expanduser()
        if not path.is_file(): fail(f"not a file: {path}")
        name, audio = path.name, path.read_bytes()
    if len(audio) > MAX_BYTES: fail(f"Sync API accepts at most 256 MB; {name} is {len(audio) / 1024 / 1024:.0f} MB", 12, False, "Use `aai transcribe` for larger files.")
    content_type = args.content_type or CONTENT_TYPES.get(Path(name).suffix.lower(), "audio/wav")
    boundary = "----aai" + os.urandom(12).hex(); config = body(args)
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode(), audio, b"\r\n"]
    if config: parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="config"\r\nContent-Type: application/json\r\n\r\n'.encode(), json.dumps(config).encode(), b"\r\n"]
    parts.append(f"--{boundary}--\r\n".encode())
    req = Request(f"https://{HOSTS[args.region]}/v1/transcribe", data=b"".join(parts), method="POST", headers={"authorization": api_key(), "X-AAI-Model": args.model, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(req, timeout=120) as response: return json.loads(response.read())
    except HTTPError as exc: fail(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}")
