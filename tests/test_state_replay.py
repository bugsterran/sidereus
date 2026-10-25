"""Replay recorded session shapes through the real state path: each `tests/fixtures/states/<case>/` folder is one
case (schema in that folder's README.md). Adding a case = adding a folder; no code change.

No live files, processes, clock or network: the case is copied into a temp Claude root, file ages are set from
the frozen NOW, and ps / lsof / `claude agents --json` / tool_busy / OTel / accounts are replaced on their owning
modules (live, live_probe, otel, claude_roots, agents).
"""
import glob
import json
import os
import re
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
cards = sidereus("cards")
bgp = sidereus("bgtasks_parse")
parse = sidereus("parse")
transcript = sidereus("transcript")
claude_roots = sidereus("claude_roots")
ident = sidereus("ident")

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "states")
CWD = "/nonexistent-sidereus/demo"   # ⚠must not exist: _session_cwd would otherwise restore a live path from the slug
_META = {"case.json", "expected.json", "ps.json", "agents.json", "otel.json", "README.md"}
_AGENTS_RE = re.compile(r"^agents\.([A-Za-z0-9_-]+)\.json$")   # per-account `claude agents --json` stdout


def _case_dirs():
    return sorted(d for d in glob.glob(os.path.join(CASES, "*")) if os.path.isdir(d))


def _read(d, name, default=None):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return f.read() if name.startswith("agents") else json.load(f)


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
    """subprocess stand-in for live_probe: `claude agents --json` prints that account's stdout, or the binary is missing.

    `out` = {CLAUDE_CONFIG_DIR or None (primary): stdout or None}, or one stdout for every account."""
    TimeoutExpired = _real_sp.TimeoutExpired

    def __init__(self, out):
        self.out = out

    def run(self, argv, **kw):
        out = self.out
        if isinstance(out, dict):
            out = out.get((kw.get("env") or {}).get("CLAUDE_CONFIG_DIR"))
        if out is None:
            raise FileNotFoundError(argv[0])
        return types.SimpleNamespace(stdout=out, returncode=0)


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
        """Copy the case into temp Claude roots; return ({transcript file name: path}, {label: config dir})."""
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
        plab = next(a["label"] for a in accs if a.get("primary"))
        self._patch(lp, "CLAUDE_PROJECTS", os.path.join(dirs[plab], "projects"))
        self._patch(cards, "CLAUDE_PROJECTS", os.path.join(dirs[plab], "projects"))
        root = dirs[case.get("root") or plab]
        tops = sorted(n for n in os.listdir(d) if n.endswith(".jsonl"))
        lab_of = case.get("roots") or {}

        def proj(name):
            return os.path.join(dirs[lab_of[name]] if name in lab_of else root, "projects", ident._slug(CWD))
        ages, fps = case.get("ages") or {}, {}
        for src in glob.glob(os.path.join(d, "**", "*"), recursive=True):
            rel = os.path.relpath(src, d)
            if os.path.isdir(src) or rel in _META or _AGENTS_RE.match(rel):
                continue
            if rel.startswith("sessions" + os.sep):
                dst = os.path.join(root, rel)
            elif os.sep in rel:                         # subagents/... sit beside the transcript
                self.assertEqual(len(tops), 1, "subagents/ needs exactly one transcript")
                dst = os.path.join(proj(tops[0]), os.path.splitext(tops[0])[0], rel)
            else:
                dst = os.path.join(proj(rel), rel)
                fps[rel] = dst
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            t = NOW - float(ages.get(rel.replace(os.sep, "/"), 0))
            os.utime(dst, (t, t))
        self.assertTrue(fps, "case has no transcript")
        return fps, dirs

    def _fakes(self, d, case, dirs):
        is_mac = case.get("os", "mac") == "mac"
        ps = _read(d, "ps.json", {"procs": [], "cwd": {}})
        snap = [tuple(r) for r in ps.get("procs") or []] if is_mac else []
        out = _read(d, "agents.json")
        per = {m.group(1): _read(d, n) for n in os.listdir(d) for m in [_AGENTS_RE.match(n)] if m}
        prim = {a["label"] for a in case.get("accounts") or [{"label": "main", "primary": True}] if a.get("primary")}
        if out is None and per:                        # primary runs with no CLAUDE_CONFIG_DIR; a label without a file fails
            out = {(None if lab in prim else dirs[lab]): txt for lab, txt in per.items()}
        alive = {str(r[0]) for r in snap}
        for txt in (out.values() if isinstance(out, dict) else [out]):
            if txt:
                alive |= {str(it.get("pid")) for it in json.loads(txt)}
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
        fps, dirs = self._install(d, case, tmp)
        self._fakes(d, case, dirs)
        name = os.path.basename(d)
        by_fp = {v: k for k, v in fps.items()}
        got = {}
        with _clock.frozen(sessions, notes, otel, live, lp, bgtasks, bgp, agents, transcript, claude_roots):
            lv = live.live_cwds(ttl=0)
            # ⚠same decision as sessions._sessions: blind accounts off macOS, then _live_slot over newest-first rows
            blind = sessions.agent_view_unknown() if case.get("os", "mac") != "mac" else set()
            slots = dict(lv) if isinstance(lv, dict) else {}
            for mt, fp in sessions._recent_transcripts(NOW, 12, lv):
                p = parse._parse_transcript(fp)
                p["contd"] = sessions._continued(fp)
                acct = sessions._row_acct(p.get("sid") or "", fp)
                lv2, stale = sessions._live_slot(p.get("cwd") or "", acct.get("acct") or "", p.get("contd"),
                                                 live.sid_alive(p.get("sid")), lv, slots, blind)
                st, o, _got, dead = sessions._row_state(mt, NOW, lv2, p, stale)
                row = sessions._row_status(st, o, p, NOW, mt)
                got[by_fp.get(fp, fp)] = {"state": row["state"], "blocked": row["blocked"],
                                          "acct": acct.get("acct", ""), "sub": agents._bg_show(p["sub"], NOW, dead)}
        if "rows" in want:
            rows = want["rows"]
        else:
            self.assertEqual(len(fps), 1, "%s: several transcripts need expected.json rows" % name)
            rows = {next(iter(fps)): want}
        for fn, w in rows.items():
            self.assertIn(fn, got, "%s: no row for %s" % (name, fn))
            g = got[fn]
            for k in ("state", "blocked", "acct"):
                if k in w:
                    self.assertEqual(g[k], w[k], "%s %s: %s" % (name, fn, k))
            if "sub" in w:
                self.assertEqual(len(g["sub"]), len(w["sub"]), "%s: sub rows %r" % (name, g["sub"]))
                for s, ws in zip(g["sub"], w["sub"]):
                    self.assertEqual({k: s.get(k) for k in ws}, ws, name)


class LiveSlot(unittest.TestCase):
    """sessions._live_slot branch order, one assertion per branch."""
    L = {"/a": 1}

    def test_blind_account_reads_unknown(self):
        slots = {"/a": 1}
        self.assertEqual(sessions._live_slot("/a", "work", "x", True, self.L, slots, {"work"}), (None, False))
        self.assertEqual(slots, {"/a": 1})

    def test_alive_by_id_keeps_slot(self):
        slots = {"/a": 1}
        self.assertEqual(sessions._live_slot("/a", "", "x", True, self.L, slots, {"work"}), (self.L, False))
        self.assertEqual(slots, {"/a": 1})

    def test_unknown_or_other_path_not_stale(self):
        self.assertEqual(sessions._live_slot("/a", "", "x", False, None, {}, set()), (None, False))
        self.assertEqual(sessions._live_slot("/b", "", "x", False, self.L, {"/a": 1}, set()), (self.L, False))

    def test_continued_leaves_slot(self):
        slots = {"/a": 1}
        self.assertEqual(sessions._live_slot("/a", "", "new", False, self.L, slots, set()), (self.L, True))
        self.assertEqual(slots, {"/a": 1})

    def test_slot_taken_then_full(self):
        slots = {"/a": 1}
        self.assertEqual(sessions._live_slot("/a", "", "", False, self.L, slots, set()), (self.L, False))
        self.assertEqual(slots, {"/a": 0})
        self.assertEqual(sessions._live_slot("/a", "", "", False, self.L, slots, set()), (self.L, True))


if __name__ == "__main__":
    unittest.main()
