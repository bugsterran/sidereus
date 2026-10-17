"""Attention-row lifetime note: server `until` on card signals only (sidereus/attention.py) and
web/js/17-attention.js attnLife wording for live vs after-the-fact signals."""
import json
import re
import subprocess
import time
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_all, js_fn
from tests.test_attention import Base, iso, sess
from tests._node import node_e


def life(sig, now, lang="ko"):
    aft = re.search(r"^const ATTN_AFTER[^\n]*$", js_all(), re.M).group(0)
    src = ("const LANG = %s;\n" % json.dumps(lang) + i18n_switch(("T",))
           + aft + "\n" + js_fn("hhmm") + "\n" + js_fn("CLK") + "\n" + js_fn("attnLife")
           + "\nconsole.log(JSON.stringify(attnLife(" + json.dumps(sig) + ", " + json.dumps(now) + ")));")
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def clock(ts):
    t = time.localtime(ts)
    return "%02d:%02d" % (t.tm_hour, t.tm_min)


def clock12(ts):
    t = time.localtime(ts)
    return "%d:%02d %s" % ((t.tm_hour % 12) or 12, t.tm_min, "PM" if t.tm_hour >= 12 else "AM")


class ServerUntil(Base):
    def test_until_only_on_card_signal(self):
        now = time.time()
        cards = [{"kind": "fcut", "cwd": "/w/p", "at": iso(now - 900)}, {"kind": "fcheck", "cwd": "/w/p", "at": iso(now - 300)}]
        row = self.one(sess("a", state="ask", age=1000, ctx=96, win=100), cards)
        by = {s["k"]: s for s in row["sigs"]}
        self.assertEqual(set(by), {"ask", "ctx95", "fail"})
        self.assertAlmostEqual(by["fail"]["until"], now - 300 + self.att_cap(), delta=2)   # newest card + 30 min
        self.assertNotIn("until", by["ask"])
        self.assertNotIn("until", by["ctx95"])

    def test_wreck_has_no_until(self):
        row = self.one(sess("a", wreck=1))
        self.assertEqual([(s["k"], "until" in s) for s in row["sigs"]], [("wreck", False)])

    def att_cap(self):
        from tests.test_attention import att
        return att.ATT_FAIL_CARD_S


class JsLife(unittest.TestCase):
    NOW = 1790000000

    def test_live_kinds(self):
        for k in ("blocked", "ask", "ctx95", "ctx85", "stall", "loop", "done", "bgdone"):
            self.assertEqual(life({"k": k, "since": self.NOW - 60}, self.NOW), "지금 상태 — 풀리면 사라짐")

    def test_fail_with_cap(self):
        s = self.NOW - 600
        out = life({"k": "fail", "since": s, "until": self.NOW + 1190}, self.NOW)
        self.assertEqual(out, clock(s) + " 발생 · 다시 일하면 사라짐 · 최대 20분 남음")
        self.assertTrue(life({"k": "fail", "since": s, "until": self.NOW - 5}, self.NOW).endswith("최대 1분 남음"))

    def test_wreck_no_cap(self):
        s = self.NOW - 120
        self.assertEqual(life({"k": "wreck", "since": s}, self.NOW), clock(s) + " 발생 · 다시 일하면 사라짐")

    def test_english(self):
        s = self.NOW - 60
        # en uses CLK (12h, like the KPI reset); ICU may put U+202F before AM/PM.
        self.assertEqual(life({"k": "fail", "since": s, "until": self.NOW + 60}, self.NOW, "en").replace("\u202f", " "),
                         "at " + clock12(s) + " · clears when work resumes · ≤1 min left")
        self.assertEqual(life({"k": "ask"}, self.NOW, "en"), "Live state — clears when resolved")


if __name__ == "__main__":
    unittest.main()
