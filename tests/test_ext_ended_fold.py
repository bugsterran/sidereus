"""Ended external CLI sessions fold under «Show n ended» like Claude rows (R1-R4); the timeline is unchanged."""
import os
import shutil
import tempfile
import time as _real_time
import unittest

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")
te = sidereus("timeline_ext")
att = sidereus("attention")
ses = sidereus("sessions")

NOW = 1790000000.0
PLATS = ("codex", "cursor", "copilot", "gemini")
SID = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0042"


class _Clock(object):
    """Mutable stand-in for a module's `time` (only time() is faked)."""

    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t

    def __getattr__(self, name):
        return getattr(_real_time, name)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clock = _Clock(NOW)
        names = {ext: ("time", "ext_tok_refresh", "ext_side_tok", "plm_of", "pl_model", "mbox_codex",
                       "_rollouts", "_codex_running"),
                 st: ("time", "_ext_save_locked", "_runs_save_locked", "_pid_gone", "EXT_FILE"),
                 te: ("ext_side_msgs", "ext_hook_cwds")}
        self.saved = [(m, n, getattr(m, n)) for m, ns in names.items() for n in ns]
        self.saved_maps = (dict(st._ext), dict(st._ext_ended), dict(st._runs))
        st._ext.clear(); st._ext_ended.clear(); st._runs.clear()
        ext.time = st.time = self.clock
        ext.ext_tok_refresh = lambda *a: None
        ext.ext_side_tok = lambda p, s: None
        ext.plm_of = lambda sid, now: None
        ext.pl_model = lambda *a, **k: []
        ext.mbox_codex = lambda cwd: ("", "")
        ext._rollouts = lambda now: []
        ext._codex_running = lambda: True
        st._ext_save_locked = lambda: None
        st._runs_save_locked = lambda: None
        st.EXT_FILE = os.path.join(self.tmp, "ext-sessions.json")
        self.dead = set()
        st._pid_gone = lambda pid, pstart: pid in self.dead
        te.ext_side_msgs = lambda cut: {}
        te.ext_hook_cwds = lambda: {}

    def tearDown(self):
        for m, n, v in self.saved:
            setattr(m, n, v)
        for live, old in zip((st._ext, st._ext_ended, st._runs), self.saved_maps):
            live.clear(); live.update(old)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def feed(self, plat, ev, t, sid="s1", **kw):
        req = {"platform": plat, "session_id": sid, "event": ev, "cwd": "/w/proj", "ts": t}
        req.update(kw)
        self.assertEqual(st.ext_ingest(req)[0], True)

    def at(self, t):
        self.clock.t = t
        return {(r["kind"], r["sid"]): r for r in ext.ext_rows()}


class EndedFold(Base):
    def test_r1_every_signal_folds_as_done_per_platform(self):
        for plat in PLATS:
            with self.subTest(plat=plat):
                st._ext.clear()
                self.feed(plat, "UserPromptSubmit", NOW, sid="end")
                self.feed(plat, "SessionEnd", NOW + 1, sid="end")
                self.dead.add(4242)
                self.feed(plat, "UserPromptSubmit", NOW, sid="pid", pid=4242, host=st._HOST)
                self.feed(plat, "PreToolUse", NOW, sid="silent", tool_name="x")
                self.feed(plat, "Stop", NOW, sid="idle")
                rows = self.at(NOW + max(st.EXT_SILENT_S, st.PIDLESS_IDLE_SEC) + 5)
                for sid in ("end", "pid", "silent", "idle"):
                    r = rows[(plat, sid)]
                    self.assertEqual((r["state"], r["goneWhy"], r["pid"], r["blocked"]), ("done", "", 0, ""), sid)
                rows = self.at(NOW + max(st.EXT_SILENT_S, st.PIDLESS_IDLE_SEC) + st.EXT_GONE_GRACE_S + 60)
                self.assertEqual(sorted(s for (p, s), r in rows.items() if r["state"] == "done"),
                                 ["end", "idle", "pid", "silent"])
                self.assertEqual({sid: st._ext[(plat, sid)].get("endWhy") for sid in ("end", "pid", "silent")},
                                 {"end": "end", "pid": "pid", "silent": "silent"})

    def test_r2_keep_window_matches_claude(self):
        self.assertEqual(ses.sessions.__defaults__[0] * 3600, st.EXT_DONE_KEEP_S)
        self.feed("cursor", "UserPromptSubmit", NOW - 10)
        self.clock.t = NOW
        self.feed("cursor", "SessionEnd", NOW)          # ended = receive time
        self.feed("gemini", "Stop", NOW - st.PIDLESS_IDLE_SEC, sid="idle")
        self.assertIn(("cursor", "s1"), self.at(NOW + st.EXT_DONE_KEEP_S - 1))
        self.assertIn(("gemini", "idle"), self.at(NOW + st.EXT_DONE_KEEP_S - 1))
        rows = self.at(NOW + st.EXT_DONE_KEEP_S + 1)
        self.assertNotIn(("cursor", "s1"), rows)
        self.assertNotIn(("gemini", "idle"), rows)
        self.assertNotIn(("cursor", "s1"), st._ext)

    def test_r3_new_event_revives(self):
        self.feed("codex", "UserPromptSubmit", NOW - 100, model="gpt-x")
        self.feed("codex", "SessionEnd", NOW)
        self.feed("codex", "SessionEnd", NOW + 1)       # repeated end: no-op
        self.assertEqual(st._ext[("codex", "s1")]["ended"], NOW)
        self.clock.t = NOW + 60
        self.feed("codex", "UserPromptSubmit", NOW + 60)
        v = st._ext[("codex", "s1")]
        self.assertEqual((v["state"], v.get("ended"), v.get("endWhy"), v["firstSeen"], v["model"]),
                         ("think", None, None, NOW + 60, "gpt-x"))   # run time restarts at the revival
        self.assertEqual([e["e"] for e in v["ev"]], ["UserPromptSubmit", "UserPromptSubmit"])
        r = self.at(NOW + 61)[("codex", "s1")]
        self.assertEqual((r["state"], r["runmin"]["run"]), ("think", 0))
        self.feed("codex", "Stop", NOW + 120)
        self.assertEqual(st._ext[("codex", "s1")]["firstSeen"], NOW + 60)   # a live row keeps its firstSeen

    def test_r4_no_attention_signal(self):
        self.feed("gemini", "Notification", NOW)
        self.feed("gemini", "SessionEnd", NOW + 1)
        rows = list(self.at(NOW + 2).values())
        saved = (att._toolfail_idx, att._conflicts)
        att._toolfail_idx, att._conflicts = (lambda now: {}), (lambda rows, now: [])
        try:
            out = att.attention(rows, [], read="", read_ids=[])
        finally:
            att._toolfail_idx, att._conflicts = saved
        self.assertEqual(out["rows"], [])

    def test_codex_rollout_of_ended_sid_stays_hidden(self):
        t = NOW + st.EXT_ENDED_KEEP_S + 1
        ext._rollouts = lambda now: [{"sid": SID, "live": True, "kind": "", "mtime": t - 10, "cwd": "/w",
                                      "start": t - 100, "msgs": {}}]
        self.assertEqual([r["sid"] for r in ext.ext_rollout_rows(t)], [SID])   # fixture shows without a store row
        self.feed("codex", "Stop", NOW - 10, sid=SID)
        self.feed("codex", "SessionEnd", NOW, sid=SID)
        st._ext_ended.clear()                           # past EXT_ENDED_KEEP_S: only the folded row hides it
        self.assertIn(SID, st.ext_ended("codex", t))
        self.assertEqual(ext.ext_rollout_rows(t), [])

    def test_survives_reload(self):
        st._ext_save_locked = next(v for m, n, v in self.saved if m is st and n == "_ext_save_locked")   # real save, temp file
        self.feed("copilot", "Stop", NOW - 10)
        self.feed("copilot", "SessionEnd", NOW)
        st._ext.clear()
        self.clock.t = NOW + 3600
        st._ext_load()
        self.assertEqual((st._ext[("copilot", "s1")]["endWhy"], self.at(NOW + 3600)[("copilot", "s1")]["state"]),
                         ("end", "done"))

    def test_timeline_unchanged_by_ended_record(self):
        def tl():
            return (te._ext_tl(NOW - 3600, NOW, {}, "cursor", "cu", "CLI", "Cursor", te._hook_scan("cursor"))
                    + te._ext_tl(NOW - 3600, NOW, {}, "gemini", "gm", "CLI", "Gemini", lambda cut: []))
        for plat in ("cursor", "gemini"):
            self.feed(plat, "Stop", NOW - 50, sid="live")
        base = tl()
        for plat in ("cursor", "gemini"):
            self.feed(plat, "UserPromptSubmit", NOW - 100, sid="gone")
            self.feed(plat, "SessionEnd", NOW - 90, sid="gone")
        self.assertTrue(st._ext[("cursor", "gone")]["ended"])
        self.assertEqual(tl(), base)
        self.assertEqual(len(base), 2)


class PresenceFolder(Base):
    def test_ended_row_does_not_hide_new_session_in_its_folder(self):
        pr = sidereus("ext_presence")
        saved = (pr.plat_cursor.scan, pr.plat_copilot.scan)
        self.addCleanup(lambda: (setattr(pr.plat_cursor, "scan", saved[0]), setattr(pr.plat_copilot, "scan", saved[1]),
                                 pr._PRES_MEMO.clear()))
        pr.plat_cursor.scan = lambda since, n, stat_n: [{"sid": "fresh", "cwd": "/w/proj", "start": NOW - 60,
                                                         "mtime": NOW - 5}]
        pr.plat_copilot.scan = lambda n: []
        self.feed("cursor", "Stop", NOW - 100, sid="old")
        self.feed("cursor", "SessionEnd", NOW - 90, sid="old")
        pr._PRES_MEMO.clear()
        self.assertEqual([r["sid"] for r in pr.ext_presence_rows(NOW)], ["fresh"])
        self.feed("cursor", "Stop", NOW - 10, sid="live")      # a live hook row in the folder still hides it
        pr._PRES_MEMO.clear()
        self.assertEqual(pr.ext_presence_rows(NOW), [])


if __name__ == "__main__":
    unittest.main()
