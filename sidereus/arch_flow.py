"""Process flows over an arch map: S/flows.json (agent-written) checked at the stored commit -> S/flows.verify.json.

A flow = an entry point (HTTP route, CLI command, job, event) traced through map.json modules; each step cites the call
site in `from` (file/line/symbol). Steps reuse the edge checks of arch_verify (owner, overlap, evidence, nodef).
⚠Advisory only: flows never change the edge rate, the gate's exit code or map.md. Metadata only (no source text).
"""
import json
import os
import re
import subprocess

from sidereus import arch_verify as AV

FLOW_MAX, STEP_MAX = 40, 40
ENTRY_KINDS = ("http", "cli", "job", "event", "hook", "mcp")
ENTRY_MAX = 80
WHYS = ("nomod", "owner", "overlap", "nofile", "range", "nosym", "bad", "nodef", "noroute")
# Route mapping lines: Spring, JAX-RS, FastAPI/Flask/Express (`x.get(`, `.route(`, ...). Heuristic, line-based.
ROUTE_LINE_RE = re.compile(r"@(?:Request|Get|Post|Put|Delete|Patch)Mapping\b|@(?:Path|GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b"
                           r"|\.(?:get|post|put|delete|patch|route|api_route)\s*\(")
_CLASS_RE = re.compile(r"\b(?:class|interface|object)\s+[A-Za-z_]")
_LIT_RE = re.compile(r"([\"'`])(/[^\"'`]*)?\1")
_BARE_RE = re.compile(r"@[\w.]+\s*(?:\(\s*\))?")
_PREFIX_RE = re.compile(r"\b(?:url_)?prefix\s*=\s*([\"'])(/[^\"']*)?\1")


def _id(x):
    return isinstance(x, str) and bool(AV.ID_RE.fullmatch(x))


def _ev_ok(x):
    return isinstance(x, dict) and set(x) == {"file", "line", "symbol"} and AV._line(x["file"], AV.PATH_MAX) \
        and AV._int(x["line"]) and AV._line(x["symbol"], AV.SYM_MAX) and x["symbol"].strip() == x["symbol"]


def _step_ok(s):
    return isinstance(s, dict) and not set(s) - {"from", "to", "label", "evidence", "est", "to_evidence"} \
        and {"from", "to", "label", "evidence"} <= set(s) and _id(s["from"]) and _id(s["to"]) \
        and AV._line(s["label"], AV.NAME_MAX, empty=True) and _ev_ok(s["evidence"]) \
        and ("est" not in s or s["est"] in (0, 1)) and ("to_evidence" not in s or _ev_ok(s["to_evidence"]))


def _route_segs(s):
    """([(segment, is_param)], open_tail) of a URL/route: scheme+host dropped, ?/# cut, empty segments dropped."""
    s = str(s or "")
    if "://" in s:
        s = s.split("://", 1)[1]
        s = s[s.index("/"):] if "/" in s else ""
    s = re.split(r"[?#]", s, 1)[0]
    segs = [(x, any(c in x for c in "{:<$*")) for x in s.split("/") if x]
    return segs, s.endswith("/")


def _be_routes(lines, ln):
    """Route paths declared around 1-based line `ln`: class/router prefixes joined with the method paths of mapping lines
    within ±ARCH_K. ⚠Prefixes come from this file only (an Express mount in another file is not resolved)."""
    first = next((i for i, x in enumerate(lines) if _CLASS_RE.search(x)), -1)
    # ⚠Only annotations above the class are prefixes: an Express/FastAPI route above a later class is a method path.
    pre_ix = set(i for i in range(max(first, 0)) if ROUTE_LINE_RE.search(lines[i]) and lines[i].lstrip().startswith("@"))
    prefixes = [m.group(2) or "" for i in sorted(pre_ix) for m in _LIT_RE.finditer(lines[i])]
    prefixes += [m.group(2) or "" for x in lines for m in _PREFIX_RE.finditer(x)]
    methods = []
    for i in range(max(0, ln - 1 - AV.ARCH_K), min(len(lines), ln + AV.ARCH_K)):
        x = lines[i]
        if not ROUTE_LINE_RE.search(x):
            continue
        if i in pre_ix:                      # the cited line is the class mapping itself: prefix alone
            methods.append("")
            continue
        lits = [m.group(2) or "" for m in _LIT_RE.finditer(x)]
        # ⚠A non-literal argument (`value = CONST`) is unknown, not "": "" would let the bare class prefix match.
        methods += lits or ([""] if _BARE_RE.fullmatch(x.strip()) else [])
    return [p.rstrip("/") + "/" + mp.lstrip("/") for p in (prefixes or [""]) for mp in methods]


def route_match(fe, be):
    """FE call URL vs BE route, compared from the end: equal or a param on either side. Either side may carry extra
    leading segments (base path, context path); >= 1 literal pair must agree. An open FE tail (`/x/` + id) may leave
    param-only BE segments. ⚠Suffix heuristic, not router resolution."""
    fs, fo = _route_segs(fe)
    bs, _bo = _route_segs(be)
    tails = [0]
    if fo:
        while tails[-1] < len(bs) and bs[len(bs) - 1 - tails[-1]][1]:
            tails.append(tails[-1] + 1)
    for k in tails:
        b = bs[:len(bs) - k]
        n = min(len(fs), len(b))
        pairs = list(zip(fs[len(fs) - n:], b[len(b) - n:]))
        if n and all(f == g or fp or gp for (f, fp), (g, gp) in pairs) \
                and any(not fp and not gp for (f, fp), (g, gp) in pairs):
            return True
    return False


def _flow_ok(x):
    if not isinstance(x, dict) or set(x) != {"id", "name", "entry", "steps"}:
        return False
    en, st = x["entry"], x["steps"]
    return _id(x["id"]) and AV._line(x["name"], AV.NAME_MAX) and isinstance(en, dict) and set(en) == {"kind", "label"} \
        and en["kind"] in ENTRY_KINDS and AV._line(en["label"], ENTRY_MAX) \
        and isinstance(st, list) and 1 <= len(st) <= STEP_MAX and all(_step_ok(s) for s in st)


def flow_errors(f, repo=None, commit=None):
    """(file errors, kept flows, dropped count). A broken file keeps nothing; a broken or duplicate flow is dropped alone.
    Unknown keys are refused so the agent cannot smuggle content in."""
    if not isinstance(f, dict):
        return ["top level must be an object"], [], 0
    errs = []
    if set(f) - {"v", "repo", "commit", "flows"}:
        errs.append("unknown keys")
    if f.get("v") != 1 or not AV._int(f.get("v")):
        errs.append("v must be 1")
    if not AV._line(f.get("repo"), 4096) or (repo and os.path.realpath(f["repo"]) != os.path.realpath(repo)):
        errs.append("repo does not match the store")
    if not (isinstance(f.get("commit"), str) and AV.COMMIT_RE.fullmatch(f["commit"])) or (commit and f["commit"] != commit):
        errs.append("commit does not match the store")
    fl = f.get("flows")
    if not isinstance(fl, list) or len(fl) > FLOW_MAX:
        errs.append("flows: 0..%d" % FLOW_MAX)
    if errs:
        return errs, [], 0
    kept, ids = [], set()
    for x in fl:
        if _flow_ok(x) and x["id"] not in ids:
            ids.add(x["id"])
            kept.append(x)
    return [], kept, len(fl) - len(kept)


def verify_flows(repo, commit, m, flows, globs=None):
    """[{id, ok, steps:[{ok, why}]}] for schema-valid flows over a schema-valid map. Failing steps are marked, never
    removed; a flow is ok only if every step passes. Same evidence rules as arch_verify.verify_map (kind call)."""
    globs = globs or {}
    mods = {d["id"]: d for d in m["modules"]}
    try:
        tree = AV._tree(repo, commit)
    except (subprocess.SubprocessError, OSError):
        tree = set()
    memo = {}

    def read(rel):
        if rel not in memo:
            try:
                memo[rel] = AV._show(repo, commit, rel)
            except (subprocess.SubprocessError, OSError):
                memo[rel] = []
        return memo[rel]

    owners = AV._owners(tree, mods, globs)
    cont, _ov = AV.contested(tree, mods, globs, owners)
    dmemo, fmemo, gmemo, jmemo, facts = {}, {}, {}, {}, {}

    def owned(to):
        if to not in fmemo:
            fmemo[to] = set(f for f, ids in owners.items() if ids == [to])
        return fmemo[to]

    def grep(s):
        if s not in gmemo:
            gmemo[s] = AV._grep(repo, commit, s)
        return gmemo[s]

    def defined(to, sym, rel):
        # Base result per (to, sym); only the Java fallback depends on the evidence file (it must name the type).
        if (to, sym) not in dmemo:
            dmemo[(to, sym)] = AV.defined_base(sym, owned(to), read, grep)
        if dmemo[(to, sym)] or not rel:
            return dmemo[(to, sym)]
        if (to, sym, rel) not in jmemo:
            jmemo[(to, sym, rel)] = AV.java_generated(sym, owned(to), read, grep, read(rel), facts)
        return jmemo[(to, sym, rel)]

    def why(s):
        if s["from"] not in mods or s["to"] not in mods:
            return "nomod"
        x, rel = s["evidence"], AV.safe_rel(s["evidence"]["file"])
        if rel and not AV.owns(AV.owner_of(s, mods), rel, globs):
            return "owner"
        if rel in cont:
            return "overlap"
        w = AV.check_evidence(x, "call", tree, read)
        # Estimated (config/DI) steps and routes skip nodef, as config/di edges and URL symbols do in the map.
        both = s["from"] != s["to"] and mods[s["from"]].get("kind") == "module" and mods[s["to"]].get("kind") == "module"
        if w == "" and both and not s.get("est") and not AV.is_route(x["symbol"]) \
                and not AV.defined_or_alias(x["symbol"], rel, read, lambda y: defined(s["to"], y, rel),
                                           lambda: owned(s["to"])):
            return "nodef"
        # An HTTP hop (est or not) must cite the BE mapping in `to` whose route matches the FE URL.
        if w == "" and both and AV.is_route(x["symbol"]):
            return "" if http_ok(s) else "noroute"
        return w

    def http_ok(s):
        tev = s.get("to_evidence")
        trel = AV.safe_rel(tev["file"]) if tev else ""
        if not trel or trel not in owned(s["to"]) or AV.check_evidence(tev, "call", tree, read) != "":
            return False
        return any(route_match(s["evidence"]["symbol"], be) for be in _be_routes(read(trel), tev["line"]))

    out = []
    for fl in flows:
        steps = [{"ok": w == "", "why": w or None} for w in (why(s) for s in fl["steps"])]
        out.append({"id": fl["id"], "ok": all(x["ok"] for x in steps), "steps": steps})
    return out


def run(repo, commit):
    """Check S/flows.json, write S/flows.verify.json; returns the summary suffix (" · flows 5/7 (steps 31/36)"),
    "" when flows.json is absent or the map is not schema-valid. ⚠Never affects the gate's exit code."""
    try:
        d = AV.store_dir(repo, commit)
        m = AV.read_json(os.path.join(d, "map.json"))
    except (OSError, ValueError):
        return ""
    if AV.schema_errors(m, repo, commit):
        return ""
    fp = os.path.join(d, "flows.json")
    if not os.path.isfile(fp):
        return ""
    try:
        f = AV.read_json(fp)
    except (OSError, ValueError):
        return " · flows ignored (unreadable)"
    errs, flows, dropped = flow_errors(f, repo, commit)
    if errs:
        return " · flows ignored (invalid)"
    try:
        plan = AV.read_json(os.path.join(d, "plan.json"))
    except (OSError, ValueError):
        plan = {}
    res = verify_flows(repo, commit, m, flows, AV.plan_globs(plan))
    steps = [s for x in res for s in x["steps"]]
    passed = sum(1 for s in steps if s["ok"])
    v = {"v": 1, "commit": commit, "total": len(steps), "passed": passed,
         "rate": round(passed / len(steps), 4) if steps else 1.0, "flows": res, "dropped": dropped}
    AV._write(os.path.join(d, "flows.verify.json"), json.dumps(v, ensure_ascii=False) + "\n")
    line = " · flows %d/%d (steps %d/%d)" % (sum(1 for x in res if x["ok"]), len(res), passed, len(steps))
    return line + (" · %d flow(s) dropped" % dropped if dropped else "")


def load_flows(d, m, root, commit):
    """`/api/arch` `flows` for one store dir: flows.json re-checked and capped, joined with flows.verify.json verdicts
    by flow id + step index. A missing verdict reads ok:false, why:"unchecked"; an old store or invalid file gives []."""
    try:
        f = AV.read_json(os.path.join(d, "flows.json"))
    except (OSError, ValueError):
        return []
    errs, flows, _n = flow_errors(f, root, commit)
    if errs:
        return []
    try:
        v = AV.read_json(os.path.join(d, "flows.verify.json"))
    except (OSError, ValueError):
        v = {}
    vs = {}
    if isinstance(v, dict) and v.get("commit") == commit and isinstance(v.get("flows"), list):
        for x in v["flows"]:
            if isinstance(x, dict) and isinstance(x.get("id"), str) and isinstance(x.get("steps"), list):
                vs.setdefault(x["id"], x["steps"])
    mods = set(x["id"] for x in m["modules"])
    out = []
    for fl in flows:
        vx, steps = vs.get(fl["id"]) or [], []
        for i, s in enumerate(fl["steps"]):
            r = vx[i] if i < len(vx) and isinstance(vx[i], dict) else {}
            ok = r.get("ok") is True and s["from"] in mods and s["to"] in mods
            why = None if ok else (r.get("why") if r.get("why") in WHYS else ("nomod" if r.get("ok") is True else "unchecked"))
            ev = s["evidence"]
            steps.append({"from": s["from"], "to": s["to"], "label": s["label"][:AV.NAME_MAX], "est": 1 if s.get("est") else 0,
                          "ok": ok, "why": why, "evidence": {"file": ev["file"][:AV.PATH_MAX], "line": ev["line"],
                                                             "symbol": ev["symbol"][:AV.SYM_MAX]}})
        out.append({"id": fl["id"], "name": fl["name"][:AV.NAME_MAX],
                    "entry": {"kind": fl["entry"]["kind"], "label": fl["entry"]["label"][:ENTRY_MAX]},
                    "ok": all(s["ok"] for s in steps), "steps": steps})
    return out
