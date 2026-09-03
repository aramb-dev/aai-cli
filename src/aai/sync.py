import json, os, sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from .core import api_key, body, fail

def transcribe(args):
    if args.file == "-": name, audio = "stdin", sys.stdin.buffer.read()
    else:
        path = Path(args.file).expanduser()
        if not path.is_file(): fail(f"not a file: {path}")
        name, audio = path.name, path.read_bytes()
    boundary = "----aai" + os.urandom(12).hex(); config = body(args)
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{name}"\r\nContent-Type: {args.content_type}\r\n\r\n'.encode(), audio, b"\r\n"]
    if config: parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="config"\r\nContent-Type: application/json\r\n\r\n'.encode(), json.dumps(config).encode(), b"\r\n"]
    parts.append(f"--{boundary}--\r\n".encode())
    req = Request("https://sync.assemblyai.com/transcribe", data=b"".join(parts), method="POST", headers={"authorization": api_key(), "X-AAI-Model": args.model, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(req, timeout=120) as response: return json.loads(response.read())
    except HTTPError as exc: fail(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}")
