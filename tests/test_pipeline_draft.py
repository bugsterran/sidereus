"""«AI 에게 초안 요청» progress strip (web/js/48e-pipeline-new.js): pure step logic + HTML, run under node."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUBS = ("var PL_DRAFT_TTL = 600000;\n"
         "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));\n"
         "function T(s){ return s; }\n")


def _js(expr):
    src = STUBS + "\n".join(js_fn(f) for f in ("plDraftSteps", "plDraftStrip", "plDraftRestore", "strShort")) \
        + "\nconsole.log(JSON.stringify(" + expr + "));"
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)


DR = {"id": "m1", "to": "s-abc", "proj": "/p/a", "cwd": "/p/a", "name": "bugfix", "at": 1000, "ok": True}


def _steps(dr, ack, data=None):
    s = _js("plDraftSteps(%s, %s, %s)" % (json.dumps(dr), json.dumps(ack), json.dumps(data or {})))
    return [s["sent"], s["got"], s["file"]]


class Steps(unittest.TestCase):
    def test_no_ack_step1_only(self):
        self.assertEqual(_steps(DR, {}), [True, False, False])

    def test_delivered_without_ack(self):
        self.assertEqual(_steps(dict(DR, ok=False), {"m1": {"delivered": ["s-abc"], "hooked": ["s-abc"]}}), [True, False, False])

    def test_ack_from_other_who(self):
        self.assertEqual(_steps(DR, {"m1": {"ack": [{"who": "s-zzz"}]}}), [True, False, False])

    def test_ack_from_to(self):
        self.assertEqual(_steps(DR, {"m1": {"ack": [{"who": "s-abc"}]}}), [True, True, False])

    def test_file_in_cwd_only_and_chip(self):
        dr = dict(DR, cwd="/p/b")
        data = {"/p/a": {"pipelines": []}, "/p/b": {"pipelines": [{"name": "bugfix"}]}}
        self.assertEqual(_steps(dr, {}, data), [True, False, True])
        h = _js("plDraftStrip(%s, {}, %s, '/p/a')" % (json.dumps(dr), json.dumps(data)))
        self.assertIn('data-pldro="/p/b"', h)
        self.assertIn('data-pldrp="/p/b"', h)
        self.assertNotIn("data-pldrp", _js("plDraftStrip(%s, {}, {}, '/p/a')" % json.dumps(DR)))

    def test_ack_note_never_rendered(self):
        ack = {"m1": {"ack": [{"who": "s-abc", "note": "SENTINEL_NOTE_BODY"}]}}
        h = _js("plDraftStrip(%s, %s, {}, '/p/a')" % (json.dumps(DR), json.dumps(ack)))
        self.assertNotIn("SENTINEL_NOTE_BODY", h)
        self.assertIn("class=on", h)

    def test_values_escaped(self):
        h = _js("plDraftStrip(%s, {}, {}, '/p/a')" % json.dumps(dict(DR, to="<b>x", cwd="/p/\"q")))
        self.assertNotIn("<b>x", h)
        self.assertNotIn('"q', h.replace("&quot;q", ""))


class Views(unittest.TestCase):
    """The strip renders through plNewForm, which every list view calls (suggestion view included)."""

    def _sug(self, plnew):
        stubs = ("Date.now = () => 1790000000000;\n"   # fixed clock
                 "var PLNEW = %s, PLSTD = false, ACK = {}, PLS = {proj: '/p/a', sugI: 0, data: {}, draft: Object.assign(%s, {at: 1790000000000})};\n"
                 "function plCanvas(){ return {html: '<canvas>'}; }\nfunction plNewBtn(){ return ''; }\n"
                 "function plStdList(){ return ''; }\nfunction plDraftForm(){ return ''; }\nfunction plImpPick(){ return ''; }\n"
                 "function plNewNameErr(){ return ''; }\nfunction plTplList(){ return []; }\nfunction diffHtml(){ return ''; }\n"
                 "function agLang(){ return ''; }\nfunction KE(k){ return k; }\n") % (plnew, json.dumps(DR))
        src = STUBS + stubs + "\n".join(js_fn(f) for f in ("plDraftSteps", "plDraftStrip", "strShort", "plNewForm", "plSugBody")) \
            + "\nconsole.log(JSON.stringify(plSugBody({suggest: [{title: 'x'}]})));"
        return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)

    def test_suggestion_view_shows_strip(self):
        self.assertIn("pldrs", self._sug("null"))

    def test_hidden_while_new_form_open(self):
        self.assertNotIn("pldrs", self._sug("{name: '', title: '', tpl: 'empty', diff: ''}"))


class Restore(unittest.TestCase):
    RAW = json.dumps({"id": "m1", "to": "s-abc", "proj": "/p/a", "cwd": "/p/a", "name": "bugfix", "at": 1000})

    def test_within_window(self):
        r = _js("plDraftRestore(%s, %d)" % (json.dumps(self.RAW), 1000 + 599999))
        self.assertEqual((r["id"], r["name"], r["ok"]), ("m1", "bugfix", True))

    def test_expires_after_10_min(self):
        self.assertIsNone(_js("plDraftRestore(%s, %d)" % (json.dumps(self.RAW), 1000 + 600000)))
        self.assertIsNone(_js("plDraftRestore('not json', 1000)"))
        self.assertIsNone(_js("plDraftRestore('', 1000)"))


if __name__ == "__main__":
    unittest.main()
