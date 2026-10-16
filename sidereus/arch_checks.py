"""Security check results on the Architecture map: judging one scanner run, the checks file schema (gate), per-module
aggregation and the `/api/arch` `checks` loader (plans and parsers: sidereus/sec_checks.py).

⚠No subprocess here — Sidereus never runs a tool (AGENTS.md rule 7). The runner `scripts/arch_checks.py --category
security` (gate of `.claude/pipelines/security-checks.json`) executes the argv built by `sec_checks.detect()` and writes
arch/<key>/<commit>/checks-security.json. Only file / line / rule id / severity (+ package) are kept, never tool message
text. Stdlib only, Python 3.9.
"""
import os
import re

from sidereus.arch_verify import COMMIT_RE, owns, plan_globs, read_json, safe_rel
from sidereus.arch_checks_parse import SEVS, clean_help
from sidereus import sec_checks as SC

STATUSES = ("ok", "fail", "timeout", "missing", "skipped")
RULE_RE = re.compile(r"[A-Za-z0-9_./@:-]{1,60}")
WHY_MAX, ITEMS_MAX, TOP_MAX, FILES_MAX = 60, 300, 50, 20000
TOOL_TIMEOUT_S, TOTAL_S = 300, 900
OUT_MAX = 32 * 1024 * 1024         # bytes of stdout / one report parsed
WHY_OFFLINE = "dependencies not cached — run a normal build once"
OFFLINE_RE = re.compile(r"offline mode|No cached version|Could not resolve|failed to download|--offline", re.I)


def rel_path(p, repo, cwd=None):
    """Repo-relative path of a tool-reported path (absolute or relative to cwd), "" if outside the repo."""
    if not isinstance(p, str) or not p or "\0" in p:
        return ""
    a = os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd or repo, p))
    r = os.path.relpath(a, repo).replace(os.sep, "/")
    return "" if r.startswith("..") else safe_rel(r)


def judge(plan, res, repo):
    """(status, why|None, items, files) of one plan from the runner's result {rc, out, err, timeout, t0};
    files = files examined (0 unless ok)."""
    st, why, items = _judge(plan, res, repo)
    if st != "ok":
        return st, why, items, 0
    try:
        return st, why, items, SC.files(plan, res, repo)
    except ValueError:
        return st, why, items, 0


def _judge(plan, res, repo):
    if res.get("timeout"):
        return "timeout", "over %d s" % TOOL_TIMEOUT_S, []
    if res.get("rc") == 127 and res.get("nostart"):
        return "fail", "cannot start", []
    if SC.net_fail(plan, res):
        return "skipped", SC.WHY_NET_FAIL, []
    rc, blob = res.get("rc"), (res.get("out") or "") + (res.get("err") or "")
    parse = SC.PARSERS[plan["id"]]
    try:
        if plan["src"] == "report":
            raw = parse(SC.take_report(plan))
        else:
            raw = parse(res.get("err" if plan["src"] == "stderr" else "out") or "")
    except ValueError:
        return "fail", WHY_OFFLINE if OFFLINE_RE.search(blob) else "unreadable output (exit %s)" % rc, []
    ok_rc = plan.get("ok_rc", (0,))
    if ok_rc is not None and rc not in ok_rc and not raw:
        return "fail", WHY_OFFLINE if OFFLINE_RE.search(blob) else "exit %s" % rc, []
    items = []
    for x in raw:
        f = rel_path(x["file"], repo, plan.get("cwd"))
        if f and RULE_RE.fullmatch(x["rule"]) and os.path.isfile(os.path.join(repo, f)):
            items.append(dict(x, file=f, tool=plan["id"]))
    return "ok", None, items


def build(repo, commit, dirty, src_changed, at, tools, items):
    """checks.json v1 dict. tools = [{id, rules, status, why?, ms, files}] (n added here); items errors first, capped."""
    files, n = {}, {}
    for x in items:
        c = files.setdefault(x["file"], {"error": 0, "warning": 0})
        c[x["sev"]] += 1
        n.setdefault(x["tool"], {"error": 0, "warning": 0})[x["sev"]] += 1
    out_t = []
    for t in tools:
        e = {"id": t["id"], "rules": t["rules"], "status": t["status"], "ms": int(t.get("ms") or 0),
             "files": int(t.get("files") or 0), "n": n.get(t["id"], {"error": 0, "warning": 0})}
        if t.get("why"):
            e["why"] = t["why"][:WHY_MAX]
        out_t.append(e)
    its = sorted(items, key=lambda x: (x["sev"] != "error", x["file"], x["line"], x["tool"]))[:ITEMS_MAX]
    rules = {}
    for x in its:   # help only for rules that reach the stored items; first finding's metadata wins
        h = clean_help((x.get("help") or {}).get("desc"), (x.get("help") or {}).get("url"))
        if h:
            rules.setdefault(x["tool"] + ":" + x["rule"], h)
    return {"v": 1, "repo": repo, "commit": commit, "dirty": bool(dirty), "src_changed": bool(src_changed), "at": at,
            "tools": out_t, "files": dict(sorted(files.items())[:FILES_MAX]),
            "items": [dict({"tool": x["tool"], "file": x["file"], "line": x["line"], "rule": x["rule"], "sev": x["sev"]},
                           **({"pkg": x["pkg"]} if x.get("pkg") else {})) for x in its], "rules": rules}


# ── schema (gate) and page loader ──

def _nat(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def _cnt(c):
    return isinstance(c, dict) and set(c) == {"error", "warning"} and \
        all(isinstance(c[k], int) and not isinstance(c[k], bool) and c[k] >= 0 for k in SEVS)


def checks_errors(j, repo=None, commit=None, ids=()):
    """Strict schema errors of a checks file dict (gate; ids = SC.SEC_IDS for checks-security.json, none by default).
    Unknown keys are refused so no text can ride along."""
    if not isinstance(j, dict):
        return ["top level must be an object"]
    errs = []
    if set(j) - {"rules"} != {"v", "repo", "commit", "dirty", "src_changed", "at", "tools", "files", "items"}:
        errs.append("keys")
    rs = j.get("rules", {})
    if not isinstance(rs, dict) or len(rs) > ITEMS_MAX or any(_rule_key(k, ids) != k or not isinstance(v, dict)
                                                              or clean_help(v.get("desc"), v.get("url")) != v
                                                              for k, v in rs.items()):
        errs.append("rules")
    if j.get("v") != 1:
        errs.append("v must be 1")
    if not isinstance(j.get("repo"), str) or (repo and os.path.realpath(j.get("repo") or "") != os.path.realpath(repo)):
        errs.append("repo")
    if not (isinstance(j.get("commit"), str) and COMMIT_RE.fullmatch(j["commit"])) or (commit and j.get("commit") != commit):
        errs.append("commit")
    if not isinstance(j.get("at"), (int, float)) or isinstance(j.get("at"), bool):
        errs.append("at")
    for i, t in enumerate(j.get("tools") if isinstance(j.get("tools"), list) else [None]):
        if not (isinstance(t, dict) and set(t) - {"why"} == {"id", "rules", "status", "ms", "files", "n"}
                and t["id"] in ids and _nat(t["files"])
                and t["rules"] in ("project", "default") and t["status"] in STATUSES and _cnt(t["n"])
                and isinstance(t["ms"], int) and not isinstance(t["ms"], bool) and (not isinstance(t.get("why"), str) or len(t["why"]) <= WHY_MAX)
                and (t.get("why") is None or isinstance(t.get("why"), str))):
            errs.append("tools[%d]" % i)
    fs = j.get("files")
    if not isinstance(fs, dict) or any(safe_rel(k) != k or not _cnt(c) for k, c in fs.items()):
        errs.append("files")
    its = j.get("items")
    if not isinstance(its, list) or len(its) > ITEMS_MAX or any(_clean_item(x, ids) != x for x in its):
        errs.append("items")
    return errs


def _rule_key(k, ids=()):
    """`<tool>:<rule>` help key, "" if malformed (rules may contain ':' themselves, e.g. clippy::x)."""
    t, _c, r = k.partition(":") if isinstance(k, str) else ("", "", "")
    return k if t in ids and RULE_RE.fullmatch(r) else ""


def _clean_item(x, ids=()):
    if not isinstance(x, dict) or x.get("tool") not in ids or x.get("sev") not in SEVS:
        return None
    f, r, ln, pk = safe_rel(x.get("file")), x.get("rule"), x.get("line"), x.get("pkg")
    if not f or not (isinstance(r, str) and RULE_RE.fullmatch(r)) or not isinstance(ln, int) or isinstance(ln, bool) or ln < 0:
        return None
    if "pkg" in x and not (isinstance(pk, str) and SC.PKG_RE.fullmatch(pk)):
        return None
    return dict({"tool": x["tool"], "file": f, "line": ln, "rule": r, "sev": x["sev"]}, **({"pkg": pk} if "pkg" in x else {}))


def aggregate(files, mods, globs):
    """({module id: {error, warning}}, other) — each file counts for its first owning module, else `other`."""
    ms = [d for d in mods if isinstance(d, dict) and d.get("kind") == "module"]
    out, other = {}, {"error": 0, "warning": 0}
    for f, c in files.items():
        o = next((d["id"] for d in ms if owns(d, f, globs)), None)
        t = out.setdefault(o, {"error": 0, "warning": 0}) if o else other
        for k in SEVS:
            t[k] += c[k]
    return out, other


def _newest(rdir, name):
    best, at = "", -1.0
    try:
        names = os.listdir(rdir)
    except OSError:
        return ""
    for c in names:
        if COMMIT_RE.fullmatch(c):
            try:
                t = os.path.getmtime(os.path.join(rdir, c, name))
            except OSError:
                continue
            if t > at:
                best, at = c, t
    return best


def load_checks(root, map_dir, m, head=""):
    """`/api/arch` `checks`: an empty top-level shell (commit "", no tools; payload shape kept for the page) + `security`
    = newest checks-security.json of root's store (sibling commit dirs of map_dir), sanitised and rolled up onto the
    map's modules, `security.log` = sec_checks.log_view; None when there is neither a result nor a log."""
    s = _load_one(root, map_dir, m, head, SC.SEC_FILE, SC.SEC_IDS)
    lg = SC.log_view(os.path.dirname(map_dir))   # security history (status computed on read)
    if lg["at_scan"] is not None or lg["at_review"] is not None:
        s = dict(s or _shell(), log=lg)
    elif s:
        s["log"] = lg
    return dict(_shell(), security=s) if s else None


def _shell():
    return {"commit": "", "at": None, "stale": False, "dirty": False, "src_changed": False, "tools": [],
            "mods": {}, "other": {"error": 0, "warning": 0}, "top": [], "rules": {}}


def _load_one(root, map_dir, m, head, name, ids):
    rdir = os.path.dirname(map_dir)
    c = _newest(rdir, name)
    if not c:
        return None
    try:
        j = read_json(os.path.join(rdir, c, name))
    except (OSError, ValueError):
        return None
    if not isinstance(j, dict) or j.get("v") != 1 or j.get("commit") != c or not isinstance(j.get("repo"), str) \
            or os.path.realpath(j["repo"]) != os.path.realpath(root):
        return None
    tools = []
    for t in j.get("tools") if isinstance(j.get("tools"), list) else ():
        if isinstance(t, dict) and t.get("id") in ids and t.get("status") in STATUSES:
            n = t.get("n") if _cnt(t.get("n")) else {"error": 0, "warning": 0}
            ms = t.get("ms") if isinstance(t.get("ms"), int) and not isinstance(t.get("ms"), bool) else 0
            e = {"id": t["id"], "rules": "project" if t.get("rules") == "project" else "default", "status": t["status"],
                 "ms": ms, "files": t["files"] if _nat(t.get("files")) else 0, "n": {"error": n["error"], "warning": n["warning"]}}
            why = t.get("why")
            if isinstance(why, str) and why:
                e["why"] = "".join(ch for ch in why[:WHY_MAX] if ord(ch) >= 32)
            tools.append(e)
    fs = j.get("files") if isinstance(j.get("files"), dict) else {}
    files = {k: {"error": v["error"], "warning": v["warning"]} for k, v in list(fs.items())[:FILES_MAX]
             if safe_rel(k) == k and _cnt(v)}
    try:
        globs = plan_globs(read_json(os.path.join(map_dir, "plan.json")))
    except (OSError, ValueError):
        globs = {}
    mods_l = m.get("modules") if isinstance(m, dict) and isinstance(m.get("modules"), list) else []
    mods, other = aggregate(files, mods_l, globs)
    rs = j.get("rules") if isinstance(j.get("rules"), dict) else {}
    top, rules = [], {}
    for x in j.get("items") if isinstance(j.get("items"), list) else ():
        y = _clean_item(x, ids)
        if y:
            rk = y["tool"] + ":" + y["rule"]
            h = rs.get(rk) if _rule_key(rk, ids) else None
            h = clean_help(h.get("desc"), h.get("url")) if isinstance(h, dict) else None
            if h:
                rules[rk] = h
            top.append(dict(y, rk=rk if h else "", mod=next((d["id"] for d in mods_l if isinstance(d, dict)
                                                             and d.get("kind") == "module" and owns(d, y["file"], globs)), "")))
        if len(top) >= TOP_MAX:
            break
    at = j.get("at")
    return {"commit": c, "at": at if isinstance(at, (int, float)) and not isinstance(at, bool) else None,
            "stale": bool(head) and head != c, "dirty": j.get("dirty") is True, "src_changed": j.get("src_changed") is True,
            "tools": tools, "mods": mods, "other": other, "top": top, "rules": rules}
