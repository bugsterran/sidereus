"""paintCfg() (web/js/90-settings.js) keeps the pane scroll: the late mailbox-watch section mounts before scrollTop is restored. Fake DOM."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run():
    """Returns [scrollTop after repaint, order of mount vs restore]."""
    src = ("const log = [];\n"
           "function mkPn(){ return {dataset: {cat: 'me'}, h: 1000, _t: 0, mounted: false,"
           " get scrollTop(){ return this._t; },"
           " set scrollTop(v){ log.push('restore'); this._t = Math.min(v, this.h - 400); }}; }\n"
           "let pn = mkPn(); pn.h = 1310; pn.mounted = true; pn._t = 900;\n"
           "const box = {querySelector: s => s === '.cfgpn' ? pn : null, set innerHTML(v){ pn = mkPn(); }};\n"
           "const document = {getElementById: id => id === 'cfgm' ? {hidden: false} : box};\n"
           "function mwMount(){ if(pn.mounted) return; log.push('mount'); pn.mounted = true; pn.h += 310; }\n"
           "const CFGCAT = 'me', vwLoad = () => [], T = s => s, esc = s => s;\n"
           "const cfgPaneDisp = () => '', cfgPaneAl = cfgPaneDisp, cfgPaneSv = cfgPaneDisp, cfgPaneTl = cfgPaneDisp,"
           " cfgPaneMe = cfgPaneDisp, cfgPaneVw = cfgPaneDisp, cfgShell = () => '', cfgBind = () => {};\n"
           + js_fn("paintCfg") + "\n"
           "paintCfg(); process.stdout.write(JSON.stringify([pn.scrollTop, log]));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class CfgScrollKeep(unittest.TestCase):
    def test_scroll_survives_repaint(self):
        top, log = run()
        self.assertEqual(top, 900)
        self.assertEqual(log, ["mount", "restore"])

    def test_strp_hover_beats_id_rule(self):
        css = open(os.path.join(os.path.dirname(__file__), "..", "web", "css", "85-palette-settings.css"), encoding="utf-8").read()
        self.assertIn("#cfgbox .mpli > .strp:not(:disabled):not(.on):hover{background:var(--seg-hv-bg)", css)


if __name__ == "__main__":
    unittest.main()
