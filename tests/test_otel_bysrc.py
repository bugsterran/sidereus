"""Unit tests for the per model|query_source split of OTel api_request (sidereus/otel.py `bySrc`).

Module state (`_otel`, `_otel_stat`, `_otel_req`, `_otel_sample`, `_usage_add`) is swapped per test;
no live server, file or network is used.
"""
import unittest

from tests import _load

o = _load.sidereus("otel")


def _rec(rid, model=None, src=None, inp=1, cr=10, cc=100, out=1000):
    at = {"event.name": "api_request", "session.id": "s1", "request_id": rid,
          "input_tokens": inp, "cache_read_tokens": cr, "cache_creation_tokens": cc, "output_tokens": out}
    if model is not None:
        at["model"] = model
    if src is not None:
        at["query_source"] = src
    attrs = [{"key": k, "value": ({"intValue": v} if isinstance(v, int) else {"stringValue": v})}
             for k, v in at.items()]
    return {"attributes": attrs}


def _payload(recs):
    return {"resourceLogs": [{"scopeLogs": [{"logRecords": recs}]}]}


class BySrcCase(unittest.TestCase):
    def setUp(self):
        self.saved = (o._otel, o._otel_stat, o._otel_req, o._otel_sample, o._usage_add, o.OTEL_SRC_CAP)
        o._otel, o._otel_req, o._otel_sample = {}, o.BoundedMemo(4000), {}
        o._otel_stat = {"posts": 0, "recs": 0, "kept": 0, "dropName": 0, "dropSeq": 0, "dropSid": 0,
                        "acct": 0, "dupReq": 0, "reSeq": 0, "names": {}, "lastPost": 0, "lastKept": 0}
        self.added = []
        o._usage_add = lambda ts, tok, cost, sid="": self.added.append(tok)

    def tearDown(self):
        (o._otel, o._otel_stat, o._otel_req, o._otel_sample, o._usage_add, o.OTEL_SRC_CAP) = self.saved

    def test_counts_match_usage_add_and_empty_source_is_dash(self):
        o._otel_ingest(_payload([_rec("r1", "opus", "main"), _rec("r2", "opus", "main"),
                                 _rec("r3", "haiku")]))
        bs = o._otel_stat["bySrc"]
        self.assertEqual(bs["opus|main"], [2, 2 * 1111])
        self.assertEqual(bs["haiku|-"], [1, 1111])
        self.assertEqual(sum(v[1] for v in bs.values()), sum(self.added))

    def test_duplicate_request_id_not_counted(self):
        o._otel_ingest(_payload([_rec("r1", "opus", "main"), _rec("r1", "opus", "main")]))
        self.assertEqual(o._otel_stat["bySrc"]["opus|main"][0], 1)
        self.assertEqual(o._otel_stat["dupReq"], 1)

    def test_key_cap_folds_into_other(self):
        o.OTEL_SRC_CAP = 2
        o._otel_ingest(_payload([_rec("r%d" % i, "m%d" % i, "s") for i in range(5)]
                                + [_rec("x", "m0", "s")]))
        bs = o._otel_stat["bySrc"]
        self.assertEqual(set(bs), {"m0|s", "m1|s", "other"})
        self.assertEqual(bs["other"][0], 3)
        self.assertEqual(bs["m0|s"][0], 2)     # an existing key keeps counting past the cap


if __name__ == "__main__":
    unittest.main()
