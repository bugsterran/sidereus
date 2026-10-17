"""getJSON timeout (web/js/08-ui-kit.js): a hung fetch aborts and throws (e.timeout) so the poll marks the link down;
caller's signal still aborts; loadLive (46-tokens-tab.js) never starts a second /api/live while one is pending. Fake fetch, short ms."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all
from tests._node import node_e


def _async_fn(name):
    return re.compile(r"^async function " + name + r"\(.*?^}", re.S | re.M).search(js_all()).group(0)


def _live_src():
    m = re.search(r"^let liveBusy = false;$", js_all(), re.M)
    if m is None:
        raise AssertionError("46-tokens-tab.js: liveBusy guard missing")
    return "let liveBusy = false;\n" + _async_fn("loadLive")


JS = r"""
const R = {};
let FETCHES = 0, HANG = true;
// Fake fetch: hangs until aborted (rejects AbortError like the browser), or answers at once.
function fetch(url, o){
  FETCHES++;
  return new Promise((res, rej) => {
    if(!HANG) return res({ok: true, status: 200, json: async () => ({live: [1], liveSec: 3, liveStep: 10})});
    o.signal.addEventListener('abort', () => { const e = new Error('aborted'); e.name = 'AbortError'; rej(e); });
  });
}
let document = {hidden: false, querySelectorAll: () => [], querySelector: () => null};
let WKU = {}, CONN = {fails: 0};
const wkLive = () => '', softErr = () => {};
(async () => {
  const t0 = Date.now();
  try{ await getJSON('/api/state', {timeout: 50}); R.hung = 'resolved'; }
  catch(e){ R.hung = [e.name, !!e.timeout, !e.status, Date.now() - t0 < 2000]; }
  const ac = new AbortController();
  const p = getJSON('/x', {signal: ac.signal, timeout: 5000}); ac.abort();
  try{ await p; }catch(e){ R.caller = [e.name, !!e.timeout]; }
  HANG = false;
  R.ok = await getJSON('/ok', {timeout: 50});
  // live loop: a pending request blocks the next ticks
  HANG = true; FETCHES = 0;
  const a = loadLive(); loadLive(); loadLive();
  R.pending = FETCHES;
  await a;   // test shortens its timeout to 30ms
  R.after = FETCHES;
  HANG = false; await loadLive(); R.again = FETCHES;   // guard released after the timeout
  process.stdout.write(JSON.stringify(R));
})();
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class GetJSONTimeout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live = _live_src().replace("{timeout: 10000}", "{timeout: 30}")
        src = _async_fn("getJSON") + "\n" + live + "\n" + JS
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_hung_request_aborts_as_failure(self):
        self.assertEqual(self.R["hung"], ["AbortError", True, True, True])

    def test_caller_signal_is_not_a_timeout(self):
        self.assertEqual(self.R["caller"], ["AbortError", False])

    def test_healthy_answer_passes(self):
        self.assertEqual(self.R["ok"]["liveSec"], 3)

    def test_live_loop_one_in_flight(self):
        self.assertEqual(self.R["pending"], 1)
        self.assertEqual(self.R["after"], 1)
        self.assertEqual(self.R["again"], 2)


if __name__ == "__main__":
    unittest.main()
