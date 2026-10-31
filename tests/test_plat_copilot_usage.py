"""Copilot usage records and quota from events.jsonl (plat_copilot): only usage lines are parsed, content never leaks."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

cp = sidereus("plat_copilot")

SID = "1ec64219-92f6-43b6-8f39-ab6a91d31212"
SID2 = "2fd75320-a3a7-47c4-9c3d-05aa1b2c3d4e"
NOW = 1800000000.0          # 2027-01-15T08:00:00Z
SECRET = "SECRET-PROMPT-TEXT"


def _iso(t):
    import datetime
    return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _use(uid, inp, out, cr, cw, t, model="gpt-6-luna"):
    d = {"type": "session.usage_record", "data": {"usage": {
        "model": model, "inputTokens": inp, "outputTokens": out, "cacheReadTokens": cr, "cacheWriteTokens": cw,
        "accounting": {"sourceSessionId": SID, "usageId": uid}}}, "id": "x", "timestamp": _iso(t)}
    return json.dumps(d, separators=(",", ":"))


def _call(t, used, ent=50, pct=26.0, reset=NOW + 9 * 86400, prem_ent=0):
    q = {"chat": {"isUnlimitedEntitlement": False, "entitlementRequests": ent, "usedRequests": used,
                  "remainingPercentage": pct, "resetDate": _iso(reset), "note": SECRET},
         "premium_interactions": {"isUnlimitedEntitlement": False, "entitlementRequests": prem_ent,
                                  "usedRequests": 3, "remainingPercentage": 90, "resetDate": _iso(reset)}}
    d = {"type": "model.model_call_success",
         "data": {"requestMessages": [{"role": "user", "content": SECRET}], "response": SECRET, "quotaSnapshots": q},
         "timestamp": _iso(t)}
    return json.dumps(d, separators=(",", ":"))


def _fixture():
    return "\n".join([
        json.dumps({"type": "user.message", "data": {"content": SECRET}, "timestamp": _iso(NOW - 50)},
                   separators=(",", ":")),
        _call(NOW - 40, used=37),
        # user text that embeds the usage-record type string (escaped inside a JSON string)
        json.dumps({"type": "user.message", "data": {"content": '{"type":"session.usage_record" ' + SECRET}},
                   separators=(",", ":")),
        _use("u1", 1000, 50, 600, 300, NOW - 30),
        _use("u2", 2000, 70, 1500, 0, NOW - 20, model="claude-sonnet-4.5"),
    ]) + "\n"


class Usage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._root = cp.root
        cp.root = lambda: self.tmp
        cp._ev.clear()
        self.d = os.path.join(self.tmp, "session-state", SID)
        os.makedirs(self.d)
        self.p = os.path.join(self.d, "events.jsonl")

    def tearDown(self):
        cp.root = self._root
        cp._ev.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, s, mode="w", path=None):
        with open(path or self.p, mode, encoding="utf-8") as f:
            f.write(s)
        os.utime(path or self.p, (NOW, NOW))

    def test_only_usage_lines_parsed_and_no_secret(self):
        self.write(_fixture())
        calls = []
        real = cp.json.loads
        cp.json.loads = lambda s, *a, **k: (calls.append(1), real(s, *a, **k))[1]
        dec = []
        Dec = cp.json.JSONDecoder

        class Rec(Dec):
            def raw_decode(self, s, idx=0):
                r = Dec.raw_decode(self, s, idx)
                dec.append(r[0])
                return r
        cp.json.JSONDecoder = Rec        # json.loads keeps its own pre-built decoder, so only _quota_line lands here
        try:
            ms = cp.usage_msgs(SID)
            q = cp.quota(NOW)
        finally:
            cp.json.loads = real
            cp.json.JSONDecoder = Dec
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(dec), 1)
        self.assertIn(SECRET, json.dumps(dec[0]))      # the raw slice may hold it; what is kept must not
        out = json.dumps([ms, q, {k: v["quota"] for k, v in cp._ev.items()}])
        self.assertNotIn(SECRET, out)
        self.assertEqual(ms["u1"][:4], (100, 50, 900, 0))
        self.assertEqual(ms["u2"][:4], (500, 70, 1500, 0))
        self.assertEqual(ms["u2"][5], "claude-sonnet-4.5")
        self.assertEqual(q, {"bucket": "chat", "used": 37, "ent": 50, "unl": False, "pct": 26.0,
                             "reset": NOW + 9 * 86400, "at": NOW - 40})

    def test_raw_decode_value_holds_no_content_after_filter(self):
        # A quota object carrying text keeps only numbers/bools/reset per bucket.
        at, qs = cp._quota_line(_call(NOW, used=1).encode())
        self.assertNotIn(SECRET, json.dumps(qs))
        self.assertEqual(set(qs["chat"]), {"isUnlimitedEntitlement", "entitlementRequests", "usedRequests",
                                           "remainingPercentage", "reset"})

    def test_incremental_partial_line_waits(self):
        a = _use("u1", 10, 1, 0, 0, NOW - 5)
        b = _use("u2", 20, 2, 0, 0, NOW - 4)
        self.write(a + "\n" + b[:30])
        self.assertEqual(set(cp.usage_msgs(SID)), {"u1"})
        self.write(b[30:] + "\n", mode="a")
        self.assertEqual(set(cp.usage_msgs(SID)), {"u1", "u2"})
        self.assertEqual(cp._ev[self.p]["off"], os.path.getsize(self.p))

    def test_truncate_resets(self):
        self.write(_use("u1", 10, 1, 0, 0, NOW) + "\n" + _use("u2", 10, 1, 0, 0, NOW) + "\n")
        self.assertEqual(len(cp.usage_msgs(SID)), 2)
        self.write(_use("u3", 10, 1, 0, 0, NOW) + "\n")
        self.assertEqual(set(cp.usage_msgs(SID)), {"u3"})

    def test_key_falls_back_to_offset(self):
        ln = json.dumps({"type": "session.usage_record", "data": {"usage": {"inputTokens": 5, "outputTokens": 1}},
                         "timestamp": _iso(NOW)}, separators=(",", ":"))
        self.write("{}\n" + ln + "\n")
        self.assertEqual(list(cp.usage_msgs(SID)), ["@3"])

    def test_oversize_skipped(self):
        self.write(_use("u1", 10, 1, 0, 0, NOW) + "\n")
        old = cp.SCAN_MAX
        cp.SCAN_MAX = 10
        try:
            self.assertEqual(cp.usage_msgs(SID), {})
            self.assertEqual(cp.msgs_since(0), {})
        finally:
            cp.SCAN_MAX = old

    def test_bad_sid_refused(self):
        self.assertEqual(cp.usage_msgs("../" + SID), {})
        self.assertEqual(cp.usage_msgs("x"), {})

    def test_msgs_since_filters(self):
        self.write(_fixture())
        self.assertEqual(set(cp.msgs_since(NOW - 25)[SID]), {"u2"})
        self.assertEqual(cp.msgs_since(NOW + 1), {})

    def test_no_rereads_across_narrow_and_wide_scans(self):
        base = os.path.join(self.tmp, "session-state")
        for i in range(100):
            sid = "%08x-0000-4000-8000-%012x" % (i, i)
            os.makedirs(os.path.join(base, sid), exist_ok=True)
            p = os.path.join(base, sid, "events.jsonl")
            self.write(_call(NOW - 1000 + i, used=i) + "\n" + _use("u%d" % i, 10, 1, 0, 0, NOW - 1000 + i) + "\n", path=p)
            os.utime(p, (NOW, NOW - (0 if i < 3 else 86400)))
        parsed = []
        ul, ql = cp._usage_line, cp._quota_line
        cp._usage_line = lambda ln, off: (parsed.append(1), ul(ln, off))[1]
        cp._quota_line = lambda ln: (parsed.append(1), ql(ln))[1]
        try:
            for _ in range(2):
                if _ == 1:
                    parsed.clear()
                self.assertEqual(len(cp.msgs_since(NOW - 3600)), 3)
                self.assertIsNotNone(cp.quota(NOW))
        finally:
            cp._usage_line, cp._quota_line = ul, ql
        self.assertEqual(parsed, [])       # second round: every file was already read to its end

    def test_quota_newest_across_sessions_and_past_reset(self):
        self.write(_call(NOW - 100, used=10) + "\n")
        d2 = os.path.join(self.tmp, "session-state", SID2)
        os.makedirs(d2)
        p2 = os.path.join(d2, "events.jsonl")
        self.write(_call(NOW - 10, used=12, prem_ent=300) + "\n", path=p2)
        q = cp.quota(NOW)
        self.assertEqual((q["bucket"], q["used"], q["ent"], q["at"]), ("premium_interactions", 3, 300, NOW - 10))
        cp._ev.clear()
        self.write(_call(NOW + 5, used=1, reset=NOW - 1) + "\n", path=p2)
        self.assertIsNone(cp.quota(NOW))


if __name__ == "__main__":
    unittest.main()
