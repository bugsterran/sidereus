"""Gemini chat-file token sums: dedupe by message id, incremental tail, and isolation from Claude usage."""
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone

from tests._load import sidereus

ext = sidereus("ext")
usage = sidereus("usage")
burn = sidereus("burn")
gm = sidereus("plat_gemini")


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _msg(mid, t, inp, out, cached=0, thoughts=0, tool=0, model="gemini-2.5-pro"):
    return {"id": mid, "timestamp": _iso(t), "type": "gemini", "content": "SECRET body text", "model": model,
            "tokens": {"input": inp, "output": out, "cached": cached, "thoughts": thoughts, "tool": tool,
                       "total": inp + out + thoughts + tool}}


class ExtTok(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.dir = os.path.join(self.home, ".gemini", "tmp", "proj", "chats")
        os.makedirs(self.dir)
        self.path = os.path.join(self.dir, "session-1-abc.jsonl")
        self._home, gm._real_home = gm._real_home, (lambda: self.home)
        self._tok = dict(ext._tok)
        ext._tok.clear()
        gm._tail.clear()
        self.now = time.time()

    def tearDown(self):
        gm._real_home = self._home
        gm._tail.clear()
        ext._tok.clear()
        ext._tok.update(self._tok)
        shutil.rmtree(self.home, ignore_errors=True)

    def write(self, *objs, mode="a", raw=""):
        with open(self.path, mode, encoding="utf-8") as f:
            for o in objs:
                f.write(json.dumps(o) + "\n")
            f.write(raw)

    def header(self):
        self.write({"sessionId": "abc", "projectHash": "h", "startTime": _iso(self.now),
                    "lastUpdated": _iso(self.now), "kind": "main"}, mode="w")

    def test_header_only(self):
        self.header()
        ext.ext_tok_refresh("gemini", "abc", self.path)
        self.assertIsNone(ext.ext_tok("gemini", "abc"))
        self.assertEqual(ext.ext_usage_today(), {})

    def test_set_rewrite_dedupes_by_id(self):
        self.header()
        self.write({"id": "u1", "type": "user", "content": "SECRET prompt"},
                   _msg("g1", self.now, 1000, 50, cached=600, thoughts=20))
        # `$set` rewrites the list: g1 again (now final) plus g2 — g1 must count once, with its latest tokens
        self.write({"$set": {"messages": [_msg("g1", self.now, 1200, 80, cached=700, thoughts=30),
                                          _msg("g2", self.now, 300, 10, tool=5, model="gemini-2.5-flash")]}})
        ext.ext_tok_refresh("gemini", "abc", self.path)
        s = ext.ext_tok("gemini", "abc")
        self.assertEqual((s["in"], s["cache"], s["out"], s["thought"]), (500 + 305, 700, 90, 30))
        self.assertEqual(s["tok"], 1200 + 80 + 30 + 300 + 10 + 5)     # == sum of Gemini `total`
        self.assertEqual(s["model"], "gemini-2.5-flash")
        self.assertEqual(ext.ext_usage_today()["gm"]["n_sessions"], 1)
        self.assertNotIn("SECRET", repr(ext._tok))

    def test_growing_file_and_partial_line(self):
        self.header()
        self.write(_msg("g1", self.now, 100, 10))
        ext.ext_tok_refresh("gemini", "abc", self.path)
        self.assertEqual(ext.ext_tok("gemini", "abc")["tok"], 110)
        line = json.dumps(_msg("g2", self.now, 200, 20))
        self.write(raw=line[:30])                                     # half-written line: not counted yet
        ext.ext_tok_refresh("gemini", "abc", self.path)
        self.assertEqual(ext.ext_tok("gemini", "abc")["tok"], 110)
        self.write(raw=line[30:] + "\n")
        ext.ext_tok_refresh("gemini", "abc", self.path)
        self.assertEqual(ext.ext_tok("gemini", "abc")["tok"], 330)
        self.header()                                                 # truncated/rewritten → restart
        ext.ext_tok_refresh("gemini", "abc", self.path)
        self.assertIsNone(ext.ext_tok("gemini", "abc"))

    def test_path_outside_gemini_is_ignored(self):
        other = os.path.join(self.home, "elsewhere.jsonl")
        with open(other, "w", encoding="utf-8") as f:
            f.write(json.dumps(_msg("g1", self.now, 100, 10)) + "\n")
        ext.ext_tok_refresh("gemini", "abc", other)
        ext.ext_tok_refresh("codex", "abc", self.path)
        self.assertEqual(ext._tok, {})

    def test_old_messages_not_in_today(self):
        self.header()
        self.write(_msg("g1", self.now - 3 * 86400, 100, 10), _msg("g2", self.now, 5, 1))
        ext.ext_tok_refresh("gemini", "abc", self.path)
        self.assertEqual(ext.ext_tok("gemini", "abc")["tok"], 116)
        self.assertEqual(ext.ext_usage_today()["gm"]["tok"], 6)

    def test_claude_usage_untouched(self):
        calls = []
        saved = usage._usage_add, burn.quota_burn
        usage._usage_add = lambda *a, **k: calls.append(("usage", a))
        burn.quota_burn = lambda *a, **k: calls.append(("burn", a))
        try:
            before = json.dumps(usage._usage, sort_keys=True, default=str)
            self.header()
            self.write(_msg("g1", self.now, 10 ** 6, 10 ** 5))
            ext.ext_tok_refresh("gemini", "abc", self.path)
            ext.ext_usage_today()
            ext.ext_tok("gemini", "abc")
            self.assertEqual(calls, [])
            self.assertEqual(json.dumps(usage._usage, sort_keys=True, default=str), before)
        finally:
            usage._usage_add, burn.quota_burn = saved
        src = "".join(open(m.__file__, encoding="utf-8").read() for m in (ext, sidereus("ext_store")))
        for mod in ("sidereus.usage", "sidereus.burn", "sidereus.quota"):
            self.assertNotIn(mod, src)

    # ── cost estimate ──
    def cost(self, *msgs):
        self.header()
        self.write(*msgs)
        ext.ext_tok_refresh("gemini", "abc", self.path)
        return ext.ext_tok("gemini", "abc")["cost"]

    def test_cost_cached_split_and_thoughts_as_output(self):
        # 2.5-pro ≤200k: `input` 100k includes 60k cached → 40k·1.25 + 60k·0.125 + (5k out + 2k thoughts)·10, per 1M
        c = self.cost(_msg("g1", self.now, 100_000, 5_000, cached=60_000, thoughts=2_000))
        self.assertAlmostEqual(c, (40_000 * 1.25 + 60_000 * 0.125 + 7_000 * 10.0) / 1e6)

    def test_cost_tier_per_request_at_200k(self):
        small = _msg("g1", self.now, 200_000, 1_000)                  # exactly 200k → base tier
        big = _msg("g2", self.now, 200_001, 1_000)                    # over → long tier
        c = self.cost(small, big)
        self.assertAlmostEqual(c, (200_000 * 1.25 + 1_000 * 10.0) / 1e6 + (200_001 * 2.50 + 1_000 * 15.0) / 1e6)
        # Summed tokens (400k) must not push the small request into the long tier
        self.assertLess(c, (400_001 * 2.50 + 2_000 * 15.0) / 1e6)

    def test_cost_unknown_model_is_none(self):
        self.assertIsNone(self.cost(_msg("g1", self.now, 100, 10, model="gemini-9-imaginary")))
        self.assertIsNone(gm.cost("", 1, 1, 1, 1))
        self.assertEqual(ext.ext_usage_today()["gm"]["cost"], None)
        self.assertEqual(ext.ext_usage_today()["gm"]["costMiss"], 1)

    def test_cost_recomputed_on_price_change(self):
        c = self.cost(_msg("g1", self.now, 1_000_000, 0, model="gemini-2.5-flash"))
        self.assertAlmostEqual(c, 0.30)
        saved = gm.PRICE_VER, dict(gm.PRICE)
        try:
            gm.PRICE["gemini-2.5-flash"] = (0.60, 0.06, 5.0)
            gm.PRICE_VER = "test"
            ext.ext_tok_refresh("gemini", "abc", self.path)            # file unchanged, stored tokens repriced
            self.assertAlmostEqual(ext.ext_tok("gemini", "abc")["cost"], 0.60)
        finally:
            gm.PRICE_VER = saved[0]
            gm.PRICE.clear(); gm.PRICE.update(saved[1])

    def test_cost_next_prices_by_request_time(self):
        t = gm.PRICE_NEXT[0]
        self.assertAlmostEqual(gm.cost("gemini-3.8-flash", 10 ** 6, 0, 0, 0, t - 1), 0.75)
        self.assertAlmostEqual(gm.cost("gemini-3.8-flash", 10 ** 6, 0, 0, 0, t), 1.50)
        self.assertAlmostEqual(gm.cost("gemini-2.5-flash", 10 ** 6, 0, 0, 0, t), 0.30)

    def test_cost_not_in_claude_totals(self):
        before = json.dumps(usage._usage, sort_keys=True, default=str)
        self.cost(_msg("g1", self.now, 10 ** 6, 10 ** 5))
        ext.ext_usage_today()
        self.assertEqual(json.dumps(usage._usage, sort_keys=True, default=str), before)
        ext._ext[("gemini", "abc")] = {"lastSeen": self.now, "firstSeen": self.now, "cwd": "/x",
                                       "transcript_path": self.path}
        try:
            row = [r for r in ext.ext_rows() if r["sid"] == "abc"][0]
        finally:
            ext._ext.pop(("gemini", "abc"), None)
        self.assertEqual(row["cost"], 0)                              # Claude's cost key stays 0
        self.assertGreater(row["estCost"], 0)


if __name__ == "__main__":
    unittest.main()
