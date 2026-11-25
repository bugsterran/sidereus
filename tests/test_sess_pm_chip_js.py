"""Session row «No prompts» chip (40ba sessPmChip, R1 · R3): only for a no-prompt permission mode on a Claude Code row,
the mode escaped and never translated; the JS mode list equals live_probe._NO_PROMPT_MODES. Pure functions under node."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn, sidereus
from tests.test_saver_quota_js import jconst
from tests._node import node_e

LP = sidereus("live_probe")
PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s === 'No prompts' ? '[T]' + s : s;
const TV = o => o.msg.replace(/\{(\w+)\}/g, (_, k) => o.vars[k]);
"""


def chips(rows):
    code = PRE + jconst("SESS_NOPROMPT") + "\n" + js_fn("sessPmChip") + "\nconsole.log(JSON.stringify(%s.map(sessPmChip)));" % json.dumps(rows)
    r = subprocess.run(node_e(code), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Chip(unittest.TestCase):
    def test_no_prompt_modes_only(self):
        on = chips([{"pmode": m, "plat": "cc"} for m in ("bypassPermissions", "auto", "dontAsk")] + [{"pmode": "auto"}])
        for h, m in zip(on, ("bypassPermissions", "auto", "dontAsk", "auto")):
            self.assertIn("class=spm", h)
            self.assertIn(">[T]No prompts</span>", h)
            self.assertIn("Permission mode " + m + " —", h)
        off = chips([{"pmode": m} for m in ("default", "", "acceptEdits", "plan")] + [{}]
                    + [{"pmode": "bypassPermissions", "plat": p} for p in ("codex", "pi", "gemini")])
        self.assertEqual(off, [""] * len(off))

    def test_never_a_dropped_class(self):
        h, = chips([{"pmode": "dontAsk"}])
        cls = re.search(r"class=(\S+)", h).group(1)
        self.assertNotIn(cls, ("sz", "sk", "sm"))

    def test_mode_escaped_not_translated(self):
        # the mode is allow-listed, but the tooltip path still goes through esc() with the value as a TV var
        src = js_fn("sessPmChip")
        self.assertIn("vars: {m: x.pmode}", src)
        self.assertNotIn("T(x.pmode", src)

    def test_js_list_equals_live_probe(self):
        js = json.loads(jconst("SESS_NOPROMPT").split("=", 1)[1].strip().rstrip(";").replace("'", '"'))
        self.assertEqual(set(js), set(LP._NO_PROMPT_MODES))
        self.assertEqual(len(js), len(set(js)))


if __name__ == "__main__":
    unittest.main()
