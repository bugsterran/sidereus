"""Replay recorded pipeline event sequences (tests/fixtures/plreplay/*.json) through hooks/pl_flow.py, then check each
checkpoint at three layers: raw runs.json (1), sidereus/pl_runs.pl_model (2) and the UI derivation in web/js (3).
Schema and cell grammar: tests/fixtures/plreplay/README.md. Tmp dirs only, fixed clock."""
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._i18n_js import i18n_prelude
from tests._load import sidereus, js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX_DIR = os.path.join(ROOT, "tests", "fixtures", "plreplay")
SID = "sess-0001"
T0 = 1000000.0
_spec = importlib.util.spec_from_file_location("pl_flow_replay", os.path.join(ROOT, "hooks", "pl_flow.py"))
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
_CELL = re.compile(r"^(run|done|skip|back|fail|hold|wait)((?: (?:k|n)=\d+| via=[^ ]+)*)$")
_BG_TEXT = "Async agent launched"   # matches pl_flow BG_RE
_JS_FNS = ("plTk", "plWhy", "plAgLab", "plAgLabs", "plPsOk", "plPrLt", "plPrLive", "tlPlOne", "tlPlCur", "tlPlSt", "plPulseOn", "plPass")


def cell(v):
    """`<o>[ k=N][ via=T][ n=N]` -> {o, k?, via?, n?}; ValueError on anything else."""
    m = _CELL.match(v.strip()) if isinstance(v, str) else None
    if not m:
        raise ValueError("bad cell %r" % (v,))
    out = {"o": m.group(1)}
    for part in m.group(2).split():
        key, val = part.split("=", 1)
        out[key] = val if key == "via" else int(val)
    return out


def _layer(cp, name):
    """Expected {title: cell} for one layer: `st` with the layer's own override (`model` / `view`) on top."""
    st = dict(cp.get("st") or {})
    st.update({k: v for k, v in (cp.get(name) or {}).items() if k not in ("cur", "status")})
    return {t: cell(v) for t, v in st.items()}


def _cmp(where, title, want, got, keys):
    """Mismatch lines for one stage; `got` None = stage absent (wait)."""
    if got is None:
        return [] if want["o"] == "wait" else ["%s %s: want %s, absent" % (where, title, want["o"])]
    out = []
    for k in keys:
        if k in want or k == "o":
            exp = want.get(k, 1 if k == "k" else None)
            if got.get(k) != exp:
                out.append("%s %s.%s: want %r, got %r" % (where, title, k, exp, got.get(k)))
    return out


def _cm(where, cp, get):
    """cp.cm {title: N} = commit times recorded on that stage (absent title = not checked)."""
    return ["%s %s.cm: want %d, got %r" % (where, t, n, get(t)) for t, n in (cp.get("cm") or {}).items() if len(get(t) or []) != n]


class Replay(object):
    """One fixture run against hook module `hook` and pl_runs module `plr` (both swappable for pre-fix proofs)."""

    def __init__(self, fx, hook=H, plr=None):
        self.fx, self.hook, self.plr = fx, hook, plr or sidereus("pl_runs")
        self.name = fx["pipe"]["name"]
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        with open(os.path.join(self.proj, ".claude", "pipelines", self.name + ".json"), "w", encoding="utf-8") as f:
            json.dump(dict({"v": 1}, **fx["pipe"]), f, ensure_ascii=False)
        self.marks = os.path.join(self.tmp, "plmark")
        self.t = T0
        self.open = {}   # aid -> live sub row (tagged dispatch still out)

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patches(self):
        vals = {"MARK_DIR": self.marks, "CONFIG_PATH": os.path.join(self.tmp, "config.local.json"), "_now": lambda: self.t,
                "CLAUDE_DIR": os.path.join(self.tmp, "user-claude"), "HOME_DIR": self.tmp,
                "DIRS_DIR": os.path.join(self.tmp, "plbrief")}
        # ⚠create=True only for an older hook version loaded for a pre-fix check: on the current hook a renamed global
        #   must fail here, or the replay would write to the real path.
        old = self.hook is not H
        ps = [mock.patch.object(self.hook, k, v, create=old) for k, v in vals.items()]
        ps.append(mock.patch.object(self.plr, "PLR_DIR", self.marks))
        return ps

    def _hook(self, i, e):
        """Feed event i to the hook; returns hookSpecificOutput or None."""
        tool, tag = e["tool"], e.get("tag") or ""
        desc = tag + " x"
        ti = {"summary" if tool == "SendMessage" else "description": desc}
        if tool in ("Agent", "Task"):
            if e.get("sub"):
                ti["subagent_type"] = e["sub"]
            if e.get("model"):
                ti["model"] = e["model"]
            if e.get("bg"):
                ti["run_in_background"] = True
        if tool == "SendMessage" and e.get("to"):
            ti["to"] = e["to"]
        if tool == "Bash":
            ti["command"] = "git commit -m x" if e.get("commit") else "true"
        ev = {"hook_event_name": "PreToolUse" if e["e"] == "pre" else "PostToolUse", "tool_name": tool,
              "session_id": SID, "cwd": self.proj, "tool_input": ti}
        if tool == "Bash" and e.get("aid"):
            ev["agent_id"] = e["aid"]   # a subagent's own Bash carries the parent session_id plus agent_id
        if e["e"] == "post":
            ev["tool_response"] = {"content": [{"type": "text", "text": _BG_TEXT if e.get("bg") else "ok"}]}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            try:
                self.hook.main([])
            except TypeError:   # older hook versions take no argv (pre-fix proofs)
                self.hook.main()
        v = out.getvalue()
        return json.loads(v).get("hookSpecificOutput") if v else None

    def _track(self, e, denied):
        """Live sub rows: an Agent/Task Pre opens its aid, a foreground Post or `bgdone` closes it, a SendMessage reopens its target."""
        if denied:
            return
        # launched id: hand-written fixtures use `aid`, the miner `to` (its `aid` is only a subagent's own Bash)
        aid = (e.get("aid") or e.get("to")) if e["tool"] in ("Agent", "Task") else e.get("to") if e["tool"] == "SendMessage" else None
        if not aid:
            return
        if e["e"] == "bgdone" or (e["e"] == "post" and not e.get("bg")):
            self.open.pop(aid, None)
        elif e["e"] == "pre":
            # ⚠a continued agent's live row keeps its original stage tag (pl_model copies run to every listing)
            self.open.setdefault(aid, {"lab": "%s: %s x" % (e.get("sub") or "agent", e.get("tag") or ""), "min": 0,
                                       "aid": aid, "tid": "tu_" + aid})

    def run(self):
        """[(checkpoint, [mismatch lines])] for every checkpoint of the fixture."""
        cps = {c["at"]: c for c in self.fx.get("cp") or []}
        res, rows = [], []
        ps = self._patches()
        for p in ps:
            p.start()
        try:
            for i, e in enumerate(self.fx["ev"]):
                self.t = T0 + float(e["t"])
                bad = []
                denied = False
                if e["e"] in ("pre", "post"):
                    # ⚠a denied or failed call gets no PostToolUse (Claude Code fires PostToolUseFailure, which pl_flow ignores)
                    if e["e"] == "post" and (e.get("denied") or e.get("err")):
                        continue
                    o = self._hook(i, e)
                    denied = bool(o and o.get("permissionDecision") == "deny")
                    if e["e"] == "pre" and denied != bool(e.get("denied")):
                        bad.append("ev %d layer 0: want denied=%d, got %d" % (i, bool(e.get("denied")), denied))
                self._track(e, denied)
                if i in cps:
                    bad += self._raw(i, cps[i])
                    pr, more = self._model(i, cps[i])
                    bad += more
                    rows.append((i, cps[i], pr))
                if bad or i in cps:
                    res.append((i, bad))
        finally:
            for p in reversed(ps):
                p.stop()
        view = self._view(rows)
        out = {i: b for i, b in res}
        return [(c, out.get(i, []) + view.get(i, [])) for i, c, _ in rows] + \
            [({"at": i}, b) for i, b in res if i not in cps]

    def _raw(self, i, cp):
        where = "ev %d layer 1" % i
        try:
            with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
                r = json.load(f)["runs"][self.name]
        except (OSError, KeyError, ValueError):
            return ["%s: no run %s" % (where, self.name)]
        bad = []
        if bool(r.get("end")) != bool(cp.get("end")):
            bad.append("%s end: want %d, got %r" % (where, bool(cp.get("end")), r.get("end")))
        if "cur" in cp and r.get("cur") != cp["cur"]:
            bad.append("%s cur: want %r, got %r" % (where, cp["cur"], r.get("cur")))
        st = r.get("st") or {}
        for t, want in _layer(cp, "raw").items():
            g = st.get(t)
            bad += _cmp(where, t, want, None if g is None else dict(g, o=g.get("s"), k=g.get("k") or 1), ("o", "k", "n"))
        bad += _cm(where, cp, lambda t: (st.get(t) or {}).get("cm"))
        return bad

    def _model(self, i, cp):
        where = "ev %d layer 2" % i
        fp = os.path.join(self.marks, SID + ".runs.json")
        now = self.t
        if os.path.exists(fp):
            os.utime(fp, (now, now))
        sub = [dict(x, lab=x["lab"]) for x in self.open.values()]
        plm = {"name": self.name, "title": cp["plm"], "age": 0} if cp.get("plm") else None
        rows = self.plr.pl_model(SID, None, sub, plm, now, cp.get("act") or "run")
        pr = next((r for r in rows if r["name"] == self.name), None)
        if pr is None:
            return None, ["%s: no plrun row" % where]
        bad = []
        if bool(pr.get("end")) != bool(cp.get("end")):
            bad.append("%s end: want %d, got %r" % (where, bool(cp.get("end")), pr.get("end")))
        for t, want in _layer(cp, "model").items():
            g = pr["stages"].get(t)
            bad += _cmp(where, t, want, None if g is None else dict(g, k=g.get("k") or 1, via=g.get("via")), ("o", "k", "via", "n"))
        bad += _cm(where, cp, lambda t: (pr["stages"].get(t) or {}).get("cm"))
        return pr, bad

    def _view(self, rows):
        """Layer 3 in one node run: plPrLt via tlPlOne (file stage order, fin cut), tlPlCur, tlPlSt, plPulseOn."""
        rows = [(i, c, pr) for i, c, pr in rows if pr is not None]
        if not rows:
            return {}
        loops = [[s["title"], s["onFail"]["goto"]] for s in self.fx["pipe"]["stages"] if isinstance(s.get("onFail"), dict)]
        args = [{"pr": pr, "now": T0 + float(self.fx["ev"][i]["t"])} for i, _, pr in rows]
        src = (i18n_prelude("'en'", ("T",)) + "const PL_OS = ['run', 'done', 'skip', 'fail', 'back', 'hold'];\n"
               + "const PLS = { data: {} }, TLPL_REQ = new Set(), tlPlLoad = () => {};\n"
               + "\n".join(js_fn(n) for n in _JS_FNS)
               + "\nconst PIPE = %s, LOOPS = %s, ARGS = %s;\n" % (json.dumps(self.fx["pipe"]), json.dumps(loops), json.dumps(args))
               + "console.log(JSON.stringify(ARGS.map(a => { PLS.data[a.pr.proj] = { pipelines: [PIPE] };\n"
               + "  const fin = !(!a.pr.end && plPrLive(a.pr)), pl = tlPlOne({ sid: 'x', r: a.pr }, fin, null, { now: a.now });\n"
               + "  return { lt: pl.lt, titles: pl.titles, cur: tlPlCur(pl), status: tlPlSt(pl),\n"
               + "    pulse: LOOPS.filter(l => plPulseOn(pl.lt, l[0], l[1])) }; })))")
        p = subprocess.run(node_e(src), capture_output=True, text=True, encoding="utf-8")
        if p.returncode:
            return {i: ["ev %d layer 3: node failed: %s" % (i, p.stderr.strip()[-300:])] for i, _, _ in rows}
        out = {}
        for (i, cp, pr), v in zip(rows, json.loads(p.stdout)):
            where, bad = "ev %d layer 3" % i, []
            exp = _layer(cp, "view")
            for t in v["titles"]:
                g = v["lt"].get(t) or {}
                bad += _cmp(where, t, exp.get(t, {"o": "wait"}), dict(g, o=g.get("st"), via=g.get("via") or None), ("o", "k", "via"))   # view n = agents shown, not dispatches
            vw = cp.get("view") or {}
            want_cur = vw.get("cur", cp.get("cur"))
            if want_cur is not None and v["cur"] != want_cur:
                bad.append("%s cur: want %r, got %r" % (where, want_cur, v["cur"]))
            want_st = vw.get("status") or ("fail" if any(c["o"] == "fail" for c in exp.values())
                                           else "fin" if cp.get("end") else "run")
            if v["status"] != want_st:
                bad.append("%s status: want %r, got %r" % (where, want_st, v["status"]))
            want_p = sorted(map(list, cp.get("pulse") or []))
            if sorted(v["pulse"]) != want_p:
                bad.append("%s pulse: want %r, got %r" % (where, want_p, v["pulse"]))
            bad += _cm(where, cp, lambda t: (v["lt"].get(t) or {}).get("cm"))
            out[i] = bad
        return out


def fixtures():
    return sorted(glob.glob(os.path.join(FX_DIR, "*.json")))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def replay(fx, hook=H, plr=None):
    rp = Replay(fx, hook, plr)
    try:
        return rp.run()
    finally:
        rp.close()


class PlReplay(unittest.TestCase):
    def test_fixtures_present(self):
        self.assertGreaterEqual(len([p for p in fixtures() if os.path.basename(p).startswith("edge-")]), 5)

    def test_cell_grammar(self):
        self.assertEqual(cell("run k=2 via=검증 n=3"), {"o": "run", "k": 2, "via": "검증", "n": 3})
        self.assertEqual(cell("wait"), {"o": "wait"})
        for bad in ("running", "run k=x", "done  n=1", 3):
            with self.assertRaises(ValueError):
                cell(bad)

    def test_fixtures(self):
        for path in fixtures():
            fx = load(path)
            self.assertTrue(fx.get("cp"), path)   # a fixture without hand-written checkpoints asserts nothing
            for cp, bad in replay(fx):
                with self.subTest(fixture=os.path.basename(path), at=cp.get("at")):
                    self.assertEqual(bad, [])

    def test_pass_commit_window(self):
        # pass 1 = [100, 200), pass 2 = [200, 300), latest pass from 300: each commit lands in one pass only
        L = {"k": 3, "p0": 300, "w0": 100, "ag": [], "ps": [{"a": 100, "b": 190, "s": "back"}, {"a": 200, "b": 290, "s": "back"}],
             "cm": [150, 250, 320]}
        src = js_fn("plAgLabs") + js_fn("plAgLab") + js_fn("plPass") + "\nconst L = %s;\nconsole.log(JSON.stringify([plPass(L, 0).cm, plPass(L, 1).cm]))" % json.dumps(L)
        out = json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        self.assertEqual(out, [[150], [250]])

    def test_pulse_predicate(self):
        src = js_fn("plPulseOn") + "\nconst lt = %s;\nconsole.log(JSON.stringify([plPulseOn(lt, 'b', 'a'), plPulseOn(lt, 'c', 'a'), plPulseOn(lt, 'b', 'd'), plPulseOn(null, 'b', 'a')]))" \
            % json.dumps({"a": {"st": "run", "via": "b", "from": {"b": 1, "c": 2}}, "d": {"st": "done", "via": "b", "from": {"b": 1}}})
        out = json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        self.assertEqual(out, [True, False, False, False])


if __name__ == "__main__":
    unittest.main()
