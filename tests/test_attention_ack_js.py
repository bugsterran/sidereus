"""web/js/17-attention.js attnRows: click-dismiss survives server `since` jitter, any badge signal
makes a badge row, and rows with an empty sid keep independent ack slots."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

FNS = ("attnPolOf", "attnWhy", "attnAckLoad", "attnAckSave", "attnRowId", "attnAckKey", "attnAckParse",
       "attnAckHit", "attnSnzLoad", "attnSnzSave", "attnRows")


def run(rows, ack, polls=1):
    """-> [{shown:[ids], quiet, badges, ack}] per poll; `rows` is a list per poll or one list reused."""
    src = js_all()
    consts = "\n".join(re.search(r"^const " + n + r"\b.*?;$", src, re.M | re.S).group(0)
                       for n in ("ATTN_APOL", "ATTN_LIST_ONLY", "ATTN_ACK_TOL"))
    per = rows if isinstance(rows[0], list) else [rows] * polls
    js = ("const LS = {mbAttnAck: %s}; const LANG = 'ko'; function T(s){ return s; }\n"
          "function lsJson(k, d){ return k in LS ? JSON.parse(JSON.stringify(LS[k])) : d; }\n"
          "function lsSetJson(k, v){ LS[k] = JSON.parse(JSON.stringify(v)); }\n"
          "function apolOf(k){ return {ask:'badge', abort:'badge', fcheck:'badge', agent:'list', bgdone:'list'}[k] || 'badge'; }\n"
          "let ATTN = null;\n" % json.dumps(ack, ensure_ascii=False)
          + consts + "\n" + "\n".join(js_fn(n) for n in FNS)
          + "\nconst out = []; for(const rs of %s){ ATTN = {rows: rs}; const a = attnRows();"
            " out.push({shown: a.shown.map(x => x.id), quiet: a.quiet, badges: a.shown.filter(x => x.badge).length,"
            " keys: a.shown.map(x => x.key), ack: LS.mbAttnAck}); }"
            " console.log(JSON.stringify(out));" % json.dumps(per, ensure_ascii=False))
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True).stdout)


def row(sid, *sigs, cwd="/w/p"):
    return {"sid": sid, "cwd": cwd, "sigs": [dict(k=k, pts=p, since=t) for k, p, t in sigs]}


class AckJitter(unittest.TestCase):
    def test_since_jitter_stays_dismissed(self):
        ack = {"s1": {"s": "ask", "t": 1000}}
        for t in (999, 1000, 1001, 1002):
            self.assertEqual(run([row("s1", ("ask", 80, t))], ack)[0]["shown"], [], t)

    def test_new_episode_or_signal_returns(self):
        ack = {"s1": {"s": "ask", "t": 1000}}
        self.assertEqual(run([row("s1", ("ask", 80, 1600))], ack)[0]["shown"], ["s1"])
        out = run([row("s1", ("ask", 80, 1000), ("abort", 70, 1000))], ack)[0]
        self.assertEqual(out["shown"], ["s1"])
        self.assertEqual(out["ack"], {})   # changed signal set prunes the ack

    def test_legacy_string_ack_migrates(self):
        out = run([row("s1", ("ask", 80, 1001))], {"s1": "s1|ask|1000"})[0]
        self.assertEqual(out["shown"], [])
        self.assertEqual(out["ack"], {"s1": {"s": "ask", "t": 1000}})

    def test_ack_kept_across_polls(self):
        polls = [[row("s1", ("ask", 80, t))] for t in (1000, 1001, 999, 1001)]
        self.assertTrue(all(p["shown"] == [] for p in run(polls, {"s1": {"s": "ask", "t": 1000}})))


class BadgeAny(unittest.TestCase):
    def test_stall_plus_toolfail_counts(self):
        out = run([row("s1", ("stall", 55, 1000), ("toolfail", 45, 1000))], {})[0]
        self.assertEqual((out["shown"], out["badges"], out["quiet"]), (["s1"], 1, 0))

    def test_only_list_signals_stay_low(self):
        out = run([row("s1", ("stall", 55, 1000), ("done", 10, 1000))], {})[0]
        self.assertEqual((out["shown"], out["quiet"]), ([], 1))


class EmptySid(unittest.TestCase):
    def test_independent_rows(self):
        rs = [row("", ("ask", 80, 1000), cwd="/w/a"), row("", ("ask", 80, 1000), cwd="/w/b")]
        out = run(rs, {"cwd:/w/a": {"s": "ask", "t": 1000}})[0]
        self.assertEqual(out["shown"], ["cwd:/w/b"])


if __name__ == "__main__":
    unittest.main()
