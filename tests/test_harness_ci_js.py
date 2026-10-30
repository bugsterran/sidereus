"""Harness «After push (CI)» checkpoint (47b strip): R2 button + filter · R3 streak line · R4 CI incident cards."""
import json
import os
import re
import subprocess
import unittest

from tests._load import ROOT
from tests import test_harness_person_js as thp   # module import: its classes must not be collected twice
from tests import test_harness_js as thj


def _js(body):
    return thp._js(body)


def _data(ci=None, inc=()):
    rep = json.loads(json.dumps(thj.Harness._REPORT))
    if ci is not None:
        rep["checkpoints"]["ci"] = ci
    rep["incidents"] = rep["incidents"] + list(inc)
    return json.dumps({"report": rep, "guards": thj.Harness._GUARDS})


_CI = {"runs": 6, "caught": 2, "listed": 1, "streak": 3}
_INC = {"cp": "ci", "mode": "ci", "fail": {"ts": 1790003000, "head": "dddd4444aaaa", "rc": 1, "failed": None},
        "pass": {"ts": 1790003600, "head": "eeee5555bbbb\"><img onerror=1>"}, "commits": 1, "flipped": [], "still": [], "state": "held", "at": 0}


def _strip(h):
    return h.split("class=hnrepg", 1)[1].split("class=hnrepc>", 1)[0]


class Ci(unittest.TestCase):
    def test_no_runs_no_button_no_streak(self):
        for ci in (None, {"runs": 0, "caught": 0, "listed": 0, "streak": 0}):
            h = _js("console.log(JSON.stringify(hnReport(%s)))" % _data(ci))
            self.assertNotIn("data-hncp=ci", h)
            self.assertNotIn("CI 연속", h)
            self.assertNotIn("data-hncpc=ci", h)

    def test_button_counts_and_streak(self):
        h = _js("console.log(JSON.stringify(hnReport(%s)))" % _data(_CI, [_INC]))
        s = _strip(h)
        self.assertEqual(re.findall(r"data-hncp=(\w+)", s), ["hooks", "fast", "full", "ci"])
        self.assertIn("푸시 후 (CI)", s)
        self.assertIn("6", re.search(r'data-hncp=ci[^>]*title="([^"]*)"', s).group(1))   # run count in the tooltip
        self.assertIn("<i>잡음 2</i></button>", s)
        self.assertIn("<i class=hntm>유지: CI 연속 통과 3/5</i>", s)
        en = _js("LANG = 'en'; console.log(JSON.stringify(hnReport(%s)))" % _data(_CI, [_INC]))
        self.assertIn("caught 2", _strip(en))
        self.assertIn("Holding: CI streak 3/5", _strip(en))
        big = _js("console.log(JSON.stringify(hnReport(%s)))" % _data(dict(_CI, streak=9)))
        self.assertIn("5/5", _strip(big))

    def test_click_filters_ci_cards_escaped(self):
        d = _data(_CI, [_INC])
        click = "LST.click.forEach(f => f({target: {closest: s => s === '.hnw [data-hncp]' ? {dataset: {hncp: 'ci'}} : null}}));"
        r = _js(click + " console.log(JSON.stringify([HN.cp, hnReport(%s), URLS]))" % d)
        self.assertEqual(r[0], "ci")
        self.assertEqual(set(re.findall(r"data-hncpc=(\w+)", r[1])), {"ci"})
        self.assertEqual(r[1].count("hninc"), 1)   # R4: one red→green card
        self.assertIn("data-hncp=ci aria-pressed=true", r[1])
        self.assertIn("이전에 잡은 1건은 목록에 없음", r[1])   # caught 2 > listed 1
        self.assertNotIn("<img", r[1])
        self.assertEqual(r[2], [])

    def test_i18n_file_checks(self):
        subprocess.run(["node", "--check", os.path.join(ROOT, "web", "js", "06-i18n-zzc-ci.js")], check=True)


if __name__ == "__main__":
    unittest.main()
