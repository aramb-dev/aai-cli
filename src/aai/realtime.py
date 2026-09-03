import json, os, sys
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

def stream(args):
    host = {"global":"streaming.assemblyai.com", "us":"streaming.us.assemblyai.com", "eu":"streaming.eu.assemblyai.com"}[args.region]
    query = {"sample_rate": args.sample_rate, "speech_model": args.speech_model, "encoding": args.encoding}
    query.update(dict(item.split("=", 1) for item in args.set))
    with connect()(f"wss://{host}/v3/ws?{urlencode(query, doseq=True)}", additional_headers={"authorization": api_key()}) as socket:
        if args.audio:
            with open(args.audio, "rb") as audio:
                while chunk := audio.read(max(1, args.sample_rate * 2 * args.chunk_ms // 1000)): socket.send(chunk)
            socket.send('{"type":"Terminate"}')
        for message in socket:
            print(message)
            if '"TurnIsFinal"' in message or '"Termination"' in message: break

def generic_ws(args):
    suffix = (("&" if "?" in args.url else "?") + urlencode(dict(item.split("=", 1) for item in args.query))) if args.query else ""
    with connect()(args.url + suffix, additional_headers={"authorization": api_key()}) as socket:
        if args.stdin_json:
            for line in sys.stdin:
                if line.strip(): socket.send(line.strip())
        for message in socket: print(message)
