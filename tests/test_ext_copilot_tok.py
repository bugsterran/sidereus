"""Copilot tokens from its usage records on session rows (hook and hook-less), timeline rows and today usage."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")
pr = sidereus("ext_presence")
te = sidereus("timeline_ext")
cp = sidereus("plat_copilot")
gm = sidereus("plat_gemini")
cx = sidereus("plat_codex")

SID = "1ec64219-92f6-43b6-8f39-ab6a91d31212"
NOW = datetime(2027, 1, 15, 12, 0, 0).timestamp()      # local noon: «today» never straddles midnight


def _iso(t):
    return datetime.utcfromtimestamp(t).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _use(uid, inp, out, cr, cw, t):
    return json.dumps({"type": "session.usage_record", "data": {"usage": {
        "model": "gpt-6-luna", "inputTokens": inp, "outputTokens": out, "cacheReadTokens": cr,
        "cacheWriteTokens": cw, "accounting": {"usageId": uid}}}, "timestamp": _iso(t)}, separators=(",", ":"))


def _call(t):
    q = {"chat": {"isUnlimitedEntitlement": False, "entitlementRequests": 50, "usedRequests": 37,
                  "remainingPercentage": 26, "resetDate": _iso(NOW + 9 * 86400)}}
    return json.dumps({"type": "model.model_call_success", "data": {"quotaSnapshots": q}, "timestamp": _iso(t)},
                      separators=(",", ":"))


class CopilotTok(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        d = os.path.join(self.tmp, "session-state", SID)
        os.makedirs(d)
        p = os.path.join(d, "events.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join([_call(NOW - 200), _use("u1", 1000, 50, 600, 300, NOW - 120),
                               _use("u2", 2000, 70, 1500, 0, NOW - 60)]) + "\n")
        os.utime(p, (NOW, NOW))
        clock = mock.Mock()
        clock.time = lambda: NOW
        self.saved = (dict(st._ext), dict(st._tok), dict(st._hooktok), dict(st._ext_ended))
        for d_ in (st._ext, st._tok, st._hooktok, st._ext_ended):
            d_.clear()
        cp._ev.clear()
        pr._PRES_MEMO.clear()
        for x in (mock.patch.object(cp, "root", lambda: self.tmp),
                  mock.patch.object(st, "time", clock), mock.patch.object(ext, "time", clock),
                  mock.patch.object(st, "_ext_save_locked", lambda: None),
                  mock.patch.object(st, "_pid_start", lambda pid: ""),
                  mock.patch.object(ext, "_ext_prune_locked", lambda now: None),
                  mock.patch.object(gm, "scan", lambda since=0.0: []),
                  mock.patch.object(cx, "scan", lambda since=0.0: []),
                  mock.patch.object(te, "ext_runs", lambda parent=None: [])):
            x.start()
            self.addCleanup(x.stop)

    def tearDown(self):
        for d, v in zip((st._ext, st._tok, st._hooktok, st._ext_ended), self.saved):
            d.clear(); d.update(v)
        cp._ev.clear()
        pr._PRES_MEMO.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def presence(self):
        c = {"sid": SID, "cwd": "/w/cp", "branch": "", "start": NOW - 600, "mtime": NOW - 30}
        return mock.patch.object(pr, "_cands", lambda plat, now: [c] if plat == "copilot" else [])

    def test_presence_row_and_timeline_carry_tokens(self):
        with self.presence():
            rows = pr.ext_presence_rows(NOW)
            tl = [r for r in te._plat_tl_rows(NOW - 3600, NOW) if r.get("sid") == SID]
        r = next(r for r in rows if r["sid"] == SID)
        self.assertEqual(r["tok"], 100 + 50 + 900 + 500 + 70 + 1500)
        self.assertEqual(r["tokSplit"], {"in": 600, "out": 120, "cache": 2400, "thought": 0})
        self.assertEqual(r["model"], "gpt-6-luna")
        self.assertEqual(len(tl), 1)
        self.assertEqual(tl[0]["tk"], 3120)
        self.assertEqual([t for t, _n in tl[0]["_tk"]], [NOW - 120, NOW - 60])

    def test_hook_row_carries_tokens(self):
        st._ext[("copilot", SID)] = {"cwd": "/w/cp", "state": "wait", "firstSeen": NOW - 600, "lastSeen": NOW - 30}
        with mock.patch.object(ext, "ext_gone_check", lambda now=None: None):
            r = next(r for r in ext.ext_rows() if r["sid"] == SID)
        self.assertEqual((r["tok"], r["tokSplit"]["cache"]), (3120, 2400))

    def test_usage_today_tokens_and_quota(self):
        u = ext.ext_usage_today(now=NOW)["cp"]
        self.assertEqual((u["tok"], u["in"], u["out"], u["cache"], u["n_sessions"]), (3120, 600, 120, 2400, 1))
        self.assertEqual(u["quota"], {"bucket": "chat", "used": 37, "ent": 50, "unl": False, "pct": 26,
                                      "reset": NOW + 9 * 86400, "at": NOW - 200})

    def test_hooktok_and_record_not_double_counted(self):
        st._hooktok["copilot|" + SID] = {"cwd": "/w/cp", "gens": {"u1": [100, 50, 900, 0, NOW - 120, "gpt-6-luna"]}}
        self.assertEqual(ext.ext_usage_today(now=NOW)["cp"]["tok"], 3120)
        self.assertEqual(st.ext_side_tok("copilot", SID)["tok"], 3120)

    def test_cursor_unchanged(self):
        self.assertIsNone(st.ext_side_tok("cursor", SID))


if __name__ == "__main__":
    unittest.main()
