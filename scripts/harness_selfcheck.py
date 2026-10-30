"""Harness guard self-check: replays tests/fixtures/harness_e2e/<case>/case.json through the real recorder path
(hooks/pl_flow.py main() + hooks/pl_guard.py for guard cases, scripts/evidence_rec.py for gate/keep rows) into
harness_flow.flow nodes, and writes one results file `DATA_DIR/harness-selfcheck.json` for the Harness screen.

Usage: python3 scripts/harness_selfcheck.py [--out PATH]
Exit 0 = every case matched its `expect`, 1 = a case missed, 2 = the replay set is absent (shipped build).
⚠Run by a person or CI only; the viewer reads the file and never runs this.
⚠Every recorder path is patched into a temp dir; the only live write is the one atomic result file.
Metadata only: case name · guard · situation · expect · actual · pass · pair · deny codes.
"""
import argparse
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sidereus import gitinfo, harness_evidence as HE, harness_flow as HF, harness_trail as HT  # noqa: E402
from sidereus.bus import _atomic_write  # noqa: E402
from sidereus.config import DATA_DIR  # noqa: E402

FX = os.path.join(ROOT, "tests", "fixtures", "harness_e2e")
OUT = os.path.join(DATA_DIR, "harness-selfcheck.json")
NOW = 1767225600.0   # synthetic clock (2026-01-01T00:00:00Z): fixture git dates and relative seconds are pinned to it
T0 = NOW - 900
SID = "e2e-sess-0001"


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H = _mod("pl_flow_selfcheck", "hooks/pl_flow.py")
REC = _mod("evidence_rec_selfcheck", "scripts/evidence_rec.py")


def case(name):
    with open(os.path.join(FX, name, "case.json"), encoding="utf-8") as f:
        return json.load(f)


def names():
    return sorted(n for n in os.listdir(FX) if os.path.isdir(os.path.join(FX, n)))


class Replay(object):
    """Patches every recorder/reader path into `tmp` on enter, restores on exit (also on error)."""

    def __init__(self, tmp):
        self.tmp = os.path.realpath(tmp)
        self.proj = os.path.join(self.tmp, "proj")
        self.marks = os.path.join(self.tmp, "plmark")
        self.evf = os.path.join(self.tmp, "evidence.jsonl")
        self.t = T0
        self._p = []

    def __enter__(self):
        os.makedirs(self.marks, exist_ok=True)
        os.makedirs(self.proj, exist_ok=True)
        env = dict((k, v) for k, v in os.environ.items() if k != "SIDEREUS_EVIDENCE")
        # ⚠_spawn stays patched: pl_flow otherwise starts the run-end report hook as a child process.
        pats = [mock.patch.object(o, k, v) for o, k, v in (
            (H, "MARK_DIR", self.marks), (H, "CONFIG_PATH", os.path.join(self.tmp, "cfg.json")),
            (H, "_now", lambda: self.t), (H, "CLAUDE_DIR", os.path.join(self.tmp, "u")), (H, "HOME_DIR", self.tmp),
            (H, "DIRS_DIR", os.path.join(self.tmp, "plbrief")), (H, "DATA_DIR", self.tmp),
            (H, "_spawn", lambda argv: None), (HF, "HF_DIR", self.marks), (HF, "_now", lambda: NOW),
            (HE, "EV_FILE", self.evf), (HE, "_now", lambda: NOW), (HT, "_now", lambda: NOW))]
        pats.append(mock.patch.dict(os.environ, env, clear=True))
        try:
            for p in pats:
                p.start()
                self._p.append(p)
        except Exception:
            self.__exit__(None, None, None)
            raise
        self._clear()
        return self

    def __exit__(self, *exc):
        while self._p:
            self._p.pop().stop()
        self._clear()
        return False

    @staticmethod
    def _clear():
        for c in (HF._HF_CACHE, HT._TR_CACHE, HE._CM_CACHE):
            c.clear()

    def flows(self):
        ev, floor = HE.scan(self.proj)
        return HF.flow(self.proj, ev, HT.trail(ev[:120], self.proj), floor=floor, commits=HE.commits(self.proj))

    def nodes(self):
        fl = self.flows()
        return dict((n["k"], n) for n in fl[0]["nodes"]) if fl else {}

    def record(self, mode, rc, steps, head="", dirty=False, ts=NOW):
        """One check.sh evidence row through scripts/evidence_rec.py (the recorder check.sh's EXIT trap calls)."""
        tsv = os.path.join(self.tmp, "steps.tsv")
        with open(tsv, "w", encoding="utf-8") as f:
            f.write("".join("%s\t%d\t%d\t%d\t%d\n" % tuple(s) for s in steps))
        REC.main([self.evf, mode, str(rc), self.proj, head, "1" if dirty else "0", tsv], ts=ts)

    def git(self, *args):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.tmp, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        if "SYSTEMROOT" in os.environ:   # Windows: git needs it to start
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        return subprocess.run(gitinfo.git_argv(self.proj, args), env=env, check=True, capture_output=True,
                              text=True, encoding="utf-8").stdout.strip()

    def _hook(self, ev):
        out, old = io.StringIO(), (sys.stdin, sys.stdout)
        try:
            sys.stdin, sys.stdout = io.StringIO(json.dumps(ev)), out
            H.main()
        finally:
            sys.stdin, sys.stdout = old
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else {}

    def guard(self, fx):
        pipe = fx["pipe"]
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        with open(os.path.join(self.proj, ".claude", "pipelines", pipe["name"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(pipe, f)
        agents = dict((s["title"], s["agent"]) for s in pipe["stages"])
        denied = []
        for e in fx["ev"]:
            self.t += 10
            if "check" in e:   # the stage's gate run, recorded by check.sh's recorder
                self.record(e["check"]["mode"], e["check"]["rc"], [["tests", e["check"]["rc"], 10, 0, 1]], ts=self.t)
                continue
            if e["tool"] == "Bash":
                ti = {"command": e["cmd"], "description": e.get("desc", "x")}
            else:
                ti = {"description": "[pl:%s/%s] x" % (pipe["name"], e["stage"]), "subagent_type": agents[e["stage"]]}
            ev = {"hook_event_name": "PreToolUse" if e["e"] == "pre" else "PostToolUse", "tool_name": e["tool"],
                  "session_id": SID, "cwd": self.proj, "tool_input": ti}
            if e["e"] == "post":
                ev["tool_response"] = {"content": [{"type": "text", "text": "ok"}]}
            o = self._hook(ev)
            if e["e"] == "pre":
                denied.append(int(o.get("permissionDecision") == "deny"))
        fp = os.path.join(self.marks, SID + ".runs.json")
        if os.path.exists(fp):
            os.utime(fp, (NOW, NOW))
        g = self.nodes().get("guard")
        actual = ("blocked" if g["v"]["deny"] else "allowed") if g and g.get("v") else ""
        return {"actual": actual, "node": g, "denied": denied}

    def gate(self, fx):
        os.makedirs(os.path.join(self.proj, ".git"))   # git root marker only; every git read fails and is skipped
        for r in fx["rows"]:
            self.record(r["mode"], r["rc"], r["steps"], head="abc1234", ts=NOW - 300 + r["dt"])
        g = self.nodes().get("gate")
        actual = ("r2g" if g["v"]["r2g"] else "no r2g") if g and g.get("v") else ""
        return {"actual": actual, "node": g}

    def keep(self, fx):
        self.git("init", "-q")
        ts = NOW - 600
        for i, s in enumerate(fx["steps"]):
            ts += 60
            if "commit" in s:
                for fn, body in s["commit"].items():
                    with open(os.path.join(self.proj, fn), "w", encoding="utf-8") as f:
                        f.write(body)
                self.git("add", "-A")
                self.git("commit", "-q", "--allow-empty", "-m", "c%d" % i)
            else:
                head = self.git("rev-parse", "--short", "HEAD")   # same as check.sh
                self.record(s["check"]["mode"], s["check"]["rc"], [["tests", s["check"]["rc"], 10, 0, 1]], head=head, ts=ts)
        k = self.nodes().get("keep")
        return {"actual": ((k or {}).get("v") or {}).get("state") or "", "node": k}

    def run(self, name):
        fx = case(name)
        return getattr(self, {"guard": "guard", "gate": "gate", "keep": "keep"}[fx["guard"]])(fx)


def replay(name, tmp):
    """{actual, node, ...} of one fixture case replayed in `tmp` (patches restored before return)."""
    with Replay(tmp) as r:
        return r.run(name)


def _head():
    """Full HEAD sha of the Sidereus repo (the code the guards ran from), "" on a git miss."""
    try:
        p = gitinfo._git_run(ROOT, ["rev-parse", "HEAD"], 10)
        s = (p.stdout or "").strip()
        return s if p.returncode == 0 and len(s) == 40 else ""
    except Exception:
        return ""


def _codes(node):
    return [r.get("code") for r in (node or {}).get("rec") or [] if r.get("k") == "deny" and r.get("code")]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Replay the harness guard self-check set and write its results file.")
    ap.add_argument("--out", default=OUT, help="results file (default DATA_DIR/harness-selfcheck.json)")
    a = ap.parse_args(argv)
    if not os.path.isdir(FX) or not names():   # an empty set would write cases [] and read as «Not run yet»
        print("replay set not found: %s" % FX)
        return 2
    cases, tmp = [], tempfile.mkdtemp(prefix="hselfcheck-")
    try:
        for n in names():
            fx = case(n)
            sub = os.path.join(tmp, n)
            os.makedirs(sub)
            try:
                res = replay(n, sub)
                actual, codes = res["actual"], _codes(res["node"]) if fx.get("guard") == "guard" else []
            except Exception as e:   # one broken case reads FAIL; the rest still run
                actual, codes = "error: %s" % type(e).__name__, []
            cases.append({"name": n, "guard": fx.get("guard"), "situation": fx.get("situation"), "expect": fx.get("expect"),
                          "actual": actual, "pass": actual == fx.get("expect"), "pair": fx.get("pair"), "codes": codes})
    finally:
        shutil.rmtree(tmp, True)
    doc = {"v": 1, "ts": int(time.time()), "head": _head(), "cases": cases}
    _atomic_write(os.path.abspath(a.out), (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8"),
                  prefix=".harness-selfcheck.", mkdir=True, mode=0o644)
    ok = sum(1 for c in cases if c["pass"])
    for c in cases:
        print("%s  %-26s expect %-9s actual %s" % ("PASS" if c["pass"] else "FAIL", c["name"], c["expect"], c["actual"]))
    print("%d/%d pass -> %s" % (ok, len(cases), a.out))
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
