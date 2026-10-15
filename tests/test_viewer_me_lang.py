"""Default viewer id follows the UI language (X-Sidereus-Lang from postJSON); an explicit viewer_me is never changed;
both default spellings count as mine so a language switch keeps earlier posts mine."""
import http.client
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._i18n_js import i18n_switch
from tests._load import sidereus
from tests.test_routes_post import HOST, _Rfile, cs
from tests.test_state_first_load import StateWiring
from tests._node import node_e

cfg = sidereus("config")
RP = sidereus("routes_post")
RA = sidereus("room_admin")
st = sidereus("state")


def say(body, lang=None):
    raw = json.dumps(body).encode("utf-8")
    hdr = "Host: %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\n" % (HOST, len(raw))
    if lang is not None:
        hdr += "X-Sidereus-Lang: %s\r\n" % lang
    h = cs.Handler.__new__(cs.Handler)
    h.headers = http.client.parse_headers(io.BytesIO((hdr + "\r\n").encode("latin-1")))
    h.rfile, h.wfile = _Rfile(raw), io.BytesIO()
    h.path, h.command, h.request_version = "/api/say", "POST", "HTTP/1.1"
    h.requestline = "POST /api/say HTTP/1.1"
    h.close_connection = False
    h.client_address = ("127.0.0.1", 0)
    h.do_POST()
    return int(h.wfile.getvalue().split(b"\r\n", 1)[0].split()[1])


class PureRules(unittest.TestCase):
    def test_default_by_lang(self):
        for me in ("사용자", "user"):
            self.assertEqual(cfg.viewer_me_for(me, "en"), "user")
            self.assertEqual(cfg.viewer_me_for(me, "ko"), "사용자")
            self.assertEqual(cfg.viewer_me_for(me, ""), "사용자")      # no header = ko (old behaviour)
            self.assertEqual(cfg.viewer_me_for(me, "fr"), "사용자")

    def test_explicit_untouched(self):
        self.assertEqual(cfg.viewer_me_for("나", "en"), "나")
        self.assertEqual(cfg.viewer_me_for("alice", "ko"), "alice")
        self.assertEqual(cfg.viewer_ids("alice"), ["alice"])

    def test_both_spellings_when_default(self):
        self.assertEqual(cfg.viewer_ids("사용자"), ["사용자", "user"])
        self.assertEqual(cfg.viewer_ids("user"), ["사용자", "user"])


class DmTarget(unittest.TestCase):
    def test_both_default_spellings_are_the_viewer(self):
        bus = sidereus("bus")
        with mock.patch.object(bus, "_load", lambda n, d: {"s1": "alice", "s2": "user"}):
            for to in ("사용자", "user"):
                self.assertEqual(bus.dm_target_error(to, "사용자"), "Sender and recipient are the same", to)
            self.assertIsNone(bus.dm_target_error("alice", "사용자"))
            self.assertIsNone(bus.dm_target_error("user", "나"))      # explicit name: «user» is just another session


class SayAuthor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-vme-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.busf = os.path.join(self.tmp, "bus.jsonl")
        for obj, k, v in ((RP, "BUS_PATH", self.busf), (RP, "ROOM_DEFAULT", "home"),
                          (RA, "_room_known", lambda r: r == "r1"),
                          (RA, "ADMIN_PATH", os.path.join(self.tmp, "room-admin.json"))):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _from(self, me, lang):
        os.path.exists(self.busf) and os.remove(self.busf)
        with mock.patch.object(RP, "VIEWER_ME", me):
            self.assertEqual(say({"body": "hi", "room": "r1"}, lang), 200)
        with open(self.busf, encoding="utf-8") as f:
            return json.loads(f.readline())["from"]

    def test_default_follows_header(self):
        self.assertEqual(self._from("사용자", "en"), "user")
        self.assertEqual(self._from("사용자", "ko"), "사용자")
        self.assertEqual(self._from("사용자", None), "사용자")

    def test_explicit_never_changed(self):
        self.assertEqual(self._from("나", "en"), "나")


class StateMine(unittest.TestCase):
    _patches, run_state = StateWiring._patches, StateWiring.run_state   # borrowed, so its own tests do not run twice

    def _state(self, me, mine):
        with mock.patch.object(st, "VIEWER_ME", me), mock.patch.object(st, "MINE", mine):
            return self.run_state(1)[0]

    def test_default_both_spellings_mine(self):
        s = self._state("사용자", ["agent-a"])
        self.assertEqual(s["mine"], ["agent-a", "사용자", "user"])
        self.assertEqual(s["cfg"]["viewerIds"], ["사용자", "user"])

    def test_explicit_only_itself(self):
        s = self._state("나", ["agent-a", "나"])
        self.assertEqual(s["mine"], ["agent-a", "나"])
        self.assertEqual(s["cfg"]["viewerIds"], ["나"])


JS = "let LANG = 'ko';\n" + i18n_switch(("T", "KE")) + r"""
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[1] + '/web/js/90b-mypref.js', 'utf8');
const R = {};
for(const lang of ['ko', 'en']){
  LANG = lang;
  const c = {T, KE, softErr: () => {}, UIS: {getItem: () => null},
             document: {documentElement: {dataset: {}}, getElementById: () => null}};
  vm.createContext(c); vm.runInContext(src, c);
  const k = (v, src) => ({ok: true, keys: {viewer_me: {value: v, default: '사용자', src: src}}});
  R[lang] = [k('사용자', 'default'), k('user', 'file'), k('나', 'file'), k('사용자', 'env')].map(s => {
    c.mpVmDefault(s); return [s.keys.viewer_me.value, s.keys.viewer_me.default]; });
}
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SettingsDefaultShown(unittest.TestCase):
    def test_settings_show_lang_default(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = json.loads(subprocess.run(node_e(JS, root), capture_output=True, text=True, check=True).stdout)
        self.assertEqual(r["en"], [["user", "user"], ["user", "user"], ["나", "user"], ["사용자", "사용자"]])
        self.assertEqual(r["ko"], [["사용자", "사용자"], ["사용자", "사용자"], ["나", "사용자"], ["사용자", "사용자"]])


if __name__ == "__main__":
    unittest.main()
