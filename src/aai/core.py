import json, os, sys, time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.assemblyai.com"

def fail(message, exit_code=15, retryable=False, next_step="Inspect the error and command arguments, then retry only if appropriate."):
    """Exit with deterministic codes and an agent-parseable diagnostic when piped."""
    report = {"ok": False, "error": str(message), "exit_code": exit_code, "retryable": retryable, "next_step": next_step}
    if os.environ.get("AAI_JSON_ERRORS") == "1" or not sys.stderr.isatty():
        print(json.dumps(report, separators=(",", ":")), file=sys.stderr)
    else:
        print(f"aai: {message}\nnext: {next_step} (exit {exit_code})", file=sys.stderr)
    raise SystemExit(exit_code)

def api_key():
    value = os.environ.get("ASSEMBLYAI_API_KEY")
    if not value: fail("ASSEMBLYAI_API_KEY is not set", 10, False, "Set the key, then run `aai doctor`.")
    return value

def json_arg(value):
    if value == "-": return json.load(sys.stdin)
    return json.loads(Path(value[1:]).read_text()) if value.startswith("@") else json.loads(value)

def body(args):
    result = json_arg(args.params) if getattr(args, "params", None) else {}
    if not isinstance(result, dict): fail("--params must contain a JSON object", 12, False, "Pass an object, not a JSON array or scalar.")
    for item in getattr(args, "set", []) or []:
        if "=" not in item: fail(f"--set requires KEY=JSON_VALUE: {item}", 12, False, "Pass JSON values such as key=true or key='[\"value\"]'.")
        key, value = item.split("=", 1); target = result
        for part in key.split(".")[:-1]: target = target.setdefault(part, {})
        try: target[key.split(".")[-1]] = json.loads(value)
        except json.JSONDecodeError: target[key.split(".")[-1]] = value
    return result

def base(region): return "https://api.eu.assemblyai.com" if region == "eu" else API

def request(method, path, data=None, query=None, base_url=API, binary=False):
    url = base_url + path + (("?" if "?" not in path else "&") + urlencode(query, doseq=True) if query else "")
    encoded = data if isinstance(data, bytes) else (json.dumps(data).encode() if data is not None else None)
    headers = {"authorization": api_key()}
    if data is not None and not isinstance(data, bytes): headers["content-type"] = "application/json"
    # Retrying an ambiguous POST risks duplicate billable work; only safe reads retry.
    attempts = 5 if method.upper() == "GET" else 1
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, data=encoded, headers=headers, method=method), timeout=120) as response:
                result = response.read(); break
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt == attempts - 1:
                detail = exc.read().decode(errors="replace")
                if exc.code in (401, 403): code, hint = 10, "Run `aai doctor`; set or rotate ASSEMBLYAI_API_KEY."
                elif exc.code == 404: code, hint = 11, "Verify the ID, endpoint path, and region."
                elif exc.code in (400, 409, 422): code, hint = 12, "Correct the request/body combination using `aai COMMAND --help`."
                elif exc.code == 429: code, hint = 13, "Wait before retrying; reduce batch rate if it persists."
                else: code, hint = 15, "Inspect the API error; do not blindly retry a write request."
                fail(f"HTTP {exc.code}: {detail}", code, retryable, hint)
            delay = min(30, 2 ** attempt)
            try: delay = max(delay, float(exc.headers.get("Retry-After", 0)))
            except ValueError: pass
            print(f"aai: GET HTTP {exc.code}; retrying in {delay:g}s ({attempt + 1}/{attempts - 1})", file=sys.stderr); time.sleep(delay)
        except URLError as exc:
            if attempt == attempts - 1: fail(str(exc.reason), 14, True, "Check network/DNS, then retry this safe read request.")
            delay = min(30, 2 ** attempt)
            print(f"aai: network error; retrying in {delay:g}s ({attempt + 1}/{attempts - 1})", file=sys.stderr); time.sleep(delay)
    if binary: return result
    try: return json.loads(result)
    except json.JSONDecodeError: return result.decode(errors="replace")

def _table(rows):
    if not rows: return "(none)"
    headers = list(dict.fromkeys(key for row in rows for key in row))
    cells = [[str(row.get(key, "")).replace("\n", " ") for key in headers] for row in rows]
    widths = [max(len(key), *(len(row[i]) for row in cells)) for i, key in enumerate(headers)]
    heading = " | ".join(key.ljust(widths[i]) for i, key in enumerate(headers))
    divider = "-+-".join("-" * width for width in widths)
    return heading + "\n" + divider + "\n" + "\n".join(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in cells)

def emit(value, compact=False, output=None, json_mode=False):
    """TTY => readable tables; non-TTY/--json => one clean JSON object."""
    machine = json_mode or compact or not sys.stdout.isatty() or bool(output)
    if machine:
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if compact or not sys.stdout.isatty() else json.dumps(value, indent=2, ensure_ascii=False)
    elif isinstance(value, list) and all(isinstance(item, dict) for item in value): rendered = _table(value)
    elif isinstance(value, dict):
        simple = {k:v for k,v in value.items() if k not in ("text", "words", "utterances", "results") and not isinstance(v, (dict, list))}
        rendered = _table([{"field": k, "value": v} for k, v in simple.items()])
        if value.get("text"): rendered += "\n\nTranscript\n----------\n" + value["text"]
        if isinstance(value.get("results"), list): rendered += "\n\nResults\n-------\n" + _table([{k:v for k,v in item.items() if not isinstance(v, (dict, list))} for item in value["results"]])
    else: rendered = str(value)
    if output: Path(output).write_text(rendered + "\n")
    else: print(rendered)
