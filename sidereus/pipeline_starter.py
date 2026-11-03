"""«Start with recommended setup» (POST /api/pipelines/starter {proj, policy, dry}): three default pipelines for a project
with none — quick-fix · change · bugfix — plus `_policy.json` (strict mode) only when `policy` is ticked.

dry = one unified diff of every new file; dry:false writes each with O_EXCL and reports files that already exist
(never overwritten). The gate is the person's `gate` when sent (blank = left out), else detect_test()'s command, else left out.
⚠Titles are English: these files ship to any user. Only pipeline files are written — never Claude Code settings —
and Sidereus never runs the gate or anything else here (rule 7).
"""
import difflib
import json
import os
import re

from sidereus.pipeline import _LOCK, _ROLES, _agents, _pipe_dir, _proj_ok, _sha
from sidereus.pipeline_schema import dump, validate

POLICY = {"enforce": "writes"}   # = hooks/pl_flow.py strict-mode test (exact content)
READ_MAX = 256 * 1024
_MAKE_TEST = re.compile(r"^test\s*:", re.M)
_NPM_STUB = "no test specified"   # npm init's placeholder script exits 1: not a test command
GATE_MAX = 200                    # = pipeline_schema stage.gate (one line, 1..200)
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def resolve_agent(role, have):
    """The user's agent whose name matches `role` (pipeline._ROLES regex), else general-purpose."""
    rx = dict(_ROLES).get(role)
    hits = sorted(n for n in have or () if isinstance(n, str) and rx and re.search(rx, n))
    return hits[0] if hits else "general-purpose"


def _read(fp):
    try:
        if os.path.islink(fp) or not os.path.isfile(fp):
            return None
        with open(fp, encoding="utf-8", errors="replace") as f:
            return f.read(READ_MAX)
    except OSError:
        return None


# ⚠Explicit pytest config only: a tests/ folder or a bare pyproject.toml also fits unittest/JS/Go repos (undetected = person types it).
_PYTEST_CFG = (("pyproject.toml", re.compile(r"^\s*\[tool\.pytest", re.M)),
               ("setup.cfg", re.compile(r"^\s*\[tool:pytest\]", re.M)),
               ("tox.ini", re.compile(r"^\s*\[pytest\]", re.M)))


def _pytest_evidence(proj):
    if any(_read(os.path.join(proj, *p)) is not None
           for p in (("pytest.ini",), ("conftest.py",), ("tests", "conftest.py"))):
        return True
    for f, rx in _PYTEST_CFG:
        t = _read(os.path.join(proj, f))
        if t is not None and rx.search(t):
            return True
    return False


def detect_test(proj):
    """Test command from project files (read only, never run), or None."""
    pk = _read(os.path.join(proj, "package.json"))
    if pk is not None:
        try:
            sc = json.loads(pk).get("scripts")
        except (ValueError, AttributeError):
            sc = None
        t = sc.get("test") if isinstance(sc, dict) else None
        if isinstance(t, str) and t.strip() and _NPM_STUB not in t:
            return "npm test"
    if _pytest_evidence(proj):
        return "python3 -m pytest -q"
    if _read(os.path.join(proj, "Cargo.toml")) is not None:
        return "cargo test"
    if _read(os.path.join(proj, "go.mod")) is not None:
        return "go test ./..."
    mk = _read(os.path.join(proj, "Makefile"))
    if mk is not None and _MAKE_TEST.search(mk):
        return "make test"
    return None


def _st(title, role, have, task, gate=None, **kw):
    s = {"title": title, "agent": resolve_agent(role, have), "task": task}
    if gate:
        s["gate"] = gate
    s.update(kw)
    return s


def drafts(proj, gate):
    """[(name, dict)] of the three starter pipelines. ⚠Every stage title is custom (English), so each carries a task."""
    have = [a["name"] for a in _agents(proj)]
    d = {"model": "inherit", "retry": 0}
    qf = {"v": 1, "name": "quick-fix", "title": "Quick fix", "use": "Small fix whose cause is known: fix, then check it.",
          "catch": "person", "defaults": dict(d), "stages": [
              _st("Fix", "fix", have, "Apply the minimal fix at the known cause and add or update a regression test. "
                  "Report changed files; anything else you find goes in findings.", gate),
              _st("Review", "review", have, "No edits. Review the diff for bugs and regressions; PASS or FAIL with file:line.",
                  onFail={"goto": "Fix", "max": 1})]}
    ch = {"v": 1, "name": "change", "title": "Change", "use": "A feature or a change across files: design, build, verify, review.",
          "defaults": dict(d), "stages": [
              _st("Design", "design", have, "Read-only. Write the spec: criteria, files to change, tests, risks.", produces="slices"),
              _st("Implement", "build", have, "Implement your slice of the spec and its tests. Touch only the files in your slice.",
                  fanout="slices", onError="continue"),
              _st("Verify", "check", have, "No edits. Run the project's tests and check the criteria; PASS or FAIL with evidence.",
                  gate, onFail={"goto": "Implement", "max": 2}),
              _st("Review", "review", have, "No edits. Review the diff for bugs, security and regressions; PASS or FAIL with file:line.",
                  onFail={"goto": "Implement", "max": 1})]}
    bf = {"v": 1, "name": "bugfix", "title": "Bug fix", "use": "A bug whose cause is not known yet: reproduce, find the cause, fix.",
          "catch": "person", "defaults": dict(d), "stages": [
              _st("Reproduce", "fix", have, "No fix yet. Reproduce the bug with a failing test or exact steps; report them."),
              _st("Cause", "fix", have, "Read-only. Find the root cause; report file:line and why, no edits."),
              _st("Fix", "fix", have, "Fix the root cause and make the reproducing test pass. Report changed files.", gate),
              _st("Regression", "check", have, "No edits. Run the tests and confirm the bug is gone with nothing else broken.",
                  gate, onFail={"goto": "Fix", "max": 2})]}
    return [("quick-fix", qf), ("change", ch), ("bugfix", bf)]


def _files(proj, policy, gate):
    """[(rel, text)] for the starter; ValueError when a draft fails the schema (a code defect: `gate` is checked first)."""
    out = []
    for name, P in drafts(proj, gate):
        errs = validate(P, name)
        if errs:
            raise ValueError("%s: %s" % (name, errs[0]))
        out.append((".claude/pipelines/%s.json" % name, dump(P)))
    if policy:
        out.append((".claude/pipelines/_policy.json", json.dumps(POLICY) + "\n"))
    return out


def _inside(proj, d):
    return os.path.realpath(d) == os.path.join(os.path.realpath(proj), ".claude", "pipelines")


def starter(req):
    """(code, body) for POST /api/pipelines/starter {proj, policy, dry, gate?}. Caller checks the viewer Origin.
    Body: {ok, dry, diff, gate (used, str | null), detected (detect_test, str | null), files: [{rel, state: new|exists|written}]}."""
    if not isinstance(req, dict):
        return 400, {"ok": False, "err": "bad body"}
    proj = req.get("proj")
    if not _proj_ok(proj):
        return 403, {"ok": False, "err": "unknown project"}
    mine = req.get("gate")
    if mine is not None and not (isinstance(mine, str) and len(mine) <= GATE_MAX and not _CTRL.search(mine)):
        return 400, {"ok": False, "err": "gate: one line, up to 200 chars"}
    detected = detect_test(proj)
    # ⚠A sent "" (blank) is an explicit «no gate», not «use detected»: the UI offers an empty input as «gate left out».
    gate = (mine.strip() or None) if mine is not None else detected
    files = _files(proj, req.get("policy") is True, gate)
    d = _pipe_dir(proj)
    with _LOCK:
        rows = [{"rel": rel, "state": "exists" if os.path.lexists(os.path.join(proj, rel)) else "new"} for rel, _t in files]
        diff = "".join("".join(difflib.unified_diff([], t.splitlines(True), "/dev/null", "b/" + rel))
                       for (rel, t), r in zip(files, rows) if r["state"] == "new")
        if req.get("dry") is not False:
            return 200, {"ok": True, "dry": True, "diff": diff, "gate": gate, "detected": detected, "files": rows}
        # ⚠Checked before makedirs too: a symlinked .claude would otherwise get a pipelines dir created outside the project.
        if not _inside(proj, d):
            return 400, {"ok": False, "err": "path leaves the project"}
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            return 500, {"ok": False, "err": "write failed ({e})", "vars": {"e": type(e).__name__}}
        if not _inside(proj, d):
            return 400, {"ok": False, "err": "path leaves the project"}
        shas = {}
        for (rel, text), r in zip(files, rows):
            if r["state"] != "new":
                continue
            try:
                fd = os.open(os.path.join(proj, rel), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            except FileExistsError:
                r["state"] = "exists"   # created between the check and the write: still never overwritten
                continue
            except OSError as e:
                return 500, {"ok": False, "err": "write failed ({e})", "vars": {"e": type(e).__name__}, "files": rows}
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            r["state"] = "written"
            shas[rel] = _sha(text)
    return 200, {"ok": True, "dry": False, "diff": diff, "gate": gate, "detected": detected, "files": rows, "sha": shas}
