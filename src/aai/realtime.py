import json, os, sys, threading, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from .core import api_key, body, fail

def connect():
    try:
        from websockets.sync.client import connect as ws_connect
        return ws_connect
    except ImportError: fail("WebSocket commands need: python3 -m pip install --user 'websockets>=12'")

def token(args):
    host = {"global":"streaming.assemblyai.com", "us":"streaming.us.assemblyai.com", "eu":"streaming.eu.assemblyai.com"}[args.region]
    query = {"expires_in_seconds": args.expires}
    if args.max_session: query["max_session_duration_seconds"] = args.max_session
    req = Request(f"https://{host}/v3/token?{urlencode(query)}", headers={"authorization": api_key()})
    try:
        with urlopen(req) as res: return json.loads(res.read())
    except HTTPError as exc: fail(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}")

TERMINATE = '{"type":"Terminate"}'

def _send_audio(socket, path, chunk_bytes, chunk_seconds):
    """Send PCM at real-time pace; the API returns inconsistent turns when audio arrives faster."""
    try:
        with open(path, "rb") as audio:
            while chunk := audio.read(chunk_bytes):
                socket.send(chunk); time.sleep(chunk_seconds)
        socket.send(TERMINATE)
    except Exception: pass  # the receive loop reports a closed socket

def stream(args):
    if not 50 <= args.chunk_ms <= 1000: fail("--chunk-ms must be between 50 and 1000", 12, False, "Streaming v3 accepts 50–1000 ms of audio per message.")
    host = {"global":"streaming.assemblyai.com", "us":"streaming.us.assemblyai.com", "eu":"streaming.eu.assemblyai.com"}[args.region]
    query = {"sample_rate": args.sample_rate, "speech_model": args.speech_model, "encoding": args.encoding}
    query.update(dict(item.split("=", 1) for item in args.set))
    bytes_per_sample = 1 if args.encoding == "pcm_mulaw" else 2
    with connect()(f"wss://{host}/v3/ws?{urlencode(query, doseq=True)}", additional_headers={"authorization": api_key()}) as socket:
        if args.audio:
            chunk_bytes = max(1, args.sample_rate * bytes_per_sample * args.chunk_ms // 1000)
            threading.Thread(target=_send_audio, args=(socket, args.audio, chunk_bytes, args.chunk_ms / 1000), daemon=True).start()
        try:
            for message in socket:
                print(message, flush=True)
                if '"Termination"' in message: break
        except KeyboardInterrupt:
            # Ask the server to close cleanly so it flushes the final turn.
            socket.send(TERMINATE)
            for message in socket:
                print(message, flush=True)
                if '"Termination"' in message: break

def generic_ws(args):
    suffix = (("&" if "?" in args.url else "?") + urlencode(dict(item.split("=", 1) for item in args.query))) if args.query else ""
    with connect()(args.url + suffix, additional_headers={"authorization": api_key()}) as socket:
        if args.stdin_json:
            for line in sys.stdin:
                if line.strip(): socket.send(line.strip())
        for message in socket: print(message)
