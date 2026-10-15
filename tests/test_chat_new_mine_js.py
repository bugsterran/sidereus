"""Chat-tab new-post count (web/js chatNew): the page's own posts (VIEWER_ME, now part of `mine`) never count as new."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ChatNewMine(unittest.TestCase):
    def test_viewer_posts_do_not_change_the_count(self):
        src = js_fn("chatNew") + r"""
var CFG = {viewerMe: '사용자'};
let chatSeen = 100;
const peer = [{t: 101, from: 'alice', idSrc: 'identity'}, {t: 102, from: 'bob', idSrc: 'identity'},
              {t: 99, from: 'alice', idSrc: 'identity'}];
const own = [{t: 103, from: '사용자', idSrc: 'viewer', mine: true},
             {t: 104, from: '사용자', idSrc: 'identity', mine: true}];   // same name written by another path
let MSGS = peer.slice();
const R = {before: chatNew()};
MSGS = peer.concat(own);
R.after = chatNew();
process.stdout.write(JSON.stringify(R));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"before": 2, "after": 2})


if __name__ == "__main__":
    unittest.main()
