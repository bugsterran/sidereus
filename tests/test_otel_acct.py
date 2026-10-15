"""Per-account OTel aggregates (sidereus/otel_acct.py) fed from otel._otel_ingest.

No live files: OA_FILE is a tmp path (tests/_load.py); `claude_roots._acct_rec`/`accounts` are patched on their owner.
"""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from tests._load import sidereus

O = sidereus("otel")
A = sidereus("otel_acct")
C = sidereus("otel_cache")
H = sidereus("otel_hooks")
CR = sidereus("claude_roots")

ACCTS = [{"dir": "/cfg/main", "label": "me", "primary": True}, {"dir": "/cfg/work", "label": "work", "primary": False}]
RECS = {"sid-main-0001": "/cfg/main", "sid-work-0001": "/cfg/work"}
T0 = time.mktime(time.strptime("2026-10-14 12", "%Y-%m-%d %H"))


def _attrs(d):
    return [{"key": k, "value": ({"intValue": v} if isinstance(v, int) else {"stringValue": str(v)})}
            for k, v in d.items()]


def _payload(*recs):
    return {"resourceLogs": [{"scopeLogs": [{"logRecords": [{"attributes": _attrs(r)} for r in recs]}]}]}


def _api(sid, rq, model="m1"):
    return {"event.name": "api_request", "session.id": sid, "request_id": rq, "model": model,
            "query_source": "repl_main_thread", "input_tokens": 10, "output_tokens": 5,
            "cache_read_tokens": 300000, "cache_creation_tokens": 100000}


def _tool(sid, seq, ok="true"):
    return {"event.name": "tool_result", "session.id": sid, "tool_name": "Bash", "success": ok,
            "duration_ms": 40, "event.sequence": seq}


def _hook(sid, ev="Stop"):
    d = {"event.name": "hook_execution_complete", "hook_event": ev, "total_duration_ms": 30,
         "num_non_blocking_error": 1, "hook_name": "secret-script.sh"}
    if sid:
        d["session.id"] = sid
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="oa-")
        for mod, name, val in ((A, "OA_FILE", os.path.join(self.tmp, "otel-acct.json")),
                               (C, "OC_FILE", os.path.join(self.tmp, "oc.json")),
                               (H, "OH_FILE", os.path.join(self.tmp, "oh.json")),
                               (O, "OTEL_TDAY_FILE", os.path.join(self.tmp, "tday.json"))):
            p = mock.patch.object(mod, name, val)
            p.start()
            self.addCleanup(p.stop)
        stores = [(A, "_oa", {}), (A, "_oa_meta", {"loaded": True, "savedAt": 0.0, "dirty": False, "since": 0}),
                  (O, "_otel", {}), (O, "_otel_tools", {}), (O, "_otel_tools_all", {}), (O, "_otel_tday", {}),
                  (O, "_otel_tday_meta", {"loaded": True, "savedAt": 0.0, "dirty": False}),
                  (O, "_otel_src", {}), (O, "_otel_sample", {}),
                  (C, "_oc", {}), (C, "_oc_meta", {"loaded": True, "savedAt": 0.0, "dirty": False}),
                  (H, "_oh", {}), (H, "_oh_meta", {"loaded": True, "savedAt": 0.0, "dirty": False})]
        for mod, name, val in stores:
            p = mock.patch.object(mod, name, val)
            p.start()
            self.addCleanup(p.stop)
        for mod, name, val in ((O, "_otel_stat", dict(O._otel_stat, acctUnk=0, names={}, bySrc={})),
                               (O, "_otel_req", O.BoundedMemo(100)), (A, "_oa_sid", A.BoundedMemo(100)),
                               (A, "_oa_miss", A.BoundedMemo(100))):
            p = mock.patch.object(mod, name, val)
            p.start()
            self.addCleanup(p.stop)
        for p in (mock.patch.object(CR, "_acct_rec", side_effect=lambda s: RECS.get(s, "")),
                  mock.patch.object(CR, "accounts", return_value=[dict(a) for a in ACCTS]),
                  mock.patch.object(O, "_usage_add"),
                  mock.patch.object(O.time, "time", return_value=T0)):
            p.start()
            self.addCleanup(p.stop)


class IngestTests(Base):
    def test_label_mapping(self):
        self.assertEqual((A._oa_label("sid-main-0001"), A._oa_label("sid-work-0001"), A._oa_label("sid-none-0001"),
                          A._oa_label(None)), ("", "work", None, None))

    def test_unlabelled_extra_is_unknown_not_primary(self):
        CR.accounts.return_value = [dict(ACCTS[0]), dict(ACCTS[1], label="")]
        self.assertIsNone(A._oa_label("sid-work-0001"))

    def test_unknown_is_memoised_then_retried_after_ttl(self):
        self.assertIsNone(A._oa_label("sid-late-0001"))
        RECS["sid-late-0001"] = "/cfg/work"
        self.addCleanup(RECS.pop, "sid-late-0001", None)
        self.assertIsNone(A._oa_label("sid-late-0001"))           # within the TTL: no second record read
        self.assertEqual(CR._acct_rec.call_count, 1)
        with mock.patch.object(A.time, "time", return_value=T0 + A.OA_MISS_S + 1):
            self.assertEqual(A._oa_label("sid-late-0001"), "work")

    def test_known_sid_fills_only_its_account(self):
        O._otel_ingest(_payload(_api("sid-work-0001", "r1"), _tool("sid-work-0001", 1), _hook("sid-work-0001")))
        self.assertEqual(list(A._oa), ["work"])
        b = A._oa["work"]
        day = "2026-10-14"
        self.assertEqual(b["t"][day]["Bash"][:2], [1, 0])
        self.assertEqual(b["c"][day]["t"], [300000, 100000])
        self.assertEqual(b["h"][day]["Stop"], [1, 30, 1])
        self.assertEqual(sum(v[0] for r in b["s"].values() for v in r.values()), 1)
        self.assertEqual(O._otel_stat["acctUnk"], 0)

    def test_unknown_sid_fills_none_and_counts(self):
        O._otel_ingest(_payload(_api("sid-none-0001", "r1"), _tool("sid-none-0001", 1), _hook("sid-none-0001"),
                                _hook(None)))
        self.assertEqual(A._oa, {})
        self.assertEqual(O._otel_stat["acctUnk"], 4)
        self.assertTrue(O._otel_tday and C._oc and H._oh)      # All still counts them

    def test_per_account_never_exceeds_all(self):
        O._otel_ingest(_payload(_api("sid-main-0001", "r1"), _api("sid-work-0001", "r2"),
                                _api("sid-none-0001", "r3"), _tool("sid-main-0001", 1), _tool("sid-work-0001", 1),
                                _hook("sid-main-0001"), _hook("sid-work-0001"), _hook(None)))
        rank_all = O._otel_tool_rank("2026-10-01")["calls"]
        per = [O._otel_tool_rank("2026-10-01", src=A._oa[k]["t"])["calls"] for k in ("", "work")]
        self.assertEqual((rank_all, sum(per)), (2, 2))
        h_all = H._oh_view("2026-10-01")["n"]
        h_per = [H._oh_view("2026-10-01", src=A._oa[k]["h"])["n"] for k in ("", "work")]
        self.assertEqual((h_all, sum(h_per)), (3, 2))
        m_all = O._otel_src_models(T0 - 3600, T0 + 3600)["n"]
        m_per = [O._otel_src_models(T0 - 3600, T0 + 3600, src=A._oa[k]["s"])["n"] for k in ("", "work")]
        self.assertEqual((m_all, sum(m_per)), (3, 2))
        c_all = sum(d["create"] for d in C._oc_view("2026-10-01")["days"])
        c_per = [sum(d["create"] for d in C._oc_view("2026-10-01", src=A._oa[k]["c"])["days"]) for k in ("", "work")]
        self.assertTrue(sum(c_per) <= c_all)

    def test_views_without_src_unchanged(self):
        O._otel_ingest(_payload(_api("sid-work-0001", "r1"), _tool("sid-work-0001", 1)))
        self.assertEqual(O._otel_tool_rank("2026-10-01"), O._otel_tool_rank("2026-10-01", src=O._otel_tday))
        self.assertEqual(O._otel_src_heat(T0 - 3600, T0), O._otel_src_heat(T0 - 3600, T0, src=O._otel_src))
        self.assertEqual(C._oc_view("2026-10-01"), C._oc_view("2026-10-01", src=C._oc))
        self.assertEqual(H._oh_view("2026-10-01"), H._oh_view("2026-10-01", src=H._oh))

    def test_stored_shape_has_no_sid_or_hook_name_outside_cache(self):
        O._otel_ingest(_payload(_hook("sid-work-0001"), _tool("sid-work-0001", 1), _api("sid-work-0001", "r1")))
        A._oa_save(T0, force=True)
        with open(A.OA_FILE, encoding="utf-8") as f:
            d = json.load(f)
        b = d["a"]["work"]
        for part in ("t", "s", "h"):
            self.assertNotIn("sid-work-0001", json.dumps(b[part]))
        self.assertNotIn("secret-script", json.dumps(d))
        self.assertNotIn("/cfg/", json.dumps(d))


class PersistTests(Base):
    def test_round_trip_and_since_once(self):
        A._oa_tool("work", T0, "Bash", 0, 12)
        A._oa_tool("work", T0 + 99, "Bash", 1, 8)
        self.assertEqual(A._oa_meta["since"], int(T0))
        self.assertTrue(A._oa_save(T0 + 100, force=True))
        saved = json.dumps(A._oa, sort_keys=True)
        A._oa.clear()
        A._oa_meta.update(loaded=False, since=0)
        A._oa_load()
        self.assertEqual(json.dumps(A._oa, sort_keys=True), saved)
        self.assertEqual(A._oa_meta["since"], int(T0))
        A._oa_load()                                    # second load does not double-count
        self.assertEqual(A._oa["work"]["t"]["2026-10-14"]["Bash"][0], 2)

    def test_since_per_account_and_old_file_fallback(self):
        A._oa_hook("work", T0, "Stop", 1, 0)
        A._oa_hook("", T0 + 500, "Stop", 1, 0)
        self.assertEqual((A._oa_snap("work")[1], A._oa_snap("")[1]), (int(T0), int(T0) + 500))
        with open(A.OA_FILE, "w", encoding="utf-8") as f:      # file written before per-account since
            json.dump({"v": 1, "since": 1000, "a": {"old": {"h": {"2026-10-14": {"Stop": [1, 2, 0]}}}}}, f)
        A._oa.clear()
        A._oa_meta.update(loaded=False, since=0)
        A._oa_load()
        self.assertEqual(A._oa_snap("old")[1], 1000)

    def test_account_cap(self):
        for i in range(A.OA_ACCT_CAP + 2):
            A._oa_hook("a%d" % i, T0, "Stop", 1, 0)
        self.assertEqual(len(A._oa), A.OA_ACCT_CAP)

    def test_snap_is_a_copy(self):
        A._oa_hook("work", T0, "Stop", 1, 0)
        s, since = A._oa_snap("work")
        s["h"]["2026-10-14"]["Stop"][0] = 99
        self.assertEqual(A._oa["work"]["h"]["2026-10-14"]["Stop"][0], 1)
        self.assertEqual((A._oa_snap("nobody")[0], since), ({"t": {}, "s": {}, "c": {}, "h": {}}, int(T0)))


if __name__ == "__main__":
    unittest.main()
