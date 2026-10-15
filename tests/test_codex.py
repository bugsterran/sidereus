"""Codex platform (sidereus/plat_codex.py) from synthetic rollout files — tokens, model, limits, wiring, no text."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from tests._load import sidereus, js_fn
from tests._node import node_e

ext = sidereus("ext")
st = sidereus("ext_store")   # store internals are patched on their owner
cx = sidereus("plat_codex")
te = sidereus("timeline_ext")
H = sidereus("history")
gm = sidereus("plat_gemini")

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ext-hooks", "ext_hook.py")
_spec = importlib.util.spec_from_file_location("ext_hook_cx", HOOK)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

SECRET = "SECRET-CODEX-MESSAGE-TEXT"
SID = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001"
PAR = "11111111-2222-3333-4444-555555555555"


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _u(inp, cached, out, reason=0, write=0):
    return {"input_tokens": inp, "cached_input_tokens": cached, "cache_write_input_tokens": write,
            "output_tokens": out, "reasoning_output_tokens": reason, "total_tokens": inp + out}


def _tc(t, last, total, rate=None):
    return {"timestamp": _iso(t), "type": "event_msg",
            "payload": {"type": "token_count", "rate_limits": rate,
                        "info": None if last is None else {"last_token_usage": last, "total_token_usage": total,
                                                           "model_context_window": 400000}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self._env = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = self.home
        cx._cache.clear()
        # ⚠Pinned to local noon: with the wall clock, fixtures at now-900 fell before midnight right after 00:00.
        self.now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()

    def tearDown(self):
        os.environ["CODEX_HOME"] = self._env
        cx._cache.clear()
        shutil.rmtree(self.home, ignore_errors=True)

    def rollout(self, lines, sid=SID, sub=None, cwd="/w/cxproj", zst=False):
        d = os.path.join(self.home, *(sub or ("sessions", "2026", "09", "24")))
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "rollout-2026-09-24T10-00-00-%s.jsonl%s" % (sid, ".zst" if zst else ""))
        meta = {"timestamp": _iso(self.now - 900), "type": "session_meta",
                "payload": {"id": sid, "cwd": cwd, "timestamp": _iso(self.now - 900), "cli_version": "0.156.1",
                            "source": "exec", "model_provider": "openai", "parent_thread_id": None,
                            "base_instructions": {"text": SECRET}}}
        with open(p, "w") as f:
            f.write("".join(json.dumps(o) + "\n" for o in [meta] + lines))
        os.utime(p, (self.now, self.now))   # mtime follows the pinned clock (scan filters on it)
        return p

    def std(self, t0=None):
        """Two turns, three requests; model changes per turn; one repeated and one null token_count."""
        t = t0 or self.now - 600
        u1, u2, u3 = _u(1000, 800, 100, 40), _u(2000, 1500, 50), _u(500, 0, 20)
        tot = lambda *us: {k: sum(x[k] for x in us) for k in us[0]}
        return [
            {"timestamp": _iso(t), "type": "turn_context", "payload": {"model": "gpt-6-sol", "cwd": "/w/cxproj"}},
            {"timestamp": _iso(t + 1), "type": "event_msg", "payload": {"type": "user_message", "message": SECRET}},
            {"timestamp": _iso(t + 2), "type": "response_item",
             "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": SECRET + " token_count"}]}},
            _tc(t + 3, None, None),                                   # null info
            _tc(t + 4, u1, tot(u1)),
            _tc(t + 5, u1, tot(u1)),                                  # same request re-announced (total unchanged)
            _tc(t + 6, u2, tot(u1, u2)),
            {"timestamp": _iso(t + 60), "type": "turn_context", "payload": {"model": "gpt-6-luna"}},
            _tc(t + 61, u3, tot(u1, u2, u3), rate={"primary": {"used_percent": 12.5, "window_minutes": 300,
                                                             "resets_at": int(self.now + 3600)},
                                                 "secondary": {"used_percent": 30, "window_minutes": 10080,
                                                               "resets_at": int(self.now + 86400)},
                                                 "plan_type": "plus"}),
            {"timestamp": _iso(t + 62), "type": "event_msg",
             "payload": {"type": "task_complete", "last_assistant_message": SECRET}},
        ]


class Parse(Base):
    def test_tokens_model_cost(self):
        self.rollout(self.std())
        c = cx.codex_rollouts(0)
        self.assertEqual(len(c), 1)
        c = c[0]
        self.assertEqual((c["sid"], c["cwd"], c["project"], c["kind"]), (SID, "/w/cxproj", "cxproj", "exec"))
        ms = sorted(c["msgs"].values(), key=lambda v: v[4])
        self.assertEqual(len(ms), 3)                                        # null + repeat skipped
        self.assertEqual(ms[0][:4], (200, 60, 800, 40))                     # cached subtracted; reasoning split out
        self.assertEqual([m[5] for m in ms], ["gpt-6-sol", "gpt-6-sol", "gpt-6-luna"])   # model from turn_context
        self.assertEqual(sum(sum(m[:4]) for m in ms), 1100 + 2050 + 520)    # per-request sum, not cumulative
        self.assertAlmostEqual(ms[0][6], (200 * 2 + 800 * 0.2 + 100 * 10) / 1e6)
        self.assertAlmostEqual(ms[2][6], (500 * 0.10 + 20 * 0.50) / 1e6)
        self.assertEqual(c["rate"][1]["primary"], {"pct": 12.5, "win": 300, "reset": int(self.now + 3600)})

    def test_no_text_in_result(self):
        self.rollout(self.std())
        self.assertNotIn(SECRET, repr(cx.codex_rollouts(0)))

    def test_null_rate_and_unknown_model(self):
        t = self.now - 100
        self.rollout([{"timestamp": _iso(t), "type": "turn_context", "payload": {"model": "gpt-unknown"}},
                      _tc(t + 1, _u(10, 0, 5), _u(10, 0, 5))])
        c = cx.codex_rollouts(0)[0]
        self.assertIsNone(c["rate"])
        self.assertIsNone(list(c["msgs"].values())[0][6])
        self.assertAlmostEqual(cx.cost("gpt-6-sol-2026-08-01", 10 ** 6, 0, 0, 0), 2.0)   # dated alias
        self.assertAlmostEqual(cx.cost("gpt-6-astra", 10 ** 6, 0, 10 ** 6, 0), 12.5)       # cache write price

    def test_zst_skipped_archived_read_and_cache(self):
        self.rollout(self.std(), zst=True)
        self.rollout(self.std(), sid="arch-1", sub=("archived_sessions",))
        c = cx.codex_rollouts(0)
        self.assertEqual([x["sid"] for x in c], ["arch-1"])
        self.assertEqual(cx._stat["zst"], 1)
        with mock.patch.object(cx, "read", side_effect=AssertionError("re-read")):
            cx.codex_rollouts(0)                                              # unchanged (size, mtime) -> cache
        self.assertEqual(cx.codex_rollouts(self.now + 3600), [])             # older than `since`

    def test_path_ok(self):
        p = self.rollout(self.std())
        self.assertTrue(cx.path_ok(p))
        self.assertFalse(cx.path_ok("/etc/passwd.jsonl"))
        self.assertFalse(cx.path_ok(os.path.join(self.home, "config.jsonl")))


class Wiring(Base):
    def setUp(self):
        super().setUp()
        self.saved = (st._ext_save_locked, st._runs_save_locked, dict(ext._ext), dict(ext._runs), dict(ext._tok))
        st._ext_save_locked = lambda: None
        st._runs_save_locked = lambda: None
        ext._ext.clear(); ext._runs.clear(); ext._tok.clear()
        self._gc, gm.scan = gm.scan, (lambda since=0.0: [])

    def tearDown(self):
        st._ext_save_locked, st._runs_save_locked, e, r, k = self.saved
        gm.scan = self._gc
        ext._ext.clear(); ext._ext.update(e)
        ext._runs.clear(); ext._runs.update(r)
        ext._tok.clear(); ext._tok.update(k)
        super().tearDown()

    def test_event_map_mirrored(self):
        self.assertEqual(hook.EVENTS["codex"], cx.EVENTS)
        out, _ = hook.build("codex", {"hook_event_name": "PermissionRequest", "session_id": SID,
                                      "tool_input": {"command": SECRET}})
        self.assertEqual(out["event"], "Notification")
        self.assertNotIn(SECRET, json.dumps(out))

    def test_usage_today_row_and_work(self):
        p = self.rollout(self.std())
        u = ext.ext_usage_today(now=self.now)
        self.assertEqual(list(u), ["cx"])
        self.assertEqual((u["cx"]["tok"], u["cx"]["n_sessions"], u["cx"]["models"]), (3670, 1, ["gpt-6-luna", "gpt-6-sol"]))
        self.assertEqual(u["cx"]["rate"]["secondary"]["pct"], 30)
        ext.ext_ingest({"platform": "codex", "session_id": SID, "event": "SessionStart", "cwd": "/w/cxproj",
                        "model": "gpt-6-luna", "transcript_path": p})
        ext.ext_ingest({"platform": "codex", "session_id": SID, "event": "Notification"})
        rows = ext.ext_rows()
        self.assertEqual((rows[0]["plat"], rows[0]["tok"], rows[0]["blocked"]), ("cx", 3670, "알림 대기"))
        w = ext.ext_work("cx", SID)
        self.assertEqual((w["ok"], w["type"][:5]), (True, "Codex"))
        self.assertEqual(ext.ext_usage_today(now=self.now)["cx"]["tok"], 3670)            # live store does not double-count
        self.assertNotIn(SECRET, json.dumps([u, rows, w]))

    def test_expired_rate_dropped(self):
        lines = self.std()
        lines[8]["payload"]["rate_limits"]["primary"]["resets_at"] = int(self.now - 10)
        self.rollout(lines)
        self.assertEqual(list(ext.ext_usage_today(now=self.now)["cx"]["rate"]), ["secondary"])

    def test_timeline_rows(self):
        self.rollout(self.std())
        rows = te._plat_tl_rows(self.now - 3600, self.now)
        self.assertEqual([(r["tid"], r["plat"], r["kind"], r["tk"]) for r in rows],
                         [("ext:cx|" + SID, "cx", "sess", 3670)])
        self.assertEqual(te._plat_rows(ext.PLAT_MODS["gemini"], self.now - 3600, self.now), [])           # Gemini builder unaffected

    def test_child_under_claude(self):
        self.rollout(self.std())
        ext.ext_ingest({"platform": "codex", "session_id": SID, "event": "SessionStart", "parent": PAR,
                        "cwd": "/w/cxproj", "ts": self.now - 600})
        rows = [{"plat": "cc", "sid": PAR}]
        ext.ext_children(rows, now=self.now)
        self.assertEqual((rows[0]["gms"][0]["plat"], rows[0]["gms"][0]["cmd"]), ("cx", "codex exec"))
        tr = te._plat_tl_rows(self.now - 3600, self.now, {PAR: ("/w/claude", "claude-proj")})
        self.assertEqual([(r["type"], r["parent"], r["cwd"]) for r in tr], [("codex exec", PAR, "/w/claude")])

    def test_history_block(self):
        self.rollout(self.std())
        H._hist_cache.clear()
        with mock.patch.object(H, "_uidx_refresh", lambda: None), mock.patch.dict(H._uidx, {"files": {}}), \
                mock.patch.object(gm, "scan", return_value=[]):
            got = H.history(2)
        H._hist_cache.clear()
        d = got["list"][0]
        self.assertNotIn("gm", d)
        self.assertEqual((d["n"], d["tok"], d["cx"]["n"], d["cx"]["tok"]), (0, 0, 1, 3670))
        self.assertEqual(d["cx"]["rows"][0]["plat"], "cx")
        self.assertNotIn(SECRET, json.dumps(got))


class SbarRate(unittest.TestCase):
    """Bottom-bar Codex segment shows its own 5h/weekly % only when the rollout carried them."""
    def run_js(self, extu):
        import shutil as _sh
        import subprocess
        from tests.test_sbar_gemini import STUBS, _fn
        if not _sh.which("node"):
            self.skipTest("node not installed")
        js = STUBS + "const KE = (k, e) => k;\n" + js_fn("fmtMoney") + "\n" + js_fn("fmtPct") + "\n" + js_fn("extCostStr") + "\n" \
            + js_fn("extRateStr") + "\n" + _fn("60-statusbar.js", "sbExt") + "\n" \
            + _fn("60-statusbar.js", "sbExtSeg") + "\nprocess.stdout.write(JSON.stringify(sbExt(" + json.dumps(extu) + ")));"
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_rate_only_when_present(self):
        h = self.run_js({"cx": {"tok": 3670, "cost": 0.01, "rate": {"primary": {"pct": 12.5, "win": 300},
                                                                     "secondary": {"pct": 30, "win": 10080}}}})
        self.assertIn("ailg-cx", h)
        self.assertNotIn("<b>Codex</b>", h)          # logo only — name stays in the tooltip
        self.assertIn("limit 5h 13% · 7d 30%", h)   # English source (T stub = identity)
        self.assertNotIn("limit 5", self.run_js({"cx": {"tok": 3670, "cost": 0.01}}))


if __name__ == "__main__":
    unittest.main()
