"""Leading pipeline tags ([pl:…] · [pl-skip:…] · [pl-model:…]) are stripped from displayed agent labels only
(web/js/00-core.js plStrip); the raw label the pipeline matcher reads (48b plDescStage) keeps the tag."""
import json
import os
import re
import shutil
import subprocess
import unittest
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name):
    return open(os.path.join(ROOT, "web", "js", name), encoding="utf-8").read()


def _fn(s, n):
    return re.search(r"^function " + n + r"\(.*?^}", s, re.S | re.M).group(0)


def run(cases):
    core, sl, run_ = _src("00-core.js"), _src("40b-sessions-list.js"), _src("48b-pipeline-run.js")
    js = "\n".join([
        re.search(r"^function plStrip\(.*$", core, re.M).group(0),
        re.search(r"^const SUB_PLAIN_TY = .*$", sl, re.M).group(0), _fn(sl, "subLab"),
        re.search(r"^function plTk\(.*$", _src("48c-pipeline-graph.js"), re.M).group(0),
        re.search(r"^const PL_DESC_RE = .*$", run_, re.M).group(0), _fn(run_, "plDescStage"),
        "const C = " + json.dumps(cases) + ";",
        "console.log(JSON.stringify(C.map(c => [plStrip(c), subLab(c).desc, plDescStage(c)])));"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlTagStrip(unittest.TestCase):
    def test_strip_display(self):
        r = run(["[pl:-] ADR 0011 3단계", "general-purpose: [pl:sidereus-change/구현] 슬라이스 A",
                 "[pl-skip:x/리뷰] 불필요", "[pl-model:x/y=opus] go", "Explore: plain desc",
                 "note [pl:-] mid-text stays", None])
        self.assertEqual([x[0] for x in r], ["ADR 0011 3단계", "general-purpose: 슬라이스 A", "불필요", "go",
                                             "Explore: plain desc", "note [pl:-] mid-text stays", None])
        self.assertEqual(r[1][1], "슬라이스 A")     # session-list row text (subLab)
        self.assertEqual(r[0][1], "ADR 0011 3단계")

    def test_raw_tag_still_matches(self):
        # ⚠The matcher reads the raw label, so stripping for display must not have changed what it sees.
        r = run(["general-purpose: [pl:sidereus-change/구현] 슬라이스 A"])
        self.assertEqual(r[0][2], {"name": "sidereus-change", "title": "구현"})

    def test_display_sites(self):
        # Session task line (40b), pipeline label parts (48b) and worktree sub rows (89) strip any leading tag.
        core, sl, run_ = _src("00-core.js"), _src("40b-sessions-list.js"), _src("48b-pipeline-run.js")
        js = "\n".join([
            "const NL = '\\n'; function T(s){ return s; }",
            re.search(r"^const esc = .*?\n.*$", core, re.M).group(0),
            re.search(r"^function plStrip\(.*$", core, re.M).group(0), _fn(sl, "sessTaskHtml"),
            re.search(r"^const PL_DESC_RE = .*$", run_, re.M).group(0), _fn(run_, "plLabParts"),
            "console.log(JSON.stringify([sessTaskHtml({state: 'tool', targ: '[pl:-] ADR 3단계'}),"
            " ['general-purpose: [pl:-] a', 'x: [pl-skip:n/s] b', 'y: [pl:n/s] c', '[pl-model:n/s=opus] d'].map(l => plLabParts(l).desc)]));"])
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        task, descs = json.loads(r.stdout)
        self.assertNotIn("[pl:", task)
        self.assertIn(">ADR 3단계</div>", task)
        self.assertEqual(descs, ["a", "b", "c", "d"])
        self.assertIn("plStrip(String(v.lab))", _src("89-branch-worktree.js"))


if __name__ == "__main__":
    unittest.main()


class AlarmCardText(unittest.TestCase):
    def test_card_text_strips_tag(self):
        core, al = _src("00-core.js"), _src("15-alarms.js")
        js = "\n".join([re.search(r"^function plStrip\(.*$", core, re.M).group(0),
                        re.search(r"^function cardText\(.*$", al, re.M).group(0),
                        "console.log(JSON.stringify([cardText({text: ' general-purpose: [pl:-] do x '}), cardText({text: '[pl:p/구현] y'}), cardText({})]))"])
        out = json.loads(subprocess.run(node_e(js), stdout=subprocess.PIPE, timeout=20).stdout)
        self.assertEqual(out, ["general-purpose: do x", "y", ""])
