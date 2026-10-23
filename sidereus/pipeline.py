"""«Pipelines» view + edit (docs/dev/PIPELINE.md steps 2–3): GET /api/pipelines · POST /api/pipelines/save|create (delete: sidereus/pipeline_del.py, schema: sidereus/pipeline_schema.py).

Reads `<proj>/.claude/pipelines/*.json` for projects in `toolinv.known_projects()` and validates them with the same
rules as the fixed runner (`.claude/workflows/pipeline.js` validate block). Edits: the canvas editor (step 4) replaces
the whole stage list (name/v/title/rules/after kept); dry call = unified diff, second call writes after a backup to
DATA_DIR/pipeline-bak. GET sends stage `task` as `instr` (user-written config, edited in the node panel) but never
pipeline `rules`; neither is conversation (rule 1). Sidereus never runs a pipeline (rule 7).
"""
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import threading
import time

from sidereus import ctxsrc
from sidereus.config import ASSET_DIR, CODE_DIR, DATA_DIR
from sidereus.bus import _atomic_write
from sidereus.pipeline_projects import _proj_ok, _remembered, allowed_projects, apply_get, project_list
from sidereus.pipeline_schema import _AGENT, _COLOR, _NAME, GATE_MODES, MODELS, dump, validate
from sidereus.pipeline_std import std_drafts
from sidereus.stage_catalog import catalog
from sidereus.toolinv import agent_desc, agent_name, skill_names

PIPE_FILE_MAX = 64 * 1024
SAVE_BODY_MAX = 16 * 1024
BAK_DIR = None               # None = DATA_DIR/pipeline-bak; ⚠tests set a tmp dir
_LOCK = threading.Lock()
RUNNER = os.path.join(ASSET_DIR, ".claude", "workflows", "pipeline.js")   # DEFAULT_TASKS source of truth
_DT_RE = re.compile(r"// DEFAULT_TASKS-BEGIN\nconst DEFAULT_TASKS = (.*?)\n// DEFAULT_TASKS-END", re.S)


def default_tasks():
    """{title: default instruction} parsed from the runner (the same text it sends); {} if unreadable."""
    try:
        with open(RUNNER, encoding="utf-8") as f:
            m = _DT_RE.search(f.read())
        v = json.loads(m.group(1)) if m else {}
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def _bak_dir():
    return BAK_DIR or os.path.join(DATA_DIR, "pipeline-bak")


def _strftime(fmt):
    return time.strftime(fmt)            # tests patch this, not the time module


def _pipe_dir(proj):
    return os.path.join(proj, ".claude", "pipelines")


def _read_pipe(proj, name):
    """(raw text, parsed | None, error | None) for `<proj>/.claude/pipelines/<name>.json`, symlinks out of the dir refused."""
    d = _pipe_dir(proj)
    p = os.path.join(d, name + ".json")
    if os.path.dirname(os.path.realpath(p)) != os.path.realpath(d):
        return None, None, "path leaves .claude/pipelines"
    # ⚠A symlinked .claude or pipelines dir would let save write outside the project (same check as create).
    if os.path.realpath(d) != os.path.join(os.path.realpath(proj), ".claude", "pipelines"):
        return None, None, "path leaves the project"
    try:
        if os.path.getsize(p) > PIPE_FILE_MAX:
            return None, None, "file too large"
        with open(p, "rb") as f:
            raw = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return None, None, "unreadable (%s)" % type(e).__name__
    try:
        return raw, json.loads(raw, parse_constant=_no_const), None
    except ValueError as e:
        return raw, None, "not valid JSON (%s)" % e


def _no_const(c):
    raise ValueError("%s is not JSON" % c)


def _sha(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# Stage keys in file order for new keys (existing stages keep their own order — minimal diffs).
STAGE_KEYS = ("title", "agent", "task", "model", "skill", "retry", "gate", "parallel", "produces", "fanout", "onError",
              "onFail", "onlyOnJump", "ui")
_FAIL_KEYS = ("goto", "max", "then", "stopOn")
TITLE_MAX = 24              # a title typed in Sidereus; ⚠files may hold up to 40 (schema), only new titles are capped
_TITLE_BAD = re.compile(r"[/\]|\r\n\x00-\x1f]")   # «/» «]» break the [pl:name/title] tag, «|» the shell marker


def title_err(t):
    """Why a new stage title is refused, or "" (expects the trimmed value)."""
    if not isinstance(t, str) or not t:
        return "stage title: empty"
    if len(t) > TITLE_MAX:
        return "stage title: at most %d chars" % TITLE_MAX
    if _TITLE_BAD.search(t):
        return "stage title: no / ] | or line breaks"
    return ""


def _rename(P, old, new):
    """Stage `old` -> `new` in place, with every in-file reference (onFail goto/then, guards.requireGates)."""
    g = P.get("guards")
    if isinstance(g, dict) and isinstance(g.get("requireGates"), list):
        g["requireGates"] = [new if x == old else x for x in g["requireGates"]]
    for s in P["stages"]:
        if s.get("title") == old:
            s["title"] = new
        f = s.get("onFail")
        if isinstance(f, dict):
            for k in ("goto", "then"):
                if f.get(k) == old:
                    f[k] = new


def _stage_row(s):
    """Schema stage fields for the canvas editor (validated file only). `task` goes out as `instr`: it is the stage
    instruction a person wrote in this config file (editable in the node panel, step 4), not conversation text."""
    out = {k: s[k] for k in STAGE_KEYS if k in s and k != "task"}
    if "onFail" in out:
        out["onFail"] = {k: s["onFail"][k] for k in _FAIL_KEYS if k in s["onFail"]}
    if s.get("task"):
        out["instr"] = s["task"]
    return out


def _agent_files(proj):
    """[(name, scope, path)] from <proj>/.claude/agents/*.md then ~/.claude/agents/*.md; first name wins.
    ⚠Keyed like the Agent tool (toolinv.agent_name: frontmatter `name`, else file name), not by file name alone."""
    out, seen = [], set()
    for scope, d in (("project", os.path.join(proj, ".claude", "agents")), ("user", os.path.join(ctxsrc.CLAUDE_DIR, "agents"))):
        for p in sorted(glob.glob(os.path.join(d, "*.md"))):
            n = agent_name(p)
            if _AGENT.fullmatch(n) and n not in seen:
                seen.add(n)
                out.append((n, scope, p))
    return out


def _agents(proj):
    """[{name, scope, desc?}] — name plus the one-line frontmatter description (the path stays server-side, see _agent_files)."""
    out = []
    for n, scope, p in _agent_files(proj):
        row = {"name": n, "scope": scope}
        d = agent_desc(p)
        if d:
            row["desc"] = d
        out.append(row)
    return out


def _names(proj):
    return sorted(n for n in (os.path.basename(p)[:-5] for p in glob.glob(os.path.join(_pipe_dir(proj), "*.json")))
                  if _NAME.fullmatch(n))


def _listed(proj):
    """_names minus `"builtin": true` files (Sidereus plumbing, e.g. security-checks): hidden
    from the list and borrowed rows. ⚠They stay in .claude/pipelines — the pl_* hooks and gates resolve them there.
    ⚠Honoured only in the Sidereus repo (CODE_DIR): elsewhere the key would hide a user's file with no way to reach it."""
    if os.path.realpath(proj) != os.path.realpath(CODE_DIR):
        return _names(proj)
    return [n for n in _names(proj) if not _builtin(_read_pipe(proj, n)[1])]


def _builtin(P):
    return isinstance(P, dict) and P.get("builtin") is True


RULE_FILES = ("AGENTS.md", "CLAUDE.md")   # repo-root rule files offered as «Follow the project rule file» (names only)
_WF = re.compile(r"[A-Za-z0-9._-]{1,60}\.js")


def _rule_files(proj):
    return [f for f in RULE_FILES if os.path.isfile(os.path.join(proj, f))]


def _workflows(proj):
    """File names of <proj>/.claude/workflows/*.js — ⚠names only, the JS is never read (the session reads it)."""
    return sorted(n for n in (os.path.basename(p) for p in glob.glob(os.path.join(proj, ".claude", "workflows", "*.js")))
                  if _WF.fullmatch(n))


def _row(proj, n):
    raw, P, err = _read_pipe(proj, n)
    errs = [err] if err else validate(P, n)
    row = {"name": n, "ok": not errs, "errs": errs[:20]}
    if raw is not None:
        row["sha"] = _sha(raw)
    if not errs:
        row.update(title=P["title"], use=P.get("use", ""), rules=P.get("rules", ""), guards=P.get("guards") or {}, defaults={"model": P["defaults"]["model"], "retry": P["defaults"]["retry"]},
                   stages=[_stage_row(s) for s in P["stages"]], after=len(P.get("after") or []))
    return row


BORROW_MAX = 8   # borrowed rows per project


def _strs(v):
    return [x for x in v if isinstance(x, str) and x]


def runs_here(proj, rows, arch, arch_name):
    """[(pipeline name, [owner hint projects])] of runs attached to `proj`: the Sidereus tool run on it (`arch` = arch_map
    seen_runs, hints = its session's cwd + repos) and plrun runs of sessions whose cwd is `proj` (hints = run proj, cwd, repos).
    ⚠cwd only for plrun: a session listing Sidereus in `repos` would otherwise lend every pipeline it runs to Sidereus."""
    rows = [r for r in rows or () if isinstance(r, dict)]
    out = []
    a = (arch or {}).get(proj)
    if isinstance(a, dict):
        s = next((r for r in rows if a.get("sid") and r.get("sid") == a.get("sid")), {})
        out.append((arch_name, _strs([s.get("cwd")] + list(s.get("repos") or []))))
    for r in rows:
        if r.get("cwd") != proj:
            continue
        for x in r.get("plrun") or ():
            if isinstance(x, dict) and isinstance(x.get("name"), str):
                out.append((x["name"], _strs([x.get("proj"), r.get("cwd")] + list(r.get("repos") or []))))
    return out


def borrowed(proj, runs):
    """Read-only rows of pipelines `proj` runs but does not define, read from the owning project.
    Owner = the first hint that defines it (`why` "run"), else the first known project that does ("first")."""
    if not runs:
        return []   # ⚠allowed_projects() costs ~0.74 s cold; no runs = nothing to borrow
    local, names, out = set(_names(proj)), {}, []
    known = [p for p in allowed_projects() if p != proj]
    for name, hints in runs or ():
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in local or any(b["name"] == name for b in out):
            continue
        cands = [p for p in known if name in (names[p] if p in names else names.setdefault(p, _listed(p)))]
        own = next((h for h in hints if h in cands), "")
        why = "run" if own else "first"
        own = own or (cands[0] if cands else "")
        if own:
            # builtin = owned by the Sidereus repo itself (CODE_DIR, e.g. arch-map): labelled «Sidereus built-in», not «from <dir>»
            out.append(dict(_row(own, name), **{"from": own, "why": why, "builtin": os.path.realpath(own) == os.path.realpath(CODE_DIR)}))
    return out[:BORROW_MAX]


def pipelines(proj, runs=None):
    """(code, body) for GET /api/pipelines. No proj = known projects that have pipelines; else that project's list.
    `runs` = runs_here(...) for the read-only `borrowed` rows (none when omitted)."""
    if not proj:
        added = _remembered()
        allowed, selfp = project_list()
        projs = [dict({"path": p, "n": len(_listed(p))}, **({"self_only": True} if p == selfp else {})) for p in allowed if _listed(p) or p in added]
        return 200, {"ok": True, "projects": projs, "added": added}
    if not _proj_ok(proj):
        return 400, {"ok": False, "msg": "unknown project"}     # ⚠not 404: the page reads 404 as «feature off»
    rows = [_row(proj, n) for n in _listed(proj)]
    agents = _agents(proj)
    return 200, {"ok": True, "proj": proj, "pipelines": rows, "borrowed": borrowed(proj, runs), "agents": agents, "models": list(MODELS), "roles": _role_agents(proj, agents),   # names + one-line descriptions only, no paths (48c plgAddPreset)
                 "default_tasks": default_tasks(), "catalog": catalog(), "gate_modes": [rx for rx, _m in GATE_MODES], "skills": skill_names(proj), "rule_files": _rule_files(proj), "workflows": _workflows(proj),
                 "suggest": [_draft_row(P, suggest=True) for P in suggest(proj)], "apply": apply_get(proj),
                 "std": [_draft_row(d["P"], std=True, src=d["src"], chain=d["chain"], gp=d["gp"]) for d in suggest(proj, std=True)]}


def _draft_row(P, **kw):
    return dict(name=P["name"], ok=True, errs=[], title=P["title"], use=P.get("use", ""), rules=P["rules"], defaults=P["defaults"],
                stages=[_stage_row(x) for x in P["stages"]], after=0, **kw)


def _apply(P, req):
    """New dict with the allowed edits applied; ValueError on anything else. `model: ""` = drop stage.model."""
    new = json.loads(json.dumps(P))
    dm = req.get("defaults")
    if dm is not None:
        if not isinstance(dm, dict) or set(dm) - {"model"}:
            raise ValueError("defaults: only model may change")
        if "model" in dm:
            new["defaults"]["model"] = dm["model"]
    edits = req.get("stages") or {}
    if not isinstance(edits, dict):
        raise ValueError("stages must be {title: {agent, model, title}}")
    by = {s["title"]: s for s in new["stages"]}
    for t, e in edits.items():
        if t not in by:
            raise ValueError("no stage %s" % str(t)[:40])
        if not isinstance(e, dict) or set(e) - {"agent", "model", "title"}:
            raise ValueError("stage %s: only agent, model and title may change" % t)
        s = by[t]
        if "agent" in e:
            s["agent"] = e["agent"]
        if "model" in e:
            if e["model"] == "":
                s.pop("model", None)
            elif "model" in s:
                s["model"] = e["model"]
            else:   # keep the file's key order: model goes right after agent
                items = list(s.items())
                k = [a for a, _ in items].index("agent") + 1
                s.clear()
                s.update(items[:k] + [("model", e["model"])] + items[k:])
    ren = {}
    for t, e in edits.items():
        if "title" in e:
            nt = e["title"].strip() if isinstance(e["title"], str) else None
            err = title_err(nt)
            if err:
                raise ValueError(err)
            if nt != t:
                ren[t] = nt
    final = [ren.get(s["title"], s["title"]) for s in new["stages"]]
    if len(set(final)) != len(final):
        raise ValueError("stage title: already used in this pipeline")
    tmp = {t: "\x00%d" % i for i, t in enumerate(ren)}   # two steps: a swap (A->B, B->A) must not merge
    for t, x in tmp.items():
        _rename(new, t, x)
    for t, x in tmp.items():
        _rename(new, x, ren[t])
    return new


def _empty(v):
    return v is None or v is False or (isinstance(v, str) and v == "")


def _replace(P, req):
    """Canvas save: the whole stage list (+ defaults model/retry) replaces the file's; name/v/title/after are kept.
    Only schema keys pass (`instr` -> `task`); empty values drop the key. ValueError on shape errors."""
    new = json.loads(json.dumps(P))
    dm = req.get("defaults")
    if dm is not None:
        if not isinstance(dm, dict) or set(dm) - {"model", "retry"}:
            raise ValueError("defaults: only model and retry may change")
        new["defaults"].update(dm)
    # user-written config; "" drops the key, a new key goes after title (use before rules)
    for key, r in [(x, req[x]) for x in ("use", "rules") if x in req]:
        if not isinstance(r, str):
            raise ValueError("%s must be a string" % key)
        if key in new and r.strip():
            new[key] = r            # keeps its place
            continue
        items = [kv for kv in new.items() if kv[0] != key]
        k = next((i + 1 for i, (a, _) in enumerate(items) if a == ("use" if key == "rules" and "use" in new else "title")), len(items))
        new.clear()
        new.update(items[:k] + ([(key, r)] if r.strip() else []) + items[k:])
    if "guards" in req:   # run guards (editor «Guards» pane); {} drops the key; shape is checked by validate()
        g = req["guards"]
        if not isinstance(g, dict):
            raise ValueError("guards must be an object")
        if g:
            new["guards"] = g
        else:
            new.pop("guards", None)
    rows = req["stages"]
    if len(rows) > 20:
        raise ValueError("stages: at most 20")
    old = {s["title"]: s for s in P["stages"]}
    out = []
    seen = set()
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("stage must be an object")
        r = dict(r)
        if "instr" in r:
            r["task"] = r.pop("instr")
        if isinstance(r.get("ui"), dict) and "color" in r["ui"] and not (isinstance(r["ui"]["color"], str) and _COLOR.fullmatch(r["ui"]["color"])):
            r["ui"] = {k: v for k, v in r["ui"].items() if k != "color"}   # a bad colour is dropped, not an error
        bad = set(r) - set(STAGE_KEYS)
        if bad:
            raise ValueError("unknown stage key %s" % ", ".join(sorted(bad))[:80])
        if isinstance(r.get("onFail"), dict) and set(r["onFail"]) - set(_FAIL_KEYS):
            raise ValueError("unknown onFail key")
        r = {k: v for k, v in r.items() if not _empty(v) or k == "title"}   # ⚠not `in (None, "", False)`: 0 == False
        if isinstance(r.get("onFail"), dict):
            r["onFail"] = {k: v for k, v in r["onFail"].items() if not _empty(v) or k == "stopOn"}
        if isinstance(r.get("title"), str):
            r["title"] = r["title"].strip()
        if r.get("title") not in old and title_err(r.get("title")):   # a renamed/new stage; existing titles stay as they are
            raise ValueError(title_err(r.get("title")))
        if r.get("title") in seen:
            raise ValueError("stage title: already used in this pipeline")
        seen.add(r.get("title"))
        prev = old.get(r.get("title")) or {}
        keys = [k for k in prev if k in r] + [k for k in STAGE_KEYS if k in r and k not in prev]
        out.append({k: r[k] for k in keys})
    new["stages"] = out
    return new


def save(req):
    """(code, body) for POST /api/pipelines/save {proj, name, base, dry, defaults?, stages?}. ⚠Caller checks Origin.
    `stages` list = canvas save (whole stage list); dict = per-stage agent/model edits (step 2a)."""
    if not isinstance(req, dict):
        return 400, {"ok": False, "err": "bad body"}
    proj, name = req.get("proj"), req.get("name")
    if not _proj_ok(proj):
        return 403, {"ok": False, "err": "unknown project"}
    if not (isinstance(name, str) and _NAME.fullmatch(name)):
        return 400, {"ok": False, "err": "bad name"}
    with _LOCK:
        raw, P, err = _read_pipe(proj, name)
        if err:
            return 400, {"ok": False, "err": err}
        if validate(P, name):
            return 400, {"ok": False, "err": "file is invalid now — fix it by hand"}
        if req.get("base") != _sha(raw):
            return 409, {"ok": False, "err": "file changed since it was loaded — reload"}
        try:
            new = _replace(P, req) if isinstance(req.get("stages"), list) else _apply(P, req)
        except (ValueError, KeyError) as e:
            return 400, {"ok": False, "err": str(e)[:200]}
        errs = validate(new, name)
        if errs:
            return 400, {"ok": False, "err": "invalid after edit", "errs": errs[:20]}
        # a new/changed stage skill must be installed; an unchanged one is kept even if uninstalled since
        old_sk = {s.get("title"): s.get("skill") for s in P["stages"]}
        have = None
        for s in new["stages"]:
            sk = s.get("skill")
            if sk and sk != old_sk.get(s.get("title")):
                have = {x["name"] for x in skill_names(proj)} if have is None else have
                if sk not in have:
                    return 400, {"ok": False, "err": "unknown skill %s" % sk}
        text = dump(new)
        rel = ".claude/pipelines/%s.json" % name
        diff = "".join(difflib.unified_diff(raw.splitlines(True), text.splitlines(True), "a/" + rel, "b/" + rel))
        if new == P:
            return 400, {"ok": False, "err": "no change"}
        if req.get("dry") is not False:
            return 200, {"ok": True, "dry": True, "diff": diff}
        p = os.path.join(_pipe_dir(proj), name + ".json")
        try:
            bak = _backup(p, proj, name)
            _atomic_write(p, text.encode("utf-8"), prefix=".sidereus-tmp.", like=p)   # keep the repo file's mode
        except OSError as e:
            return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    return 200, {"ok": True, "dry": False, "diff": diff, "backup": bak, "sha": _sha(text)}


def _backup(p, proj, name, move=False):   # move = delete (sidereus/pipeline_del.py); ⚠shutil.move: other volume possible
    base = os.path.join(_bak_dir(), _strftime("%Y%m%d-%H%M%S"))
    d, n = base, 1
    while os.path.exists(d):
        n += 1
        d = "%s-%d" % (base, n)
    os.makedirs(d)
    dst = os.path.join(d, "%s--%s.json" % (re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(proj.rstrip("/"))), name))
    (shutil.move if move else shutil.copy2)(p, dst)
    return dst


# «Suggested»: pipelines guessed from agent NAMES only
# (no file content, no AI); shown unsaved, written only through pipeline_new.create() after preview + «Confirm».
_ROLES = (("triage", r"triage"), ("design", r"design|spec"), ("fix", r"fix"), ("build", r"implement|(^|-)(be|fe)($|-)|dev"),
          ("check", r"(^|-)gate|verifier|(^|-)qa"), ("review", r"review"), ("live", r"live|verify"), ("probe", r"probe|measure"),
          ("ux", r"(^|-)ux($|-)"))


def _role_agents(proj, agents):
    """role -> agent. Tier 1: the project's own .claude/agents. Tier 2: global agents named `<dir name>-*` or sharing the
    first segment of a project agent (ledger-* when the project has ledger-*.md). ⚠No shorter fallback such as «cart-»:
    that picked other projects' agents (★2026-10-01 live check, cart-agent got cart-api-*). No match = no stage."""
    base = os.path.basename(os.path.normpath(proj)).lstrip(".").lower()
    own = [a for a in agents if a.get("scope") == "project"]
    pre = {a["name"].split("-")[0] + "-" for a in own if "-" in a["name"]}
    glob_ok = [a for a in agents if a.get("scope") != "project"
               and ((base and a["name"].startswith(base + "-")) or any(a["name"].startswith(x) for x in pre))]
    out = {}
    for role, rx in _ROLES:
        for tier in (own, glob_ok):
            hits = sorted((a["name"] for a in tier if re.search(rx, a["name"])),
                          key=lambda n: (0 if base and n.startswith(base + "-") else 1, n))
            if hits:
                out[role] = hits[0]
                break
    return out


def _tail(R, back):
    """check / review / live stages after the fix or build stage `back` (loop-backs return there)."""
    st = []
    if "check" in R:
        st.append({"title": "검증", "agent": R["check"], "model": "sonnet", "onFail": {"goto": back, "max": 2}})
    if "review" in R:
        st.append({"title": "리뷰", "agent": R["review"], "onFail": {"goto": back, "max": 1}})
    if "live" in R:
        st.append({"title": "라이브 검증", "agent": R["live"], "onFail": {"goto": back, "max": 1}})
    return st


def suggest(proj, agents=None, std=False):
    """[pipeline dict] (at most 2, each validated) for a project, from its agent names. std = the valid per-task standard
    drafts instead ([{name, title, src, chain, gp, P}], sidereus/pipeline_std.py)."""
    ags = _agents(proj) if agents is None else agents
    R = _role_agents(proj, ags)
    rules = ["Follow %s in the repo." % f for f in _rule_files(proj)] + ["Never commit or push."]
    if std:   # agents the project's saved pipelines already use win (cart-code-review is not cart-api-*)
        used = {s.get("agent") for n in _names(proj) for s in ((_read_pipe(proj, n)[1] or {}).get("stages") or [])}
        R = dict(R, **_role_agents("", [dict(a, scope="project") for a in ags if a.get("name") in used]))
        tasks = {t["title"]["ko"]: t["instr"] for t in catalog()["items"] if t.get("instr")}
        return [d for d in std_drafts(R, rules, tasks) if not validate(d["P"], d["name"])]
    cands = []
    if "fix" in R:
        st = ([{"title": "트리아지", "agent": R["triage"]}] if "triage" in R else []) + [
            {"title": "재현", "agent": R.get("probe", R["fix"])}, {"title": "원인", "agent": R["fix"]}, {"title": "수정", "agent": R["fix"]}]
        cands.append(("bugfix", "버그 수정", st + _tail(R, "수정")))
    if "build" in R:
        st = ([{"title": "설계", "agent": R["design"], "produces": "slices"}] if "design" in R else [])
        st.append(dict({"title": "구현", "agent": R["build"]}, **({"fanout": "slices", "onError": "continue"} if "design" in R else {})))
        cands.append(("change", "변경", st + _tail(R, "구현")))
    out = []
    for key, title, st in cands:
        P = {"v": 1, "name": key, "title": title, "rules": "\n".join(rules), "defaults": {"model": "inherit", "retry": 0}, "stages": st}
        if not validate(P, key):
            out.append(P)
    return out
