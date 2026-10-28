"""Pipeline request records on the structure «Architecture» view (web/js/84l2-structure-arch-req.js): row per state with the
receiving session (R1, R2), stage title escaped and never translated, «Stop» only while running, stop preview + confirm payload (R3)."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

FNS = ["archReqMs", "archReqRows", "archReqLive", "archReqLast", "archReqStopOk", "archReqBusy", "archStopBody", "archReqWho",
       "archReqRowHtml", "archReqStopHtml", "archReqSlot", "archReqSig", "archSecRunHtml", "archSecRunSig"]
_SRC_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js", "84l2-structure-arch-req.js")
with open(_SRC_P, encoding="utf-8") as fh:
    _SRC = fh.read()
SEND = re.search(r"^async function archStopSend\(.*?^}", _SRC, re.S | re.M).group(0)
CONSTS = "\n".join(re.findall(r"^const ARCH_REQ_(?:KEEP_MS|LBL) = .*$", _SRC, re.M))
PRE = "\n".join([
    "let LANG = 'ko';", i18n_prelude("LANG", ("T", "KE", "U", "TV")), "function sid8(s){ return String(s).slice(0, 8); }",
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
    "const ARCH_PL = 'arch-map', ARCH_SEC_PL = 'security-checks'; const ARCH = { msg: '', pstop: null };",
    "let SECRUN = {}; function archRunOf(p, pl){ const r = pl === ARCH_SEC_PL && SECRUN[p]; return r && r.stage ? r : null; }",
    "function archRunHtml(r, now, pl){ return '<RUN ' + pl + ' ' + esc(r.stage) + '>'; }",
    "let PLREQ = {}, POSTS = [], PAINTS = 0; function paintStruct(){ PAINTS++; }",
    "async function postJSON(u, b){ POSTS.push([u, b]); return { ok: true }; }",
    CONSTS,
])
NOW = 1700000000
ROW = {"id": "m-1", "pipeline": "arch-map", "sid": "abcdef1234567", "to": "box-a", "project": "repo", "state": "run",
       "stage": "<b>모듈</b>", "at": NOW - 60}


def run(body, lang="ko"):
    pre = PRE if lang == "ko" else PRE.replace("let LANG = 'ko';", "let LANG = 'en';", 1)
    js = pre + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + SEND + "\n(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def rows(**kw):
    r = dict(ROW)
    r.update(kw)
    return r


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructArchReq(unittest.TestCase):
    def test_row_labels_per_state(self):   # R1, R2
        st = ["sent", "run", "stopping", "stopped", "done", "gone"]
        r = run("console.log(JSON.stringify(" + json.dumps(st) + ".map(s => archReqRowHtml(Object.assign(" + json.dumps(ROW) + ", {state: s})))));", lang="en")
        for h in r:
            self.assertIn("repo · abcdef12 · box-a", h)   # receiving session: project · sid8 · mailbox id
        self.assertIn("Sent", r[0])
        self.assertIn("Running · &lt;b&gt;모듈&lt;/b&gt;", r[1])
        self.assertIn("Stopping", r[2])
        self.assertIn("Stopped", r[3])
        self.assertIn("Done", r[4])
        self.assertIn("No session", r[5])
        self.assertTrue(all(" end" in h for h in r[3:]))
        ko = run("console.log(JSON.stringify(archReqRowHtml(" + json.dumps(ROW) + ")));")
        self.assertIn("실행 중 · &lt;b&gt;모듈&lt;/b&gt;", ko)   # stage title raw + escaped, never through T()
        self.assertNotIn("<b>", ko)

    def test_stop_only_for_run_and_stopping(self):   # R3
        st = ["sent", "run", "stopping", "stopped", "done", "gone"]
        r = run("console.log(JSON.stringify(" + json.dumps(st) + ".map(s => archReqRowHtml(Object.assign(" + json.dumps(ROW) + ", {state: s})))));")
        self.assertEqual(["data-arstop=" in h for h in r], [False, True, True, False, False, False])

    def test_slot_replaces_transient_line(self):   # R1
        PL = {"/r": [rows(state="sent"), rows(id="m-0", at=NOW - 9000, state="done")]}
        r = run("PLREQ = " + json.dumps(PL) + "; const now = " + str(NOW * 1000) + ";"
                "const a = archReqSlot('/r', 'arch-map', '<TRANS>', '', now), b = archReqSlot('/r', 'other-pipeline', '<TRANS>', '', now);"
                "PLREQ = {'/r': [Object.assign(" + json.dumps(ROW) + ", {state: 'done'})]};"
                "const c = archReqSlot('/r', 'arch-map', '<TRANS>', '', now), e = archReqSlot('/r', 'arch-map', '<TRANS>', '', now + 7200000);"
                "console.log(JSON.stringify([a, b, c, e, archReqBusy('/r', 'arch-map')]));")
        self.assertIn("archpr", r[0])
        self.assertNotIn("<TRANS>", r[0])     # live row replaces «Requested» / «Analysis requested»
        self.assertEqual(r[1], "<TRANS>")     # no record for that pipeline
        self.assertIn("<TRANS>", r[2])        # finished row sits above the normal slot
        self.assertEqual(r[3], "<TRANS>")     # finished row expires
        self.assertFalse(r[4])

    def test_stop_preview_and_payload(self):   # R3
        r = run("PLREQ = {'/r': [" + json.dumps(ROW) + "]}; const n0 = await archStopSend();"
                "ARCH.pstop = {p: '/r', id: 'm-1', busy: false}; const h = archReqSlot('/r', 'arch-map', '', '', 0);"
                "const n1 = POSTS.length; await archStopSend();"
                "console.log(JSON.stringify([n0, n1, h, POSTS, ARCH.pstop]));", lang="en")
        self.assertEqual([r[0], r[1]], [False, 0])   # nothing without the confirm on an open preview
        self.assertIn("data-arstopgo", r[2])
        self.assertNotIn("data-arstop=", r[2])
        self.assertIn("Stop pipeline arch-map for /r (request m-1)", r[2])
        self.assertEqual(len(r[3]), 1)
        u, b = r[3][0]
        self.assertEqual(u, "/api/dm")
        self.assertEqual([b["to"], b["sid"], b["relay"], b["thread"]], ["box-a", "abcdef1234567", True, "pipeline:arch-map"])
        self.assertEqual(b["plreq"], {"kind": "stop", "pipeline": "arch-map", "repo": "/r", "of": "m-1"})
        self.assertIsNone(r[4])

    def test_stop_body_metadata_only(self):   # R3
        r = run("console.log(JSON.stringify(archStopBody('arch-map', '/r', 'm-9')))")
        self.assertEqual(r, "Stop pipeline arch-map for /r (request m-9): let the running stage agent finish, dispatch no further stages, report and end.")
        self.assertNotIn("«", r)   # no request text quoted

    def test_stop_refused_when_not_running(self):   # R3
        r = run("PLREQ = {'/r': [Object.assign(" + json.dumps(ROW) + ", {state: 'sent'})]}; ARCH.pstop = {p: '/r', id: 'm-1', busy: false};"
                "console.log(JSON.stringify([await archStopSend(), POSTS.length]));")
        self.assertEqual(r, [False, 0])

    def test_security_run_banner(self):   # live security record: row + «Stop»; stage falls back to the server run, then «Security check»
        SR = rows(id="s-1", pipeline="security-checks", stage="")
        r = run("const now = " + str(NOW * 1000) + "; const out = [archSecRunHtml('/r', now)];"
                "PLREQ = {'/r': [" + json.dumps(SR) + "]}; out.push(archSecRunHtml('/r', now));"
                "SECRUN = {'/r': {stage: '<i>scan</i>', sid: 'x', t0: 1}}; out.push(archSecRunHtml('/r', now));"
                "PLREQ = {'/r': [Object.assign(" + json.dumps(SR) + ", {state: 'done'})]}; out.push(archSecRunHtml('/r', now));"
                "SECRUN = {}; out.push(archSecRunHtml('/r', now));"
                "PLREQ = {'/r': [" + json.dumps(ROW) + "]}; out.push(archSecRunHtml('/r', now));"
                "console.log(JSON.stringify(out));", lang="en")
        self.assertEqual(r[0], "")
        self.assertIn('class="archck archsecrun"', r[1])
        self.assertIn("Running · Security check", r[1])
        self.assertIn('data-arstop="s-1"', r[1])
        self.assertIn("repo · abcdef12 · box-a", r[1])
        self.assertIn("Running · &lt;i&gt;scan&lt;/i&gt;", r[2])   # server run stage, escaped, not translated
        self.assertIn("<RUN security-checks &lt;i&gt;scan&lt;/i&gt;>", r[3])   # finished record: server run line, no «Stop»
        self.assertNotIn("data-arstop", r[3])
        self.assertEqual(r[4:], ["", ""])   # finished record only / arch-map record: no banner

    def test_security_banner_stop_preview_and_sig(self):   # same stop preview + payload path as arch-map
        SR = rows(id="s-1", pipeline="security-checks")
        r = run("PLREQ = {'/r': [" + json.dumps(SR) + "]}; const s0 = archReqSig('/r'); ARCH.pstop = {p: '/r', id: 's-1', busy: false};"
                "const h = archSecRunHtml('/r', 0); await archStopSend();"
                "const s1 = archReqSig('/r'); PLREQ = {'/r': [Object.assign(" + json.dumps(SR) + ", {stage: 'review'})]};"
                "console.log(JSON.stringify([h, POSTS, s0 === s1, s1 === archReqSig('/r')]));", lang="en")
        self.assertIn("Stop pipeline security-checks for /r (request s-1)", r[0])
        self.assertNotIn("data-arstop=", r[0])
        self.assertEqual(r[1][0][1]["plreq"], {"kind": "stop", "pipeline": "security-checks", "repo": "/r", "of": "s-1"})
        self.assertEqual(r[1][0][1]["thread"], "pipeline:security-checks")
        self.assertTrue(r[2])     # stop sent: pstop cleared again, same record
        self.assertFalse(r[3])    # a security stage change changes the arch paint sig (repaint)


if __name__ == "__main__":
    unittest.main()
