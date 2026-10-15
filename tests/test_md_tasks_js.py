"""md() GFM task items: `- [ ]`/`- [x]` become a read-only checkbox; other list items stay byte-identical (node)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    src = ("const NL = '\\n';\n"
           "function esc(s){ return String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])); }\n"
           "const inline = x => esc(x); const mdLinks = x => x; const codeBlock = b => '<pre>' + esc(b) + '</pre>';\n"
           + js_fn("md") + "\n" + body)
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


BOX = '<input type=checkbox disabled'


class Tasks(unittest.TestCase):
    def test_tasks(self):
        cases = ['- [ ] foo', '- [x] done', '* [X] big', '1. [ ] num',
                 '- a [ ] mid', '- plain', '- [ ] <b>', '- [x]', '- [y] no']
        out = run("const c=" + json.dumps(cases) + ";process.stdout.write(JSON.stringify("
                  "[].concat(c.map(s => md(s)), c.map(s => md(s, 1)))));")
        for k in (0, len(cases)):
            o = out[k:k + len(cases)]
            self.assertEqual(o[0], '<ul><li class=mdtask>' + BOX + '> foo</li></ul>')
            self.assertEqual(o[1], '<ul><li class=mdtask>' + BOX + ' checked> done</li></ul>')
            self.assertEqual(o[2], '<ul><li class=mdtask>' + BOX + ' checked> big</li></ul>')
            self.assertEqual(o[3], '<ul><li class=mdtask>' + BOX + '> num</li></ul>')
            self.assertEqual(o[4], '<ul><li>a [ ] mid</li></ul>')
            self.assertEqual(o[5], '<ul><li>plain</li></ul>')
            self.assertEqual(o[6], '<ul><li class=mdtask>' + BOX + '> &lt;b&gt;</li></ul>')
            self.assertEqual(o[7], '<ul><li>[x]</li></ul>')
            self.assertEqual(o[8], '<ul><li>[y] no</li></ul>')


if __name__ == "__main__":
    unittest.main()
