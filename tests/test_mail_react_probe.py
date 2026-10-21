"""scripts/mail_react_probe.py: probe row shape on a temp bus, read/reply detection, timeout, platform, args."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tests._load import ROOT

_spec = importlib.util.spec_from_file_location("mail_react_probe", os.path.join(ROOT, "scripts", "mail_react_probe.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

S = 10 ** 9
T0 = 1_700_000_000 * S       # fixed probe time: no wall clock in the detection paths


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


class MailReactProbeTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mail-probe-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.bus = os.path.join(self.d, "bus.jsonl")
        self.probe = P.make_probe("tgt-codex", "probe-sender", "n0nce12345", T0)

    def rows(self):
        with open(self.bus, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def add(self, rec):
        with open(self.bus, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def cursor(self, t, mtime):
        p = os.path.join(self.d, "read-tgt-codex.cursor")
        with open(p, "w", encoding="utf-8") as f:
            f.write(str(t))
        os.utime(p, (mtime, mtime))

    def test_send_writes_one_server_shaped_row(self):
        P.send(self.d, self.probe)
        rs = self.rows()
        self.assertEqual(len(rs), 1)
        self.assertEqual(set(rs[0]), {"id", "t", "from", "idSrc", "to", "room", "subject", "thread", "body"})
        self.assertEqual((rs[0]["to"], rs[0]["room"], rs[0]["subject"]), ("tgt-codex", None, "[probe] n0nce12345"))
        self.assertIn("PONG n0nce12345", rs[0]["body"])
        if os.name != "nt":   # ⚠Windows st_mode only reflects the read-only bit (0o666/0o444)
            self.assertEqual(os.stat(self.bus).st_mode & 0o777, 0o600)

    def test_probe_alone_is_not_a_reply_or_read(self):
        P.send(self.d, self.probe)
        self.cursor(T0 - 1, T0 / S)
        self.assertIsNone(P.reply_t(self.d, self.probe, "n0nce12345"))
        self.assertIsNone(P.read_at(self.d, "tgt-codex", T0))

    def test_read_and_reply_times(self):
        P.send(self.d, self.probe)
        self.add({"id": "x1", "t": T0 + 5 * S, "from": "other", "to": "tgt-codex", "body": "unrelated"})
        self.add({"id": "r1", "t": T0 + 42 * S, "from": "tgt-codex", "to": "probe-sender", "body": "PONG n0nce12345"})
        self.cursor(T0 + 42 * S, T0 / S + 40)
        clk = FakeClock(T0 / S)
        res = P.watch(self.d, self.probe, "n0nce12345", 600, clock=clk, sleep=clk.sleep)
        self.assertAlmostEqual(res["read_s"], 40.0, places=3)
        self.assertAlmostEqual(res["reply_s"], 42.0, places=3)
        out = P.line("tgt-codex", "codex", self.probe, res)
        self.assertRegex(out, r"^target=tgt-codex platform=codex sent_at=\S+ read_after_s=40.0 reply_after_s=42.0$")

    def test_reply_without_cursor_counts_as_read(self):
        P.send(self.d, self.probe)
        self.add({"id": "r1", "t": T0 + 7 * S, "from": "tgt-codex", "to": "probe-sender", "body": "PONG n0nce12345"})
        clk = FakeClock(T0 / S)
        res = P.watch(self.d, self.probe, "n0nce12345", 600, clock=clk, sleep=clk.sleep)
        self.assertEqual((round(res["read_s"], 3), round(res["reply_s"], 3)), (7.0, 7.0))

    def test_timeout(self):
        P.send(self.d, self.probe)
        self.add({"id": "s1", "t": T0 + S, "from": "probe-sender", "to": "tgt-codex", "body": "n0nce12345 echo"})
        clk = FakeClock(T0 / S)
        res = P.watch(self.d, self.probe, "n0nce12345", 30, poll=5, clock=clk, sleep=clk.sleep)
        self.assertEqual(res, {"read_s": None, "reply_s": None})
        self.assertGreaterEqual(clk.now - T0 / S, 30)
        self.assertIn("read_after_s=TIMEOUT reply_after_s=TIMEOUT", P.line("tgt-codex", "codex", self.probe, res))

    def test_read_only_then_timeout(self):
        P.send(self.d, self.probe)
        self.cursor(T0, T0 / S + 3)
        clk = FakeClock(T0 / S)
        res = P.watch(self.d, self.probe, "n0nce12345", 10, clock=clk, sleep=clk.sleep)
        self.assertEqual((round(res["read_s"], 3), res["reply_s"]), (3.0, None))

    def test_platform(self):
        with open(os.path.join(self.d, "identity.json"), "w", encoding="utf-8") as f:
            json.dump({"/x/a": "probe-cc", "codex:/x/b": "b-codex", "gemini:/x/c": "named"}, f)
        self.assertEqual(P.platform_of(self.d, "probe-cc"), "claude")
        self.assertEqual(P.platform_of(self.d, "b-codex"), "codex")
        self.assertEqual(P.platform_of(self.d, "named"), "gemini")
        self.assertEqual(P.platform_of(self.d, "z-codex"), "codex")
        self.assertEqual(P.platform_of(self.d, "nobody"), "unknown")

    def test_dry_run_writes_nothing_and_sender_must_be_throwaway(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(P.main(["--to", "tgt-codex", "--dry-run"], store=self.d), 0)
        self.assertIn("nothing written", out.getvalue())
        self.assertFalse(os.path.exists(self.bus))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(P.main(["--to", "tgt-codex", "--from", "Sidereus", "--dry-run"], store=self.d), 2)


if __name__ == "__main__":
    unittest.main()
