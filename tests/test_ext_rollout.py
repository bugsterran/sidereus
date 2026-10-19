"""Codex sessions without hooks: a fresh rollout file -> one coarse session row (ext.ext_rollout_rows)."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")
cx = sidereus("plat_codex")
lp = sidereus("live_probe")
att = sidereus("attention")

NOW = 1800000000.0
SECRET = "SECRET-ROLLOUT-BODY-TEXT"
SID = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0042"
CODEX_PS = [("101", "1", "/opt/homebrew/bin/codex"), ("7", "1", "/usr/sbin/sshd")]


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class RolloutRows(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self._root, self._mods = cx.root, dict(st.PLAT_MODS)
        cx.root = lambda: self.home
        cx._cache.clear()
        self._ext = dict(ext._ext)
        ext._ext.clear()
        self._snap = list(lp._ps_snap_cache)
        lp._ps_snap_cache[0], lp._ps_snap_cache[1] = NOW, list(CODEX_PS)
        self._prune, self._gone = ext._ext_prune_locked, ext.ext_gone_check
        ext._ext_prune_locked = lambda now: None     # no wall-clock prune of fixture entries
        ext.ext_gone_check = lambda now=None: None   # no live pid probes

    def tearDown(self):
        cx.root = self._root
        cx._cache.clear()
        st.PLAT_MODS.clear()
        st.PLAT_MODS.update(self._mods)
        ext._ext.clear()
        ext._ext.update(self._ext)
        lp._ps_snap_cache[0], lp._ps_snap_cache[1] = self._snap
        ext._ext_prune_locked, ext.ext_gone_check = self._prune, self._gone
        shutil.rmtree(self.home, ignore_errors=True)

    def rollout(self, sid=SID, source="cli", sub=("sessions", "2026", "10", "19"), age=60):
        d = os.path.join(self.home, *sub)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "rollout-2026-10-19T10-00-00-%s.jsonl" % sid)
        t = NOW - 300
        lines = [
            {"timestamp": _iso(t), "type": "session_meta",
             "payload": {"id": sid, "cwd": "/w/cxproj", "timestamp": _iso(t), "source": source,
                         "base_instructions": {"text": SECRET}}},
            {"timestamp": _iso(t + 1), "type": "turn_context", "payload": {"model": "gpt-5.1-codex"}},
            {"timestamp": _iso(t + 2), "type": "response_item",
             "payload": {"type": "message", "content": [{"type": "input_text", "text": SECRET}]}},
            {"timestamp": _iso(t + 3), "type": "event_msg",
             "payload": {"type": "token_count", "info": {
                 "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 20,
                                      "reasoning_output_tokens": 0, "total_tokens": 120},
                 "total_token_usage": {"total_tokens": 120}}}},
        ]
        with open(p, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(o) + "\n" for o in lines))
        os.utime(p, (NOW - age, NOW - age))
        return p

    def test_recent_rollout_gives_one_row(self):
        self.rollout()
        rows = ext.ext_rollout_rows(NOW)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["sid"], r["plat"], r["state"], r["kind"]), (SID, "cx", "unknown", "codex"))
        self.assertIs(r["rollout"], True)
        self.assertEqual((r["cwd"], r["model"], r["project"]), ("/w/cxproj", "gpt-5.1-codex", "cxproj"))
        self.assertEqual((r["blocked"], r["otel"], r["pid"], r["ageSec"]), ("", False, 0, 60))
        self.assertEqual(r["tok"], 120)
        for k in ("plm", "plrun"):
            self.assertNotIn(k, r)

    def test_same_key_set_as_hook_rows(self):
        self.rollout()
        ext._ext[("codex", "other")] = {"cwd": "/w/x", "state": "think", "lastSeen": NOW, "firstSeen": NOW}
        hook = ext.ext_rows()[0]
        roll = ext.ext_rollout_rows(NOW)[0]
        self.assertEqual(set(hook) - {"plm", "plrun"}, set(roll) - {"rollout"})

    def test_hook_entry_wins(self):
        self.rollout()
        ext._ext[("codex", SID)] = {"cwd": "/w/cxproj", "state": "gone", "lastSeen": NOW, "firstSeen": NOW}
        rows = ext.ext_rows() + ext.ext_rollout_rows(NOW)
        self.assertEqual([r["sid"] for r in rows], [SID])
        self.assertNotIn("rollout", rows[0])

    def test_shared_pid_keeps_both_hook_rows(self):
        for s in ("cx-a", "cx-b"):
            ext._ext[("codex", s)] = {"cwd": "/w/p", "state": "think", "pid": 4242, "lastSeen": NOW, "firstSeen": NOW}
        self.assertEqual(sorted(r["sid"] for r in ext.ext_rows()), ["cx-a", "cx-b"])

    def test_skipped_cases(self):
        self.rollout(sid="arch", sub=("archived_sessions",))
        self.rollout(sid="ex", source="exec")
        self.rollout(sid="old", age=ext.ROLL_WIN_S + 5)
        self.assertEqual(ext.ext_rollout_rows(NOW), [])
        self.rollout()
        lp._ps_snap_cache[1] = [("7", "1", "/usr/sbin/sshd")]    # snapshot taken, no codex process
        self.assertEqual(ext.ext_rollout_rows(NOW), [])
        lp._ps_snap_cache[1] = None                             # no snapshot yet: do not guess
        self.assertEqual([r["sid"] for r in ext.ext_rollout_rows(NOW)], [SID])

    def test_subagent_rollout_has_no_row(self):
        p = self.rollout(sid="sub1", source="cli")
        with open(p, encoding="utf-8") as f:
            txt = f.read().replace('"source": "cli"', '"source": {"subagent": {"thread_spawn": {"parent_thread_id": "par-1"}}}')
        with open(p, "w", encoding="utf-8") as f:
            f.write(txt)
        os.utime(p, (NOW - 60, NOW - 60))
        c = [x for x in cx.codex_rollouts(0) if x["sid"] == "sub1"][0]
        self.assertEqual((c["kind"], c["parentThread"]), ("subagent", "par-1"))
        self.assertEqual(ext.ext_rollout_rows(NOW), [])

    def test_ended_hook_session_does_not_return(self):
        self.rollout()
        fake = type("T", (), {"time": staticmethod(lambda: NOW)})
        real, st.time = st.time, fake
        st._ext_ended.clear()
        try:
            ext._ext[("codex", SID)] = {"cwd": "/w/cxproj", "state": "wait", "lastSeen": NOW, "firstSeen": NOW}
            self.assertEqual(ext.ext_ingest({"platform": "codex", "session_id": SID, "event": "SessionEnd"}),
                             (True, "end"))
            self.assertEqual(ext.ext_rollout_rows(NOW), [])
            # dismissing a rollout-only row hides it too
            self.rollout(sid="roll-2")
            self.assertEqual([r["sid"] for r in ext.ext_rollout_rows(NOW)], ["roll-2"])
            self.assertEqual(ext.ext_dismiss("roll-2"), 1)
            self.assertEqual(ext.ext_rollout_rows(NOW), [])
            self.assertEqual(ext.ext_rollout_rows(NOW + ext.ROLL_WIN_S + 1), [])   # rollout itself is stale by then
        finally:
            st.time = real
            st._ext_ended.clear()

    def test_no_message_body(self):
        self.rollout()
        rows = ext.ext_rollout_rows(NOW)
        self.assertTrue(rows)
        self.assertNotIn(SECRET, json.dumps(rows))
        self.assertNotIn(SECRET, json.dumps(ext.ext_work("cx", SID, now=NOW)))

    def test_no_attention_signal(self):
        self.rollout()
        self.assertEqual(att._row_sigs(ext.ext_rollout_rows(NOW)[0], NOW), [])

    def test_work_panel_fallback(self):
        self.rollout()
        d = ext.ext_work("cx", SID, now=NOW)
        self.assertTrue(d["ok"])
        self.assertEqual((d["sid"], d["cwd"], d["model"], d["state"], d["events"]),
                         (SID, "/w/cxproj", "gpt-5.1-codex", "unknown", []))
        self.assertFalse(ext.ext_work("cx", "nope", now=NOW)["ok"])
        self.assertFalse(ext.ext_work("gm", SID, now=NOW)["ok"])


if __name__ == "__main__":
    unittest.main()
