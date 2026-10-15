"""History rows carry `acct` only for a non-primary Claude account (picker filter key); primary and external CLI
rows have no key, so the default output is unchanged. A subagent-only row takes its parent session's account."""
import time
import types
import unittest

from tests._load import sidereus

hi = sidereus("history")

KEYS = {"date", "sid", "id", "slug", "cwd", "project", "plat", "model", "models", "from", "to", "hours",
        "tok", "cost", "sub", "title", "branch", "runFrom", "runTo"}


def _at(y, mo, d, h):
    return int(time.mktime((y, mo, d, h, 0, 0, 0, 0, -1)))


def _h(*hours):
    return {str(k): {"claude-opus-5": [1, 1, 0, 0]} for k in hours}


class _Gm:
    KEY, NAME = "gm", "Gemini"

    def __init__(self, ts):
        self.ts = ts

    def scan(self, since):
        return [{"sid": "g1", "cwd": "/w/x", "project": "x", "msgs": {"m": (1, 1, 0, 0, self.ts, "gemini", 0.1)}}]


class HistAcct(unittest.TestCase):
    def setUp(self):
        self.now = _at(2026, 9, 21, 12)
        t = _at(2026, 9, 21, 9)
        files = {
            "/p/-x/prim.jsonl": {"sl": "-x", "h": _h(t)},
            "/p/-x/work.jsonl": {"sl": "-x", "h": _h(t)},
            "/p/-x/par/subagents/agent-a.jsonl": {"sl": "-x", "h": _h(t)},   # parent transcript not in the index
        }
        self.calls = []
        self.who = {"work": "work", "par": "work"}
        self.saved = {k: getattr(hi, k) for k in ("_uidx", "_uidx_refresh", "time", "PLAT_MODS", "_cwd_from_slug")}
        self.saved_acct = hi.claude_roots.acct_of
        hi._uidx = {"files": files}
        hi._uidx_refresh = lambda: None
        hi.time = types.SimpleNamespace(time=lambda: self.now, mktime=time.mktime, strptime=time.strptime)
        hi.PLAT_MODS = {"gemini": _Gm(t)}
        hi._cwd_from_slug = lambda s: "/w/x"

        def acct_of(sid, fp):
            self.calls.append((sid, fp))
            a = self.who.get(sid, "")
            return (a, "/acct/" + a) if a else ("", "")
        hi.claude_roots.acct_of = acct_of
        hi._hist_cache.clear()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(hi, k, v)
        hi.claude_roots.acct_of = self.saved_acct
        hi._hist_cache.clear()

    def _rows(self):
        out = hi.history(7)
        d = next(x for x in out["list"] if x["date"] == "2026-09-21")
        return {r["sid"]: r for r in d["rows"]}, d

    def test_non_primary_only(self):
        rows, d = self._rows()
        self.assertEqual(rows["work"]["acct"], "work")
        self.assertNotIn("acct", rows["prim"])
        self.assertNotIn("acct", d["gm"]["rows"][0])

    def test_subagent_only_row_takes_parent(self):
        rows, _d = self._rows()
        self.assertEqual(rows["par"]["acct"], "work")
        self.assertIn(("par", "/p/-x/par/subagents/agent-a.jsonl"), self.calls)

    def test_default_output_unchanged(self):
        self.who = {}
        rows, _d = self._rows()
        for r in rows.values():
            self.assertEqual(set(r), KEYS)


if __name__ == "__main__":
    unittest.main()
