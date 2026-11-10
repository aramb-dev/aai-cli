"""Offline tests: nothing here calls the AssemblyAI API."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from aai import __version__, batteries, core, sync  # noqa: E402


def aai(*args, env=None):
    return subprocess.run([sys.executable, "-m", "aai.main", *args], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(SRC), **(env or {})})


class Body(unittest.TestCase):
    def test_set_parses_json_and_falls_back_to_string(self):
        args = SimpleNamespace(params=None, set=["speaker_labels=true", "language_code=ar", 'keyterms_prompt=["a","b"]', "speaker_options.min_speakers_expected=2", "prompt=Names: Ada, Linus"])
        self.assertEqual(core.body(args), {"speaker_labels": True, "language_code": "ar", "keyterms_prompt": ["a", "b"], "speaker_options": {"min_speakers_expected": 2}, "prompt": "Names: Ada, Linus"})


class Cache(unittest.TestCase):
    def test_key_ignores_audio_url_and_key_order(self):
        self.assertEqual(batteries.key_for("abc", {"a": 1, "b": 2, "audio_url": "x"}), batteries.key_for("abc", {"b": 2, "a": 1}))
        self.assertNotEqual(batteries.key_for("abc", {"a": 1}), batteries.key_for("abd", {"a": 1}))


class Usage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.saved = batteries.DATA_HOME, batteries.DB, batteries.CONFIG
        batteries.DATA_HOME, batteries.DB, batteries.CONFIG = root, root / "usage.sqlite3", root / "config.json"
        batteries.CONFIG.write_text(json.dumps({"estimated_usd_per_audio_hour": 1.0}))

    def tearDown(self):
        batteries.DATA_HOME, batteries.DB, batteries.CONFIG = self.saved
        self.tmp.cleanup()

    def test_cache_hits_are_not_billed(self):
        batteries.record("a.mp3", "h", {"id": "1", "status": "completed"}, 3600, False, {})
        batteries.record("a.mp3", "h", {"id": "1", "status": "completed"}, 3600, True, {})
        report = batteries.usage(SimpleNamespace(month=None))
        self.assertEqual(report["transcriptions"], 2)
        self.assertEqual(report["audio_seconds"], 3600)
        self.assertEqual(report["cached_audio_seconds"], 3600)
        self.assertEqual(report["estimated_usd"], 1.0)
        self.assertEqual(report["cache_hits"], 1)

    def test_cache_only_month_costs_zero(self):
        batteries.record("a.mp3", "h", {"id": "1", "status": "completed"}, 3600, True, {})
        self.assertEqual(batteries.usage(SimpleNamespace(month=None))["estimated_usd"], 0.0)


class Sync(unittest.TestCase):
    def test_hosts_use_v1_transcribe_regions(self):
        self.assertEqual(sync.HOSTS, {"global": "sync.assemblyai.com", "us": "sync.us.assemblyai.com", "eu": "sync.eu.assemblyai.com"})
        self.assertEqual(sync.CONTENT_TYPES[".m4a"], "audio/mp4")


class Cli(unittest.TestCase):
    def test_version(self):
        result = aai("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), f"aai {__version__}")

    def test_every_command_has_help(self):
        commands = ["transcribe", "submit", "upload", "get", "delete", "list", "export", "exports", "search", "sync", "token", "chat", "request", "stream", "ws", "batch", "usage", "doctor", "pricing", "schema"]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(aai(command, "--help").returncode, 0)

    def test_stream_rejects_out_of_range_chunks(self):
        result = aai("--json-errors", "stream", "--sample-rate", "16000", "--chunk-ms", "20", env={"ASSEMBLYAI_API_KEY": "test"})
        self.assertEqual(result.returncode, 12)
        self.assertIn("--chunk-ms", json.loads(result.stderr)["error"])

    def test_stream_rejects_missing_audio_before_connecting(self):
        result = aai("--json-errors", "stream", "--sample-rate", "16000", "--audio", "/nonexistent/audio.pcm", env={"ASSEMBLYAI_API_KEY": "test"})
        self.assertEqual(result.returncode, 12)
        self.assertIn("cannot read --audio", json.loads(result.stderr)["error"])

    def test_dry_run_makes_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "clip.wav"; audio.write_bytes(b"RIFF")
            result = aai("transcribe", str(audio), "--dry-run", "--set", "language_code=ar", env={"ASSEMBLYAI_API_KEY": "", "XDG_CONFIG_HOME": tmp})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["request"], {"language_code": "ar"})


if __name__ == "__main__":
    unittest.main()
