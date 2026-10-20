"""Chat participant list (50-people.js buildPeople): a participant whose mbox matches a live session row gets
that session's platform logo; an id with no session row gets none (no guessing from the name)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("rcPlat", "rcWho", "buildPeople")


def rows(ids, sess):
    now = 1700000000
    js = ("const SESS=" + json.dumps(sess) + ", place='dm', ROOMS={}, PROF={}, CUR={};\n"
          "const MSGS=" + json.dumps([{"from": i, "t": now * 1e9, "audience": []} for i in ids]) + ";\n"
          "const PRES=" + json.dumps({i: {"online": True, "at": now, "source": "watch"} for i in ids}) + ";\n"
          "Date.now=()=>" + str(now * 1000) + ";\n"
          "const OUT={}; const el=id=>({id:id}); const document={querySelector:()=>el('h'),"
          " getElementById:el};\n"
          "function setHtml(e,h){OUT[e.id]=h;} function esc(s){return String(s).replace(/</g,'&lt;');}\n"
          "function T(s){return s;} function TV(o){return o.msg;} function AGO(s){return s;} function ago(s){return s+'s';}\n"
          "function U(n){return n;} function inPlace(){return true;} const nmSty=()=>'';\n"
          "function aiLogo(p){return '<i class=\"ailg ailg-'+p+'\"></i>';}\n"
          + "\n".join(js_fn(f) for f in FNS) + "\n"
          "buildPeople();\n"
          "const R={}; (OUT.people.match(/<span class=nxn><b>.*?<\\/b>/g)||[]).forEach(s=>{\n"
          "  const b=s.slice(19,-4); R[b.replace(/<i[^>]*><\\/i>/,'')]=b; });\n"
          "process.stdout.write(JSON.stringify(R));")
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class PeopleLogo(unittest.TestCase):
    def test_platform_logo_per_session(self):
        r = rows(["api-agent", "admin-codex", "ghost"],
                 [{"mbox": "api-agent", "plat": "cc"}, {"mbox": "admin-codex", "plat": "cx"}])
        self.assertIn("ailg-cc", r["api-agent"])
        self.assertIn("ailg-cx", r["admin-codex"])
        self.assertNotIn("ailg", r["ghost"])   # unknown id: no logo, not a Claude fallback

    def test_name_escaped(self):
        r = rows(["<b>"], [])
        self.assertIn("&lt;b>", r)


if __name__ == "__main__":
    unittest.main()
