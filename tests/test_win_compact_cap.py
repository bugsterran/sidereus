"""Window learning ignores auto compactions caused by the user's autoCompactWindow (not by the model window)."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from tests._load import sidereus

L = sidereus("live_win")
P = sidereus("prefs")
# Pinned table (the built-in default is empty).
HIST = P.compact_hist({"compact_history": [["2026-09-03", 300_000], ["2026-09-10", 200_000], ["2026-09-22", 450_000]]})


def _ts(y, m, d):
    # transcripts carry UTC; _line_ts adds the local offset back, so write the UTC form of local midnight+noon
    return datetime.fromtimestamp(datetime(y, m, d, 12).timestamp(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _lines(model, day, pre):
    ts = _ts(*day)
    return [{"timestamp": ts, "message": {"model": model}},
            {"timestamp": ts, "type": "system", "subtype": "compact_boundary",
             "compactMetadata": {"trigger": "auto", "preTokens": pre}}]


class CompactCap(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        os.makedirs(os.path.join(self.d, "proj"))
        self.ev, self.seen, self.scanned = {}, {}, {}
        for p in (mock.patch.object(L, "CLAUDE_PROJECTS", self.d),
                  mock.patch.object(L, "COMPACT_HIST", HIST),
                  mock.patch.object(L, "COMPACT_STATE_FILE", os.path.join(self.d, "none.json")),
                  mock.patch.object(L, "_win_save", lambda: None),
                  mock.patch.object(L, "_win_ev", self.ev), mock.patch.object(L, "_win_seen", self.seen),
                  mock.patch.object(L, "_win_scanned", self.scanned)):
            p.start()
            self.addCleanup(p.stop)

    def mk(self, name, rows):
        fp = os.path.join(self.d, "proj", name + ".jsonl")
        with open(fp, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))
        return fp

    def scan(self, now):
        with mock.patch.object(L.time, "time", lambda: now):
            L._scan_windows(days=365)
        return {m: {w: len(s) for w, s in v.items()} for m, v in self.ev.items()}

    def test_cap_history(self):
        h = L.COMPACT_HIST
        self.assertIsNone(L._compact_cap(datetime(2026, 9, 1).timestamp(), datetime(2026, 9, 2).timestamp(), h))
        self.assertEqual(L._compact_cap(datetime(2026, 9, 15).timestamp(), datetime(2026, 9, 15).timestamp(), h), 200_000)
        # born under 200k, compacted after the 09-22 raise -> still 200k (setting read at session start)
        self.assertEqual(L._compact_cap(datetime(2026, 9, 21).timestamp(), datetime(2026, 9, 23).timestamp(), h), 200_000)
        self.assertFalse(L._win_clean(200_000, 300_000))
        self.assertTrue(L._win_clean(200_000, 450_000))
        self.assertTrue(L._win_clean(1_000_000, None))

    def test_scan_discards_setting_caused(self):
        self.mk("a", _lines("claude-sonnet-5", (2026, 9, 15), 168_000))     # 200k setting -> discarded
        self.mk("b", _lines("claude-sonnet-5", (2026, 9, 5), 190_000))      # 300k setting -> too close, discarded
        self.mk("c", _lines("claude-sonnet-4-6", (2026, 9, 25), 180_000))   # 450k setting -> real 200k window
        self.mk("d", _lines("claude-opus-5", (2026, 8, 20), 980_000))       # unset -> real 1M window
        got = self.scan(datetime(2026, 9, 28).timestamp())
        self.assertEqual(got, {"claude-sonnet-4-6": {200_000: 1}, "claude-opus-5": {1_000_000: 1}})
        self.assertEqual(L._ctx_window("claude-sonnet-5", 172_453, ""), (0, ""))   # no clean evidence -> no %

    def test_compact_state_extends_history(self):
        with open(L.COMPACT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"value": 200_000, "since": datetime(2026, 9, 26).timestamp()}, f)
        self.mk("e", _lines("claude-sonnet-4-6", (2026, 9, 27), 180_000))
        self.assertEqual(self.scan(datetime(2026, 9, 28).timestamp()), {})


if __name__ == "__main__":
    unittest.main()
