"""External CLI killed without SessionEnd: pid liveness, silence fallback, grace drop, drawer and counters."""
import errno
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import sidereus, ROOT, js_all, js_fn
from tests._node import node_e

ext = sidereus("ext")
st = sidereus("ext_store")   # store internals are patched on their owner
te = sidereus("timeline_ext")
att = sidereus("attention")
gm = sidereus("plat_gemini")

NOW = 1790000000.0


def _alive_via(kill, pid):
    """config.pid_alive's POSIX branch over a fake kill."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
PAR = "11111111-2222-3333-4444-555555555555"


class Gone(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (st._ext_save_locked, st.EXT_RUNS_FILE, dict(ext._ext), dict(ext._runs),
                      os.kill, st._pid_start, ext.time.time, gm.scan, st.pid_alive)
        st._ext_save_locked = lambda: None
        st.EXT_RUNS_FILE = os.path.join(self.tmp, "ext-runs.json")
        ext._ext.clear()
        ext._runs.clear()
        self.alive = set()
        self.kills = []
        self.starts = {}

        def kill(pid, sig):
            self.kills.append((pid, sig))
            if sig != 0:
                raise AssertionError("only signal 0 is allowed")
            if pid not in self.alive:
                raise ProcessLookupError(errno.ESRCH, "no such process")
        os.kill = kill
        # ⚠Windows config.pid_alive uses OpenProcess, not os.kill: drive the store's own name through the fake kill.
        st.pid_alive = lambda pid: _alive_via(kill, pid)
        st._pid_start = lambda pid: self.starts.get(pid, "")
        self.clock = [NOW]
        ext.time.time = lambda: self.clock[0]
        gm.scan = lambda cut: []

    def tearDown(self):
        (st._ext_save_locked, st.EXT_RUNS_FILE, e, r, os.kill, st._pid_start, ext.time.time,
         gm.scan, st.pid_alive) = self.saved
        ext._ext.clear(); ext._ext.update(e)
        ext._runs.clear(); ext._runs.update(r)
        shutil.rmtree(self.tmp)

    def feed(self, ev, t, sid="g1", **kw):
        req = {"platform": "gemini", "session_id": sid, "event": ev, "cwd": "/tmp/scratch", "ts": t}  # nosec B108 -- fake path, never touched
        req.update(kw)
        return ext.ext_ingest(req)

    def row(self, sid="g1"):
        return next(r for r in ext.ext_rows() if r["sid"] == sid)

    def test_dead_pid_is_gone_then_dropped(self):
        self.feed("UserPromptSubmit", NOW, pid=4242, host=st._HOST, pstart="Thu Sep 24 10:00:00 2026")
        r = self.row()
        self.assertEqual((r["state"], r["goneWhy"]), ("gone", "pid"))
        self.assertTrue(all(sig == 0 for _p, sig in self.kills))
        self.clock[0] = NOW + st.EXT_GONE_GRACE_S + 1
        self.assertEqual(ext.ext_rows(), [])                        # like a SessionEnd

    def test_alive_pid_stays_thinking_even_when_silent(self):
        self.alive.add(4242)
        self.starts[4242] = "Thu Sep 24 10:00:00 2026"
        self.feed("UserPromptSubmit", NOW, pid=4242, host=st._HOST, pstart="Thu Sep 24 10:00:00 2026")
        self.clock[0] = NOW + st.EXT_SILENT_S + 60
        self.assertEqual(self.row()["state"], "think")

    def test_reused_pid_is_gone(self):
        self.alive.add(4242)
        self.starts[4242] = "Fri Sep 25 09:00:00 2026"
        self.feed("PreToolUse", NOW, pid=4242, host=st._HOST, pstart="Thu Sep 24 10:00:00 2026", tool_name="x")
        self.assertEqual(self.row()["state"], "gone")

    def test_pid_from_other_host_ignored(self):
        self.feed("UserPromptSubmit", NOW, pid=4242, host="elsewhere")
        self.assertNotIn("pid", ext._ext[("gemini", "g1")])
        self.assertEqual(self.row()["state"], "think")

    def test_silence_without_pid(self):
        self.feed("PreToolUse", NOW, tool_name="run_shell_command")
        self.clock[0] = NOW + st.EXT_SILENT_S - 5
        self.assertEqual(self.row()["state"], "tool")
        self.clock[0] = NOW + st.EXT_SILENT_S + 5
        r = self.row()
        self.assertEqual((r["state"], r["goneWhy"], r["tool"]), ("gone", "silent", ""))
        self.feed("PostToolUse", NOW + st.EXT_SILENT_S + 6)       # it was alive after all
        self.assertEqual((self.row()["state"], self.row()["goneWhy"]), ("think", ""))

    def test_idle_wait_without_pid_is_not_gone(self):
        self.feed("Stop", NOW)
        self.clock[0] = NOW + 3 * 3600
        self.assertEqual(self.row()["state"], "wait")

    def test_live_pid_prompt_never_ages_out(self):
        self.alive.add(4242)
        self.starts[4242] = "Thu Sep 24 10:00:00 2026"
        self.feed("Notification", NOW, pid=4242, host=st._HOST, pstart="Thu Sep 24 10:00:00 2026")
        for ago in (31 * 60, 2 * 3600, st.EXT_TTL_S + 60):
            self.clock[0] = NOW + ago
            r = self.row()
            self.assertEqual((r["state"], r["blocked"]), ("ask", "알림 대기"), ago)

    def test_pidless_prompt_kept_unknown_liveness(self):
        self.feed("Notification", NOW)
        for ago in (31 * 60, 2 * 3600, st.EXT_TTL_S + 60):
            self.clock[0] = NOW + ago
            r = self.row()
            self.assertEqual((r["state"], r["blocked"]), ("ask", "알림 대기"), ago)

    def test_dead_pid_prompt_leaves(self):
        self.alive.add(4242)
        self.feed("Notification", NOW, pid=4242, host=st._HOST)
        self.alive.discard(4242)
        self.clock[0] = NOW + 31 * 60
        r = self.row()
        self.assertEqual((r["state"], r["blocked"], r["goneWhy"]), ("gone", "", "pid"))
        self.clock[0] = NOW + 31 * 60 + st.EXT_GONE_GRACE_S + 5
        self.assertEqual(ext.ext_rows(), [])

    def test_dismiss_drops_pidless_pending_after_reload(self):
        saved_file = st.EXT_FILE
        st.EXT_FILE = os.path.join(self.tmp, "ext-sessions.json")
        st._ext_save_locked = self.saved[0]                       # real save into the tmp file
        try:
            self.alive.add(4242)
            self.feed("Notification", NOW, sid="g1")
            self.feed("Notification", NOW, sid="g2", pid=4242, host=st._HOST)
            self.assertEqual((ext.ext_dismiss("g1"), ext.ext_dismiss("g2"), ext.ext_dismiss("../x")), (1, 0, 0))
            ext._ext.clear()
            st._ext_load()
            self.assertEqual(sorted(k[1] for k in ext._ext), ["g2"])   # pid row: ext_gone_check owns its exit
        finally:
            st.EXT_FILE = saved_file

    def test_idle_row_still_pruned_after_ttl(self):
        self.feed("Stop", NOW)
        self.clock[0] = NOW + st.EXT_TTL_S + 60
        self.assertEqual(ext.ext_rows(), [])

    def test_session_end_still_works(self):
        self.alive.add(4242)
        self.feed("UserPromptSubmit", NOW, pid=4242, host=st._HOST)
        self.feed("SessionEnd", NOW + 5)
        self.assertEqual(ext.ext_rows(), [])

    def test_dead_child_leaves_drawer_and_ends(self):
        self.feed("UserPromptSubmit", NOW, sid="c1", parent=PAR, pid=4343, host=st._HOST)
        rows = [{"plat": "cc", "sid": PAR}]
        ext.ext_children(rows, now=NOW + 1)
        self.assertNotIn("gms", rows[0])
        self.assertEqual((ext._runs["c1"]["state"], ext._runs["c1"]["end"]), ("gone", NOW))
        tr = te._plat_rows(ext.PLAT_MODS["gemini"], NOW - 60, NOW + 60, {PAR: ("/w/claude", "claude-proj")})
        self.assertEqual([(r["run"], r["done"], r["fin"]) for r in tr], [(False, True, 1)])
        ext.ext_children(rows, now=NOW + st.EXT_GONE_GRACE_S + 5)
        self.assertEqual(ext._runs["c1"]["state"], "done")
        self.assertNotIn(("gemini", "c1"), ext._ext)

    def test_attention_lists_gone_as_low(self):
        self.feed("UserPromptSubmit", NOW, pid=4242, host=st._HOST)
        r = self.row()
        saved = (att._toolfail_idx, att._conflicts)
        att._toolfail_idx, att._conflicts = (lambda now: {}), (lambda rows, now: [])   # no live scans
        try:
            out = att.attention([r], [], read="", read_ids=[])
        finally:
            att._toolfail_idx, att._conflicts = saved
        sig = out["rows"][0]["sigs"][0]
        self.assertEqual((sig["k"], sig["why"]), ("gone", "끊김"))


class HookPid(unittest.TestCase):
    def test_walks_past_shell_to_cli(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ext_hook_g", os.path.join(ROOT, "ext-hooks", "ext_hook.py"))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        tree = {100: (90, "Thu Sep 24 10:00:01 2026", "sh"), 90: (80, "Thu Sep 24 10:00:00 2026", "node")}
        saved = (hook._ps, hook.os.getppid)
        hook._ps, hook.os.getppid = tree.get, (lambda: 100)
        off = os.environ.pop("SIDEREUS_HOOK_NO_PID", None)          # this test fakes ps itself
        try:
            self.assertEqual(hook.cli_pid(), (90, "Thu Sep 24 10:00:00 2026"))
            out, _ = hook.build("gemini", {"hook_event_name": "BeforeAgent", "session_id": "g1"})
            self.assertEqual((out["pid"], out["pstart"]), (90, "Thu Sep 24 10:00:00 2026"))
            hook._ps = lambda pid: None                              # ps failed: no pid rather than the shell's
            out, _ = hook.build("gemini", {"hook_event_name": "BeforeAgent", "session_id": "g1"})
            self.assertNotIn("pid", out)
        finally:
            hook._ps, hook.os.getppid = saved
            if off is not None:
                os.environ["SIDEREUS_HOOK_NO_PID"] = off


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Counters(unittest.TestCase):
    def test_sescount_and_label(self):
        rd = lambda p: open(os.path.join(ROOT, "web", "js", p), encoding="utf-8").read()
        q = js_all()                      # sesCount looked up by name, not by file (survives JS splits)
        s = rd("20-session-state.js")
        fn = lambda src, n: re.search(r"^function " + n + r"\(.*?^}", src, re.S | re.M).group(0)
        lbl = re.search(r"^const LBL = \{.*?\};", s, re.S | re.M).group(0) + "\n" + re.search(r"^const LBL_CTX = \{.*?\};", s, re.S | re.M).group(0)
        sess = [{"state": "think"}, {"state": "gone", "goneWhy": "pid"}, {"state": "gone", "goneWhy": "silent"},
                {"state": "wait", "wf": [{"run": True}]}, {"state": "wait", "wf": [{"run": False}]}]
        js = "\n".join([i18n_prelude("'ko'", ("T", "TV", "U")), lbl, fn(s, "stateLbl"),
                        "let SESS = " + json.dumps(sess) + ";", fn(q, "sesCount"),
                        "let ACCTS = []; const UIS = {getItem: () => null, setItem(){}, removeItem(){}}; function softErr(){}",
                        *(js_fn(n) for n in ("acctList", "mainAcctOk", "mainAcct", "lsGet", "lsSet", "lsDel", "acctLabel", "acctPick", "acctInPick")), fn(s, "sessLabel"),
                        fn(s, "wfRunning"), fn(s, "waitOnLabel"),
                        "console.log(JSON.stringify([sesCount(), SESS.map(sessLabel)]));"])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        cnt, labs = json.loads(r.stdout)
        self.assertEqual((cnt["open"], cnt["think"], cnt["subw"], cnt["idle"]), (3, 1, 1, 1))   # live workflow = working
        self.assertEqual(labs, ["생각 중", "끊김", "끊김?", "워크플로 진행 중", "입력 대기"])


if __name__ == "__main__":
    unittest.main()
