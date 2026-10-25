"""Replay recorded session shapes through the real state path: each `tests/fixtures/states/<case>/` folder is one
case (schema in that folder's README.md). Adding a case = adding a folder; no code change.

No live files, processes, clock or network: the case is copied into a temp Claude root, file ages are set from
the frozen NOW, and ps / lsof / `claude agents --json` / tool_busy / OTel / accounts are replaced on their owning
modules (live, live_probe, otel, claude_roots, agents).
"""
import glob
import json
import os
import shutil
import subprocess as _real_sp
import tempfile
import types
import unittest
from unittest import mock

from tests import _clock
from tests._clock import NOW
from tests._load import load, sidereus

load()
live = sidereus("live")
lp = sidereus("live_probe")
sessions = sidereus("sessions")
notes = sidereus("notes")
otel = sidereus("otel")
agents = sidereus("agents")
bgtasks = sidereus("bgtasks")
bgp = sidereus("bgtasks_parse")
parse = sidereus("parse")
transcript = sidereus("transcript")
claude_roots = sidereus("claude_roots")
ident = sidereus("ident")

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "states")
CWD = "/nonexistent-sidereus/demo"   # ⚠must not exist: _session_cwd would otherwise restore a live path from the slug
_META = {"case.json", "expected.json", "ps.json", "agents.json", "otel.json", "README.md"}


def _case_dirs():
    return sorted(d for d in glob.glob(os.path.join(CASES, "*")) if os.path.isdir(d))


def _read(d, name, default=None):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return f.read() if name == "agents.json" else json.load(f)


def _empty_blocks(obj):
    """Rule-1 guard: every text/thinking block "", every tool input {}, every tool_result content empty."""
    msg = obj.get("message") if isinstance(obj, dict) else None
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c == ""
    for b in c or []:
        if not isinstance(b, dict):
            return False
        t = b.get("type")
        if t == "text" and b.get("text"):
            return False
        if t == "thinking" and b.get("thinking"):
            return False
        if t == "tool_use" and b.get("input") != {}:
            return False
        if t == "tool_result" and b.get("content") not in (None, "", []):
            return False
    return True


class _FakeSub(object):
    """subprocess stand-in for live_probe: `claude agents --json` prints agents.json, or the binary is missing."""
    TimeoutExpired = _real_sp.TimeoutExpired

    def __init__(self, out):
        self.out = out

    def run(self, argv, **kw):
        if self.out is None:
            raise FileNotFoundError(argv[0])
        return types.SimpleNamespace(stdout=self.out, returncode=0)


class StateReplay(unittest.TestCase):
    def test_at_least_six_cases(self):
        self.assertGreaterEqual(len(_case_dirs()), 6)

    def test_fixtures_are_metadata_only(self):
        n = 0
        for fp in glob.glob(os.path.join(CASES, "*", "**", "*.jsonl"), recursive=True):
            with open(fp, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    n += 1
                    self.assertTrue(_empty_blocks(json.loads(line)), "%s:%d carries content" % (fp, i))
        for fp in glob.glob(os.path.join(CASES, "*", "**", "*.meta.json"), recursive=True):
            with open(fp, encoding="utf-8") as f:
                self.assertFalse({"description", "prompt"} & set(json.load(f)), fp)
        self.assertGreater(n, 0)

    def test_cases(self):
        for d in _case_dirs():
            with self.subTest(case=os.path.basename(d)):
                self._run_case(d)

    # ── seam ────────────────────────────────────────────────────────────────
    def _patch(self, obj, name, val):
        p = mock.patch.object(obj, name, val)
        p.start()
        self.addCleanup(p.stop)

    def _reset_state(self):
        """Clear every per-process cache the state path reads; dicts/sets/lists restored after the case."""
        lists = ((lp, "_av_cache", [0.0, None]), (lp, "_av_fail", [0.0]), (lp, "_live_sids", [0.0, set()]),
                 (lp, "_live_pid_cwd", [0.0, {}]), (lp, "_sid_file", [0.0, {}]), (lp, "_sid_stale", [0.0, {}]),
                 (lp, "_ps_snap_cache", [0.0, None]), (lp, "_ps_snap_fail", [0.0, None]),
                 (agents, "_BOOT", [NOW - 86400]))
        for mod, name, init in lists:
            cur = getattr(mod, name)
            self.addCleanup(cur.__setitem__, slice(None), list(cur))
            cur[:] = init
        for mod, name in ((lp, "_av_sigs"), (lp, "_av_acct"), (lp, "_av_unknown"), (lp, "_stale"),
                          (agents, "_AGENT_META"), (bgtasks, "_bg_offset"), (bgp, "_bg_open"),
                          (bgp, "_bg_open_at"), (bgp, "_bg_seeded"), (bgp, "_bg_finished")):
            cur = getattr(mod, name)
            saved = cur.copy()
            self.addCleanup(lambda cur=cur, saved=saved: (cur.clear(), cur.update(saved)))
            cur.clear()
        for memo in (agents._AGENT_LAST, agents._AGENT_FIN, bgp._bg_popped, bgp._bg_resume, bgp._bg_sent,
                     bgp._bg_said, bgp._mon_lab, bgp._fg_lab):
            memo.clear()
        self._patch(live, "_live_cache", (0.0, set()))
        self._patch(lp, "_busy_cache", (0.0, {}))

    def _install(self, d, case, tmp):
        """Copy the case into temp Claude roots; return the transcript path."""
        accs = case.get("accounts") or [{"label": "main", "primary": True}]
        dirs = {}
        rows = []
        for a in accs:
            ad = os.path.join(tmp, ".claude-" + a["label"])
            os.makedirs(os.path.join(ad, "projects"))
            dirs[a["label"]] = ad
            rows.append({"dir": ad, "label": a["label"], "primary": bool(a.get("primary"))})
        by_real = {os.path.realpath(r["dir"]): r for r in rows}
        self._patch(claude_roots, "_cached", lambda: ([dict(r) for r in rows], [dict(r) for r in rows], by_real))
        self._patch(claude_roots, "_acct_rec", lambda sid: "")
        prim = dirs[next(a["label"] for a in accs if a.get("primary"))]
        self._patch(lp, "CLAUDE_PROJECTS", os.path.join(prim, "projects"))
        root = dirs[case.get("root") or next(a["label"] for a in accs if a.get("primary"))]
        proj = os.path.join(root, "projects", ident._slug(CWD))
        ages, fp = case.get("ages") or {}, None
        for src in glob.glob(os.path.join(d, "**", "*"), recursive=True):
            rel = os.path.relpath(src, d)
            if os.path.isdir(src) or rel in _META:
                continue
            if rel.startswith("sessions" + os.sep):
                dst = os.path.join(root, rel)
            elif os.sep in rel:                         # subagents/... sit beside the transcript
                sid = next(os.path.splitext(n)[0] for n in os.listdir(d) if n.endswith(".jsonl"))
                dst = os.path.join(proj, sid, rel)
            else:
                dst = os.path.join(proj, rel)
                fp = dst
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            t = NOW - float(ages.get(rel.replace(os.sep, "/"), 0))
            os.utime(dst, (t, t))
        self.assertTrue(fp, "case has no transcript")
        return fp

    def _fakes(self, d, case):
        is_mac = case.get("os", "mac") == "mac"
        ps = _read(d, "ps.json", {"procs": [], "cwd": {}})
        snap = [tuple(r) for r in ps.get("procs") or []] if is_mac else []
        out = _read(d, "agents.json")
        alive = {str(r[0]) for r in snap}
        if out:
            alive |= {str(it.get("pid")) for it in json.loads(out)}
        pcwd = dict(ps.get("cwd") or {})
        for mod in (live, lp):
            self._patch(mod, "IS_MAC", is_mac)
            self._patch(mod, "_ps_snap", lambda ttl=None: list(snap))
            self._patch(mod, "warn_once", lambda *a, **k: None)
        self._patch(live, "_live_pid_cwds", lambda pids: {p: pcwd[p] for p in pids if p in pcwd})
        self._patch(lp, "subprocess", _FakeSub(out))
        self._patch(lp, "bin_path", lambda n: "claude")
        self._patch(lp, "bin_forget", lambda n: None)        # ⚠in-memory only, stubbed so no real cache is touched
        self._patch(lp, "rich_env", lambda: {"PATH": "/usr/bin"})
        self._patch(lp, "_slow_why", lambda: [])
        self._patch(lp, "pid_alive", lambda pid: str(pid) in alive)
        busy = case.get("busy")
        self._patch(lp, "tool_busy", lambda ttl=2: busy)
        ot = _read(d, "otel.json", {}) or {}
        cur = {sid: dict(v, at=NOW - float(v.get("age", 0))) for sid, v in ot.items()}
        for name, val in (("_otel", cur), ("_otel_tools", {})):
            p = mock.patch.dict(getattr(otel, name), val, clear=True)
            p.start()
            self.addCleanup(p.stop)

    def _run_case(self, d):
        case = _read(d, "case.json")
        want = _read(d, "expected.json")
        tmp = tempfile.mkdtemp(prefix="sidereus-states-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self._reset_state()
        fp = self._install(d, case, tmp)
        self._fakes(d, case)
        with _clock.frozen(sessions, notes, otel, live, lp, bgtasks, bgp, agents, transcript, claude_roots):
            mt = os.path.getmtime(fp)
            lv = live.live_cwds(ttl=0)
            p = parse._parse_transcript(fp)
            p["contd"] = sessions._continued(fp)
            st, o, _got, dead = sessions._row_state(mt, NOW, lv, p, False)
            row = sessions._row_status(st, o, p, NOW, mt)
            subs = agents._bg_show(p["sub"], NOW, dead)
            acct = sessions._row_acct(p.get("sid") or "", fp)
        got = {"state": row["state"], "blocked": row["blocked"], "acct": acct.get("acct", "")}
        for k in ("state", "blocked", "acct"):
            if k in want:
                self.assertEqual(got[k], want[k], "%s: %s" % (os.path.basename(d), k))
        if "sub" in want:
            self.assertEqual(len(subs), len(want["sub"]), "%s: sub rows %r" % (os.path.basename(d), subs))
            for s, w in zip(subs, want["sub"]):
                self.assertEqual({k: s.get(k) for k in w}, w, os.path.basename(d))


if __name__ == "__main__":
    unittest.main()
