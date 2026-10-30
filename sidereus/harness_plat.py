"""Harness map per platform (GET /api/harness?plat=): cc = harness.harness(); cx/gm = the same row contract built from
the platform module's `harness_items()` and `LANE`.

⚠Metadata only, same as harness.py: hook commands leave as a script basename; env/args/url/header values from TOML or
  JSON never leave this module. Scripts are read only under the platform root · data dir · project · git root.
⚠settings.json / config.toml (and other config/credential files) are never openable — they can hold keys.
"""
import os
import re
import time

from sidereus import arch_verify, ctxsrc, harness, harness_evidence, harness_flow, harness_person, harness_trail, harness_verdict, sec_runtime, toolinv
from sidereus.config import DATA_DIR
from sidereus.ext_store import PLAT_MODS
from sidereus.ident import _real_home
from sidereus.pipeline_projects import _proj_ok

HP_MODS = {m.KEY: m for m in PLAT_MODS.values() if hasattr(m, "harness_items")}
HP_NO_OPEN = ("settings.json", "config.toml", "hooks.json", "auth.json", "oauth_creds.json", "google_accounts.json")
HP_REF = re.compile(r"(h:[A-Za-z0-9_]{1,60}:\d{1,4}|r:\d{1,4}|a:[A-Za-z0-9._-]{1,80}|s:\d{1,4})")
HP_VARS = re.compile(r"\$\{?(GEMINI_PROJECT_DIR|CLAUDE_PROJECT_DIR|CODEX_PROJECT_DIR)\}?")


def plats():
    """["cc"] + platform keys whose home folder exists (stat only)."""
    return ["cc"] + [k for k, m in HP_MODS.items() if os.path.isdir(m.root())]


def _roots(mod, proj):
    return [os.path.realpath(x) for x in (mod.root(), DATA_DIR, proj, ctxsrc._git_root(proj)) if x]


def _items(mod, proj):
    return [it for it in mod.harness_items(proj, ctxsrc._git_root(proj) or "") if isinstance(it, dict)]


def _script(cmd, proj):
    """Resolved script path of a hook command (platform project vars and ~ / $HOME = the real home)."""
    tok = HP_VARS.sub(lambda m: proj, harness._script_tok(cmd))
    tok = tok.replace("${HOME}", _real_home()).replace("$HOME", _real_home())
    if tok.startswith("~/"):
        tok = os.path.join(_real_home(), tok[2:])
    return harness._resolve(tok, proj, "")


def _hook_rows(mod, items, proj, paths=None):
    """[{ev (native), lane, hooks: [chip]}] in lane order (lane "" = «Other» last); `paths` collects ref -> script."""
    roots, by = _roots(mod, proj), {}
    for it in items:
        ev = str(it.get("ev") or "")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,60}", ev):
            continue
        c = it.get("cmd") if isinstance(it.get("cmd"), str) else ""
        sp = _script(c, proj) if c else ""
        eff, desc = harness._scan(sp, proj, roots) if c else (harness.EFF_UNKNOWN, "")
        ref = "h:%s:%d" % (ev, len(by.get(ev, [])))   # ⚠opaque index: the absolute path never goes in the row
        ok = eff in harness._OPEN_EFF and bool(sp) and harness._under(sp, roots)
        if paths is not None and ok:
            paths[ref] = sp
        to = it.get("timeout")
        by.setdefault(ev, []).append({"open": ref if ok else "", "scope": it.get("scope") or "", "src": it.get("scope") or "",
                                      "matcher": str(it.get("matcher") or "")[:harness.HN_CMD_MAX], "cmd": harness.cmd_name(c),
                                      "timeout": to if isinstance(to, (int, float)) and not isinstance(to, bool) else None,
                                      "eff": eff, "desc": desc, "n": None, "last": None, "plug": "", "on": it.get("on") is not False,
                                      "miss": int(bool(sp) and os.path.isabs(sp) and not os.path.exists(sp)),
                                      "ch": harness.hook_hash(sp + "\0" + c)[:8] if c else ""})   # dup key: resolved path + command, hashed
    lane = getattr(mod, "LANE", {})
    rank = dict((e, i) for i, e in enumerate(harness.EVENTS))
    order = sorted(by, key=lambda e: (rank.get(lane.get(e, ""), len(rank)), e))
    return [{"ev": e, "lane": lane.get(e, "") if lane.get(e, "") in rank else "", "hooks": by[e]} for e in order]


def _openable(p, proj, roots):
    if not p or not os.path.isfile(p) or os.path.basename(p) in HP_NO_OPEN:   # link name and target both checked
        return False
    rp = os.path.realpath(p)
    return harness._under(p, roots) and not rp.endswith((".jsonl", ".toml")) and os.path.basename(rp) not in HP_NO_OPEN


def _kind(items, k):
    return [it for it in items if it.get("kind") == k]


def _rows(mod, proj, items):
    roots = _roots(mod, proj)
    rules = [{"path": toolinv._abbrev(it["path"]), "size": toolinv._size(it["path"]),
              "order": i + 1, "open": "r:%d" % i if _openable(it["path"], proj, roots) else ""} for i, it in enumerate(_kind(items, "rule"))]
    agents = [{"name": str(it["name"])[:harness.TI_NAME], "scope": it["scope"], "pipes": [], "n": None,
               "open": "a:" + it["name"] if re.fullmatch(r"[A-Za-z0-9._-]{1,80}", str(it["name"])) and _openable(it["path"], proj, roots) else ""}
              for it in _kind(items, "agent")]
    mcps = [{"name": str(it["name"])[:harness.TI_NAME], "scope": it["scope"], "plug": str(it.get("plug") or "")[:harness.HN_CMD_MAX],
             "transport": it.get("transport") if it.get("transport") in ("stdio", "http", "sse") else "", "on": it.get("on") is not False,
             "n": None, "last": None, "status": "", "err": "", "fail_at": 0} for it in _kind(items, "mcp")]
    skills = [{"name": str(it["name"])[:harness.TI_NAME], "scope": it["scope"], "plug": "", "on": it.get("on") is not False,
               "n": None, "last": None, "open": "s:%d" % i if _openable(it["path"], proj, roots) else ""}
              for i, it in enumerate(_kind(items, "skill"))]
    counts = dict((k, sum(1 for it in _kind(items, k) if it.get("on") is not False)) for k in ("skill", "cmd", "mcp"))
    return rules, agents, mcps, skills, counts


def harness_evidence_only(proj):
    """(code, body) for GET /api/harness/evidence?proj= — gate evidence alone, so the pipeline view can label stages without the hook scan."""
    if not _proj_ok(proj):
        return 400, {"ok": False, "msg": "unknown project"}
    return 200, {"ok": True, "evidence": harness_evidence.recent(proj, 60), "commits": harness_evidence.commits(proj)}


def _results(proj):
    """«Results» keys: one evidence read feeds the list (newest 30) and the report (every row read); runtime = the
    stored patch card (sec_runtime, file read only — the viewer never looks versions up)."""
    ev, _floor = harness_evidence.scan(proj)
    rep, p = harness_trail.report(ev, proj), harness_person.person(proj)
    rep = dict(rep, counts=dict(rep["counts"], person=p["runs"]), person=p)   # ⚠copy: report() returns its cached dict
    return {"evidence": ev[:30], "report": rep, "guards": harness_flow.guards(proj),
            "runtime": sec_runtime.view(arch_verify.ARCH_DIR, time.time())}


def harness_plat(plat, proj, days=30):
    """(code, body) for GET /api/harness?plat=&proj=&days=. plat "" / cc = Claude Code (harness.harness)."""
    plat = plat or "cc"
    if plat != "cc" and plat not in HP_MODS:
        return 400, {"ok": False, "msg": "unknown platform"}
    if plat == "cc":
        code, body = harness.harness(proj, days)
        if code != 200:
            return code, body
        return code, harness_verdict.verdict(dict(body, plat="cc", plats=plats(), **_results(proj)), body.get("days", days))
    if not _proj_ok(proj):
        return 400, {"ok": False, "msg": "unknown project"}
    try:
        days = max(1, min(90, int(days or 30)))
    except (TypeError, ValueError):
        return 400, {"ok": False, "msg": "bad days"}
    mod = HP_MODS[plat]
    items = _items(mod, proj)
    rules, agents, mcps, skills, counts = _rows(mod, proj, items)
    return 200, harness_verdict.verdict({"ok": True, "plat": plat, "plats": plats(), "proj": proj, "days": days,
                                         "events": _hook_rows(mod, _kind(items, "hook"), proj), "rules": rules, "agents": agents,
                                         "counts": counts, "mcps": mcps, "skills": skills, "scanning": False,
                                         **_results(proj)}, days)


def _ref_path(mod, proj, ref):
    """Path for an `open` ref, re-derived from the platform config; "" when it names nothing openable."""
    kind, _, rest = ref.partition(":")
    items = _items(mod, proj)
    if kind == "h":
        paths = {}
        _hook_rows(mod, _kind(items, "hook"), proj, paths)
        return paths.get(ref, "")
    lst = {"r": _kind(items, "rule"), "s": _kind(items, "skill")}.get(kind)
    if lst is not None and rest.isdigit():
        i = int(rest)
        return lst[i]["path"] if i < len(lst) else ""
    if kind == "a":
        return next((it["path"] for it in _kind(items, "agent") if it["name"] == rest), "")
    return ""


def harness_plat_file(plat, proj, ref):
    """(code, body) for GET /api/harness/file?plat=&proj=&ref=. cc = harness.harness_file."""
    plat = plat or "cc"
    if plat == "cc":
        return harness.harness_file(proj, ref)
    if plat not in HP_MODS:
        return 400, {"ok": False, "msg": "unknown platform"}
    if not _proj_ok(proj):
        return 400, {"ok": False, "msg": "unknown project"}
    if not isinstance(ref, str) or not HP_REF.fullmatch(ref):
        return 400, {"ok": False, "msg": "bad ref"}
    mod = HP_MODS[plat]
    p = _ref_path(mod, proj, ref)
    cap = harness.HN_SCRIPT_MAX if ref.startswith("h:") else harness.HN_FILE_MAX
    # ⚠Symlinks may point anywhere: realpath under the roots, never config files or transcripts.
    if not _openable(p, proj, _roots(mod, proj)):
        return 404, {"ok": False, "msg": "No file to open."}
    try:
        if os.path.getsize(p) > cap:
            return 413, {"ok": False, "msg": "The file is too large."}
        with open(p, "rb") as f:
            raw = f.read(cap + 1)
    except OSError:
        return 404, {"ok": False, "msg": "File not found."}
    if len(raw) > cap:
        return 413, {"ok": False, "msg": "The file is too large."}
    if raw.startswith(harness._BIN_MAGIC) or b"\0" in raw[:4096]:
        return 415, {"ok": False, "msg": "Not a text file."}
    return 200, {"ok": True, "name": os.path.basename(p), "path": toolinv._abbrev(p), "text": raw.decode("utf-8", "replace"),
                 "lang": harness._LANG.get(os.path.splitext(p)[1].lower(), "")}
