"""«+ New pipeline» (POST /api/pipelines/create): templates, copy from another project, suggested/std drafts.

Split from sidereus/pipeline.py at the 620-line cap. Imports from pipeline (never the reverse: cycle).
"""
import difflib
import json
import os

from sidereus.pipeline import _LOCK, _agents, _pipe_dir, _read_pipe, _sha, suggest
from sidereus.pipeline_projects import _proj_ok
from sidereus.pipeline_schema import _NAME, _one_line, dump, validate


# «+ New pipeline» templates. Agents a project lacks become general-purpose at create time; `main` is kept.
# Recommended titles take their default instruction from the runner (DEFAULT_TASKS); a custom title carries its own `task`.
_CROSS_TASK = (
    'Orchestrator stage: run it yourself. If you are a subagent, change nothing and FAIL with cause "unrelated", '
    'reason "main stage - the orchestrator runs this pipeline itself". '
    "Run one Bash call described `[pl:<this pipeline>/<this stage title>]` that runs "
    '`codex exec --sandbox read-only "<prompt>"` (first confirm the flag with `codex exec --help`). '
    "The prompt asks Codex to run git diff (or the range the request names), review it for bugs, security and "
    "regressions, list each blocking finding as file:line + fix, and change nothing. "
    "It is a one-shot run that takes no follow-up; to ask again, run a new exec. "
    "This stage is billed to the Codex account. "
    "PASS when Codex reports no blocking finding, otherwise FAIL. Relay the findings as they are and fix nothing.")
TEMPLATES = {
    "change": ("변경", {"model": "inherit", "retry": 0}, [
        {"title": "설계", "agent": "sidereus-designer", "produces": "slices"},
        {"title": "구현", "agent": "sidereus-implementer", "fanout": "slices", "onError": "continue"},
        {"title": "검증", "agent": "sidereus-verifier", "model": "sonnet", "onFail": {"goto": "구현", "max": 2}},
        {"title": "리뷰", "agent": "sidereus-reviewer", "onFail": {"goto": "구현", "max": 1, "then": "재검증"}},
        {"title": "재검증", "agent": "sidereus-verifier", "model": "sonnet", "onlyOnJump": True}]),
    "bugfix": ("버그 수정", {"model": "inherit", "retry": 0}, [
        {"title": "재현", "agent": "general-purpose"},
        {"title": "원인", "agent": "general-purpose"},
        {"title": "수정", "agent": "general-purpose"},
        {"title": "회귀", "agent": "general-purpose", "model": "sonnet", "onFail": {"goto": "수정", "max": 2}}]),
    "triage": ("트리아지", {"model": "inherit", "retry": 0}, [
        {"title": "트리아지", "agent": "general-purpose"}]),
    "live": ("라이브 검증", {"model": "inherit", "retry": 0}, [
        {"title": "라이브 검증", "agent": "general-purpose"}]),
    "cross-review": ("교차 리뷰", {"model": "inherit", "retry": 0}, [
        {"title": "교차 리뷰", "agent": "main", "task": _CROSS_TASK}]),
    "empty": ("", {"model": "inherit", "retry": 0}, [{"title": "설계", "agent": "general-purpose"}]),
}


def _from_template(proj, name, title, tpl):
    """New pipeline dict from a template; agents missing in the project (and ~/.claude/agents) -> general-purpose."""
    t_title, defaults, stages = TEMPLATES[tpl]
    have = {a["name"] for a in _agents(proj)}
    out = []
    for s in json.loads(json.dumps(stages)):
        if s["agent"] not in ("general-purpose", "main") and s["agent"] not in have:   # ⚠`main` = orchestrator stage, never an agent file
            s["agent"] = "general-purpose"
        out.append(s)
    return {"v": 1, "name": name, "title": title or t_title or name, "defaults": dict(defaults), "stages": out}


def _from_other(proj, name, title, src):
    """(dict, replaced agents) copied from another known project's valid pipeline; agents missing here -> general-purpose."""
    sp, sn = src.get("proj"), src.get("name")
    if not _proj_ok(sp) or not (isinstance(sn, str) and _NAME.fullmatch(sn)):
        return None, "unknown source"
    raw, P, err = _read_pipe(sp, sn)
    if err or validate(P, sn):
        return None, "source pipeline is not valid"
    have, gone = {a["name"] for a in _agents(proj)}, []
    for s in P["stages"]:
        if s["agent"] != "general-purpose" and s["agent"] not in have:
            gone.append(s["agent"])
            s["agent"] = "general-purpose"
    P["name"] = name
    if title:
        P["title"] = title
    return P, sorted(set(gone))


def create(req):
    """(code, body) for POST /api/pipelines/create {proj, name, title, template | from:{proj, name}, dry}. dry = full new file as a diff;
    dry:false writes it. ⚠Never overwrites (O_EXCL); creates .claude/pipelines/ if missing. Caller checks Origin."""
    if not isinstance(req, dict):
        return 400, {"ok": False, "err": "bad body"}
    proj, name, title, tpl = req.get("proj"), req.get("name"), req.get("title") or "", req.get("template")
    if not _proj_ok(proj):
        return 403, {"ok": False, "err": "unknown project"}
    if not (isinstance(name, str) and _NAME.fullmatch(name)):
        return 400, {"ok": False, "err": "name must match ^[a-z0-9-]{1,40}$"}
    if not isinstance(title, str) or (title and not _one_line(title, 80)):
        return 400, {"ok": False, "err": "title: one line, <= 80 chars"}
    gone = []
    if isinstance(req.get("from"), dict):
        P, gone = _from_other(proj, name, title.strip(), req["from"])
        if P is None:
            return 400, {"ok": False, "err": gone}
    elif isinstance(tpl, str) and tpl.startswith(("suggest:", "std:")):
        std, k = tpl.startswith("std:"), tpl.split(":", 1)[1]       # ⚠drafts are rebuilt here; client-sent stages are ignored
        rows = suggest(proj, std=True) if std else [{"name": x["name"], "P": x, "gp": []} for x in suggest(proj)]
        P, gone = next(((x["P"], x["gp"]) for x in rows if x["name"] == k), (None, []))
        if P is None:
            return 400, {"ok": False, "err": "unknown suggestion"}
        P["name"] = name
        if title.strip():
            P["title"] = title.strip()
    elif tpl not in TEMPLATES:
        return 400, {"ok": False, "err": "unknown template"}
    else:
        P = _from_template(proj, name, title.strip(), tpl)
    errs = validate(P, name)
    if errs:
        return 400, {"ok": False, "err": "template invalid", "errs": errs[:20]}
    text, d = dump(P), _pipe_dir(proj)
    rel = ".claude/pipelines/%s.json" % name
    diff = "".join(difflib.unified_diff([], text.splitlines(True), "/dev/null", "b/" + rel))
    p = os.path.join(d, name + ".json")
    with _LOCK:
        if os.path.lexists(p):
            return 409, {"ok": False, "err": "%s already exists" % rel}
        if req.get("dry") is not False:
            return 200, {"ok": True, "dry": True, "diff": diff, "replaced": gone}
        try:
            os.makedirs(d, exist_ok=True)
            if os.path.realpath(d) != os.path.join(os.path.realpath(proj), ".claude", "pipelines"):
                return 400, {"ok": False, "err": "path leaves the project"}
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
        except FileExistsError:
            return 409, {"ok": False, "err": "%s already exists" % rel}
        except OSError as e:
            return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    return 200, {"ok": True, "dry": False, "diff": diff, "name": name, "sha": _sha(text)}
