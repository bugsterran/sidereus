"""`sessions()`: a transcript whose tail says `continued-in` gives its path slot to the successor, even when the
remaining process is a plain `claude` (no sid in argv). Temp files only, no live files."""
import json
import os
import tempfile
import unittest

from tests._load import sidereus

ss = sidereus("sessions")

OLD = "cc33cc33-0000-4000-8000-000000000001"
NEW = "dd44dd44-0000-4000-8000-000000000002"
CWD = "/Users/x/proj"
PATCH = ("live_cwds", "_recent_transcripts", "_parse_transcript", "sid_alive", "_session_row",
         "_note_bg_done", "_note_transition", "_note_ctx", "ext_rows", "_subs_mt", "_subs_newer")


def _write(path, recs):
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


class SessContinued(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(ss, k) for k in PATCH}
        self.d = tempfile.mkdtemp()
        self.old = os.path.join(self.d, OLD + ".jsonl")
        self.new = os.path.join(self.d, NEW + ".jsonl")
        _write(self.new, [{"type": "user", "sessionId": NEW, "cwd": CWD}])
        ss._parse_transcript = lambda fp: {"cwd": CWD, "sid": os.path.basename(fp)[:-6]}
        ss._session_row = lambda fp, mt, now, live, p, stale=False: {
            "sid": p["sid"], "state": "done" if stale else "wait", "ageSec": 0}
        for k in ("_note_bg_done", "_note_transition", "_note_ctx"):
            setattr(ss, k, lambda *a, **k: None)
        ss.ext_rows = lambda: []
        ss._subs_mt = lambda sd: 0
        ss._subs_newer = lambda sd, t: False
        ss.sid_alive = lambda sid: False                   # plain `claude` pid: no official/argv sid for either
        ss.live_cwds = lambda: {CWD: 1}
        # ⚠The old file is **newer** (metadata written at exit) — it comes first and used to take the slot.
        ss._recent_transcripts = lambda now, h, live: [(2.0, self.old), (1.0, self.new)]
        with ss._parse_lock:
            ss._parse_cache.pop(self.old, None)
            ss._parse_cache.pop(self.new, None)

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(ss, k, v)
        with ss._parse_lock:
            ss._parse_cache.pop(self.old, None)
            ss._parse_cache.pop(self.new, None)
        for fn in os.listdir(self.d):
            os.remove(os.path.join(self.d, fn))
        os.rmdir(self.d)

    def states(self):
        return {r["sid"]: r["state"] for r in ss.sessions()}

    def test_continued_gives_slot_to_successor(self):
        _write(self.old, [{"type": "assistant", "sessionId": OLD},
                          {"type": "continued-in", "sessionId": OLD, "continuedInSessionId": NEW},
                          {"type": "last-prompt"}, {"type": "cost-state"}])
        self.assertEqual(self.states(), {OLD: "done", NEW: "wait"})

    def test_resumed_after_continuation_keeps_slot(self):
        # ⚠A conversation line after the marker means the old session was resumed — it is live again.
        _write(self.old, [{"type": "continued-in", "sessionId": OLD, "continuedInSessionId": NEW},
                          {"type": "user", "sessionId": OLD}])
        self.assertEqual(self.states(), {OLD: "wait", NEW: "done"})


if __name__ == "__main__":
    unittest.main()
