"""Row `cmpEta` «Compacts in ~N turns» (sidereus/compact_eta.py): fixture transcripts and settings in a tmp dir only."""
import json
import os
import shutil
import tempfile
import types
from collections import OrderedDict
import unittest

from tests._load import sidereus

ce = sidereus("compact_eta")
parse = sidereus("parse")
sessions = sidereus("sessions")
bu = sidereus("burn_scan")


def _asst(ctx, mid, side=False):
    return json.dumps({"type": "assistant", "isSidechain": side, "sessionId": "s1", "message": {
        "id": mid, "model": "claude-opus-5", "content": [{"type": "text", "text": "x"}],
        "usage": {"input_tokens": 10, "cache_read_input_tokens": ctx - 10, "cache_creation_input_tokens": 0}}})


FUTURE = 2 ** 40   # a recorded change after any fixture file was born
BOUNDARY = json.dumps({"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": "auto"}})


class CompactEtaTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.fp = os.path.join(self.d, "s1.jsonl")
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write("{}\n")
        self.stg = os.path.join(self.d, "settings.json")
        self.cw = os.path.join(self.d, "compact-win.json")
        self.acct = ("", "")
        for n, v in {"SETTINGS_FILE": self.stg, "CW_FILE": self.cw, "_SET_MEMO": {}, "_SERIES": OrderedDict(),
                     "claude_roots": types.SimpleNamespace(acct_of=lambda sid, fp: self.acct)}.items():
            self.patch(ce, n, v)
        self.settings({"autoCompactWindow": 450000})
        self.window(450000)

    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)

    def settings(self, d, path=None):
        with open(path or self.stg, "w", encoding="utf-8") as f:
            json.dump(d, f)
        ce._SET_MEMO.clear()

    def window(self, value, since=0, prev=None):
        with open(self.cw, "w", encoding="utf-8") as f:
            json.dump({"value": value, "since": since, "prev": prev, "approx": False}, f)
        ce._SET_MEMO.clear()

    def eta(self, ctxs, win=1_000_000, dead=False):
        return ce.row_eta(self.fp, {"sid": "s1", "ctx": ctxs[-1] if ctxs else 0, "ctxs": ctxs}, win, dead)

    def test_R1_n_from_median(self):
        # diffs 10k, 20k, 30k -> median 20k; (450k - 160k) / 20k = 14.5 -> 15
        self.assertEqual(self.eta([100000, 110000, 130000, 160000]),
                         {"cmpEta": {"n": 15, "pt": 450000, "grow": 20000, "k": 3}})

    def test_R1_dedups_message_id_and_skips_sidechain(self):
        rows = [_asst(100000, "m1"), _asst(100000, "m1"), _asst(120000, "m2"), _asst(900000, "sx", side=True),
                _asst(140000, "m3"), _asst(140000, "m3"), json.dumps({"type": "assistant", "message": {
                    "id": "z", "usage": {"input_tokens": 0}}}), _asst(160000, "m4")]
        self.assertEqual(ce.ctx_turns(rows), [100000, 120000, 140000, 160000])

    def test_R1_keeps_newest_points_only(self):
        rows = [_asst(100000 + i * 1000, "m%d" % i) for i in range(30)]
        got = ce.ctx_turns(rows)
        self.assertEqual(len(got), ce.ETA_KEEP)
        self.assertEqual(got[-1], 129000)

    def test_R1_window_is_min_of_model_and_session_setting(self):
        ctxs = [100000, 110000, 120000, 130000]
        self.assertEqual(self.eta(ctxs, win=200000)["cmpEta"]["pt"], 200000)      # model window smaller
        self.assertEqual(self.eta(ctxs, win=1000000)["cmpEta"]["pt"], 450000)     # session setting smaller
        # born before the last recorded change: the previous value is in effect for this session
        self.window(450000, since=FUTURE, prev=300000)
        self.assertEqual(self.eta(ctxs)["cmpEta"]["pt"], 300000)
        # extra account: that account's own settings.json
        other = os.path.join(self.d, "acct2")
        os.mkdir(other)
        self.settings({"autoCompactWindow": 250000}, os.path.join(other, "settings.json"))
        self.acct = ("work", other)
        self.assertEqual(self.eta(ctxs)["cmpEta"]["pt"], 250000)

    def test_R2_disabled_setting(self):
        self.settings({"autoCompactWindow": 450000, "autoCompactEnabled": False})
        self.assertEqual(self.eta([100000, 110000, 120000, 130000]), {})

    def test_R2_env_disable(self):
        for k in ("DISABLE_AUTO_COMPACT", "DISABLE_COMPACT", "DISABLE_AUTOCOMPACT"):
            self.settings({"env": {k: "1"}})
            self.assertEqual(self.eta([100000, 110000, 120000, 130000]), {}, k)
        self.settings({"env": {"DISABLE_AUTO_COMPACT": "0"}})
        self.assertIn("cmpEta", self.eta([100000, 110000, 120000, 130000]))

    def test_R2_fewer_than_3(self):
        self.assertEqual(self.eta([100000, 110000, 120000]), {})
        self.assertEqual(self.eta([]), {})

    def test_R2_median_nonpositive(self):
        self.assertEqual(self.eta([100000, 110000, 105000, 100000]), {})
        self.assertEqual(self.eta([100000, 100000, 100000, 100000]), {})

    def test_R2_window_unknown(self):
        ctxs = [100000, 110000, 120000, 130000]
        self.assertEqual(self.eta(ctxs, win=0), {})                        # model window unknown
        os.remove(self.cw)
        ce._SET_MEMO.clear()
        self.assertEqual(self.eta(ctxs), {})                               # no compact-win.json yet
        self.window(450000, since=FUTURE, prev=None)
        self.assertEqual(self.eta(ctxs), {})                               # born before an unrecorded change
        with open(self.stg, "w", encoding="utf-8") as f:
            f.write("{half")
        ce._SET_MEMO.clear()
        self.window(450000)
        self.assertEqual(self.eta(ctxs), {})                               # mid-write settings: unknown, not default

    def test_R2_dead_row(self):
        self.assertEqual(self.eta([100000, 110000, 120000, 130000], dead=True), {})

    def test_R2_past_compaction_point(self):
        self.assertEqual(self.eta([420000, 440000, 460000, 480000]), {})

    def test_R4_cut_at_compact_boundary(self):
        rows = [_asst(300000, "a"), _asst(320000, "b"), _asst(340000, "c"), BOUNDARY,
                _asst(50000, "d"), _asst(60000, "e"), _asst(70000, "f")]
        self.assertEqual(ce.ctx_turns(rows), [50000, 60000, 70000])
        self.assertEqual(self.eta(ce.ctx_turns(rows)), {})                 # 2 diffs after the compaction

    def write(self, lines, mode="a"):
        with open(self.fp, mode, encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def test_R1_series_survives_a_tail_with_few_responses(self):
        first = [_asst(100000 + i * 10000, "m%d" % i) for i in range(10)]
        self.write(first, "w")
        self.assertEqual(len(ce.ctx_turns(first, self.fp)), 10)
        # big tool-result lines push older responses out of the parse tail: only 2 new responses left in it
        big = json.dumps({"type": "user", "message": {"content": "x" * 1000}})
        newer = [_asst(200000, "m10"), big, big, _asst(210000, "m11")]
        self.write(newer)
        got = ce.ctx_turns(newer, self.fp)
        self.assertEqual(got, [100000 + i * 10000 for i in range(1, 10)] + [200000, 210000])
        eta = self.eta(got)["cmpEta"]
        self.assertGreaterEqual(eta["k"], 10)
        self.assertEqual((eta["grow"], eta["n"]), (10000, 24))   # (450k - 210k) / 10k
        # a tail with no response at all keeps the series
        self.write([big])
        self.assertEqual(ce.ctx_turns([big], self.fp), got)
        # without a path the tail alone is used (no memo)
        self.assertEqual(ce.ctx_turns(newer), [200000, 210000])

    def test_R4_cut_in_later_tail_resets_the_kept_series(self):
        first = [_asst(300000 + i * 10000, "m%d" % i) for i in range(8)]
        self.write(first, "w")
        ce.ctx_turns(first, self.fp)
        later = [_asst(380000, "m8"), BOUNDARY, _asst(50000, "n1"), _asst(60000, "n2")]
        self.write(later)
        self.assertEqual(ce.ctx_turns(later, self.fp), [50000, 60000])
        self.assertEqual(ce.ctx_turns([_asst(70000, "n3")], self.fp), [50000, 60000, 70000])
        # unmarked compaction in the gap between the kept series and the tail: cut at the drop too
        ce._SERIES.clear()
        ce.ctx_turns(first, self.fp)
        self.write(["{}"])
        self.assertEqual(ce.ctx_turns([_asst(60000, "z1"), _asst(70000, "z2")], self.fp), [60000, 70000])

    def test_R4_replaced_file_resets(self):
        first = [_asst(100000 + i * 10000, "m%d" % i) for i in range(10)]
        self.write(first, "w")
        ce.ctx_turns(first, self.fp)
        tail = [_asst(300000, "q1"), _asst(310000, "q2")]
        self.write(tail[:1], "w")                                          # truncated / rewritten: smaller
        self.assertEqual(ce.ctx_turns(tail, self.fp), [300000, 310000])
        ce.ctx_turns(first, self.fp)
        new = self.fp + ".new"                                             # replaced: other inode, larger
        with open(new, "w", encoding="utf-8") as f:
            f.write("\n".join(first + first) + "\n")
        os.replace(new, self.fp)
        self.assertNotEqual(ce._SERIES[self.fp][0], os.stat(self.fp).st_ino)
        self.assertEqual(ce.ctx_turns(tail, self.fp), [300000, 310000])

    def test_R4_cut_at_large_drop(self):
        rows = [_asst(300000, "a"), _asst(320000, "b"), _asst(340000, "c"),
                _asst(60000, "d"), _asst(70000, "e"), _asst(80000, "f"), _asst(90000, "g")]
        self.assertEqual(ce.ctx_turns(rows), [60000, 70000, 80000, 90000])
        # a small drop (> 70% of the older value) is kept as a negative diff
        rows = [_asst(100000, "a"), _asst(90000, "b"), _asst(120000, "c")]
        self.assertEqual(ce.ctx_turns(rows), [100000, 90000, 120000])

    def test_R5_session_row_has_cmpEta_from_fixture(self):
        cwd = "/w/repo-e"
        lines = [_asst(100000 + i * 20000, "m%d" % i) for i in range(6)]
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.patch(parse, "_running_bg", lambda fp: ([], [], []))
        self.patch(parse, "_cwd_from_slug", lambda s: cwd)
        self.patch(parse, "_human_deep", lambda fp: 0)
        p = parse._parse_transcript(self.fp)
        self.assertEqual(p["ctxs"], [100000, 120000, 140000, 160000, 180000, 200000])
        for n, v in {"_ctx_window": lambda *a: (1000000, "obs"), "_otel_state": lambda sid: None,
                     "_bg_show": lambda *a: [], "_mon_rows": lambda *a: [], "_bg_age": lambda *a: 0,
                     "session_repos": lambda *a: [], "_wt_of": lambda *a: None, "mbox_of": lambda *a: ("", ""),
                     "_projcost_of": lambda *a: 0.0, "_git_state": lambda *a: "", "_model_win": lambda *a: (0, 0),
                     "_dead": lambda *a: False, "_row_acct": lambda *a: {}, "compacting": lambda *a: None,
                     "perm_wait": lambda *a: None, "plm_of": lambda *a: None}.items():
            self.patch(sessions, n, v)
        self.patch(sessions.pl_runs, "PLR_DIR", self.d)   # no live plmark/ reads
        now = os.path.getmtime(self.fp) + 5    # file time, not the clock
        row = sessions._session_row(self.fp, now - 5, now, {cwd: 1}, p)
        # (450k - 200k) / 20k = 12.5 -> 13
        self.assertEqual(row["cmpEta"], {"n": 13, "pt": 450000, "grow": 20000, "k": 5})

    def test_R5_burn_compact_setting_unchanged(self):
        self.patch(bu, "CLAUDE_SETTINGS", self.stg)
        for d, want in (({"autoCompactWindow": 300000}, 300000), ({}, ce.COMPACT_DEFAULT),
                        ({"autoCompactWindow": "abc"}, ce.COMPACT_DEFAULT), ({"autoCompactWindow": 5}, ce.COMPACT_DEFAULT),
                        ({"autoCompactWindow": 300000, "env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200000"}}, 200000),
                        ({"env": {"DISABLE_AUTOCOMPACT": "1"}}, ce.COMPACT_DEFAULT), ({"env": None}, ce.COMPACT_DEFAULT),
                        ({"autoCompactWindow": 300000, "autoCompactEnabled": False}, 300000), ([1], ce.COMPACT_DEFAULT)):
            self.settings(d)
            self.assertEqual(bu._compact_setting()[0], want, d)
        self.assertIs(bu.COMPACT_DEFAULT, ce.COMPACT_DEFAULT)
        self.assertIs(bu._sess_win, ce.sess_win)


if __name__ == "__main__":
    unittest.main()
