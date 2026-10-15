"""Architecture map: map.json v1/v2 schema (`schema_errors`) and the constants that bound it.

Split out of arch_verify (file-size cap); arch_verify re-exports every name here, so old imports keep working.
Stdlib only.
"""
import os
import re

MOD_MAX, EDGE_MAX, EV_MAX = 200, 600, 5
NAME_MAX, PATH_MAX, SYM_MAX = 60, 300, 120
KINDS = ("import", "call", "config", "di")
MOD_KINDS = ("module", "external")
EXTS = ("db", "auth", "api", "jar")
# v2: layers, groups, entry/store modules and data-flow edges. ⚠v1 maps keep the v1 rules exactly (new keys = unknown).
KINDS_V2, MOD_KINDS_V2 = KINDS + ("read", "write", "event", "serve"), MOD_KINDS + ("entry", "store")
LAYERS = ("entry", "ui", "api", "service", "domain", "data", "infra", "shared")
ENTRY_EXTS, STORE_EXTS = ("http", "hook", "mcp", "cli", "file", "job"), ("store", "file", "queue", "db")
GROUP_MAX, SUM_MAX, OWNS_MAX = 40, 120, 20
ROLE_LAYER = {"web": "api", "view": "ui", "viewmodel": "ui", "service": "service", "app": "service", "domain": "domain",
              "model": "domain", "port": "domain", "data": "data", "adapter": "infra", "shared": "shared"}
ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,60}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")   # full sha1 / sha256 only: it names a store directory
ROLES = ("web", "service", "data", "domain", "port", "adapter", "app", "view", "viewmodel", "model", "shared")


def _line(x, mx, empty=False):
    return isinstance(x, str) and len(x) <= mx and (empty or x != "") and "\n" not in x and "\r" not in x


def _int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _groups_errors(gs):
    """(errors, ids) for v2 `groups`: 1..GROUP_MAX of {id, name[, layer]}, ids unique."""
    if not isinstance(gs, list) or not 1 <= len(gs) <= GROUP_MAX:
        return ["groups: 1..%d" % GROUP_MAX], set()
    errs, ids = [], set()
    for i, g in enumerate(gs):
        ok = isinstance(g, dict) and {"id", "name"} <= set(g) <= {"id", "name", "layer"} and isinstance(g["id"], str)
        if not (ok and ID_RE.fullmatch(g["id"]) and g["id"] not in ids and _line(g["name"], NAME_MAX)
                and g.get("layer", "shared") in LAYERS):
            errs.append("groups[%d]: {id unique, name 1..%d, layer?: %s}" % (i, NAME_MAX, "|".join(LAYERS)))
        ids.add(g["id"] if ok else None)
    return errs, ids


def _mod_v2_errors(d, at, gids, kind_of):
    """v2-only module rules: layer, group, summary, owns (store ids), kind/ext/layer pairs, role vs layer."""
    lay, rl = d.get("layer"), ROLE_LAYER.get(d["role"]) if isinstance(d.get("role"), str) else None
    ext, ow, need = d.get("ext"), d.get("owns", []), {"entry": (ENTRY_EXTS, "entry"), "store": (STORE_EXTS, "data")}.get(d["kind"])
    bad = [(lay not in LAYERS, ".layer: " + "|".join(LAYERS)),
           (not (isinstance(d.get("group"), str) and d["group"] in gids), ".group: an id from groups"),
           ("summary" in d and not _line(d["summary"], SUM_MAX), ".summary: one line, 1..%d chars" % SUM_MAX),
           (bool(need) and (ext not in need[0] or lay != need[1]),
            ": %s needs ext %s and layer %s" % ((d["kind"],) + ("|".join(need[0]), need[1]) if need else ("", "", ""))),
           (not need and "ext" in d and ext not in EXTS, ".ext: db|auth|api|jar"),
           (not isinstance(ow, list) or len(ow) > OWNS_MAX or any(not isinstance(x, str) or kind_of.get(x) != "store"
                                                                  or x == d["id"] for x in ow), ".owns: <= %d store ids" % OWNS_MAX),
           (bool(rl) and lay in LAYERS and rl != lay, ": role %s needs layer %s" % (d.get("role"), rl))]
    return [at + msg for hit, msg in bad if hit]


def schema_errors(m, repo=None, commit=None):
    """Error list for a map.json dict (v1 or v2, by `v`). Unknown keys are refused so the agent cannot smuggle content in."""
    if not isinstance(m, dict):
        return ["top level must be an object"]
    v2 = m.get("v") == 2 and _int(m.get("v"))
    extra = set(m) - {"v", "repo", "commit", "modules", "edges"} - ({"groups"} if v2 else set())
    errs = ["unknown keys: %s" % sorted(extra)[:5]] if extra else []
    if not v2 and (m.get("v") != 1 or not _int(m.get("v"))):
        errs.append("v must be 1 or 2")
    ge, gids = _groups_errors(m.get("groups")) if v2 else ([], set())
    errs.extend(ge)
    if not _line(m.get("repo"), 4096):
        errs.append("repo: string")
    elif repo and os.path.realpath(m["repo"]) != os.path.realpath(repo):
        errs.append("repo does not match the store")
    if not (isinstance(m.get("commit"), str) and COMMIT_RE.fullmatch(m["commit"])):
        errs.append("commit: full hex id")
    elif commit and m["commit"] != commit:
        errs.append("commit does not match the store")
    mods = m.get("modules")
    ids, mkeys = set(), {"id", "name", "path", "kind", "ext", "role"} | ({"layer", "group", "summary", "owns"} if v2 else set())
    if not isinstance(mods, list) or not 1 <= len(mods) <= MOD_MAX:
        errs.append("modules: 1..%d" % MOD_MAX)
        mods = []
    kind_of = {d["id"]: d.get("kind") for d in mods if isinstance(d, dict) and isinstance(d.get("id"), str)}
    for i, d in enumerate(mods):
        at = "modules[%d]" % i
        if not isinstance(d, dict) or set(d) - mkeys or not {"id", "name", "path", "kind"} <= set(d):
            errs.append(at + ": keys id,name,path,kind[,ext,role]" + (" + layer,group[,summary,owns]" if v2 else ""))
            continue
        # ⚠A list/dict id or kind would raise TypeError below (set membership, dict lookup): refuse it first.
        nonstr = [k for k in ("id", "kind") if not isinstance(d[k], str)]
        if nonstr:
            errs.extend("%s.%s must be a string" % (at, k) for k in nonstr)
            continue
        if not ID_RE.fullmatch(d["id"]) or d["id"] in ids:
            errs.append(at + ".id: [A-Za-z0-9_.-]{1,60}, unique")
        ids.add(d["id"])
        if not _line(d["name"], NAME_MAX):
            errs.append(at + ".name: 1..%d chars" % NAME_MAX)
        if not _line(d["path"], PATH_MAX, empty=True):
            errs.append(at + ".path: <= %d chars" % PATH_MAX)
        if d["kind"] not in (MOD_KINDS_V2 if v2 else MOD_KINDS):
            errs.append(at + ".kind: " + "|".join(MOD_KINDS_V2 if v2 else MOD_KINDS))
        if v2:
            errs.extend(_mod_v2_errors(d, at, gids, kind_of))
        elif "ext" in d and d["ext"] not in EXTS:
            errs.append(at + ".ext: db|auth|api|jar")
        if "role" in d and d["role"] not in ROLES:
            errs.append(at + ".role: " + "|".join(ROLES))
    edges = m.get("edges")
    if not isinstance(edges, list) or len(edges) > EDGE_MAX:
        errs.append("edges: 0..%d" % EDGE_MAX)
        edges = []
    for i, e in enumerate(edges):
        at = "edges[%d]" % i
        if not isinstance(e, dict) or set(e) - {"from", "to", "kind", "label", "evidence", "est"} \
                or not {"from", "to", "kind", "label", "evidence"} <= set(e):
            errs.append(at + ": keys from,to,kind,label,evidence[,est]")
            continue
        nonstr = [k for k in ("from", "to", "kind") if not isinstance(e[k], str)]
        if nonstr:
            errs.extend("%s.%s must be a string" % (at, k) for k in nonstr)
            continue
        if e["from"] not in ids or e["to"] not in ids:
            errs.append(at + ": from/to must name a module id")
        if e["kind"] not in (KINDS_V2 if v2 else KINDS):
            errs.append(at + (".kind: " + "|".join(KINDS_V2) if v2 else ".kind: import|call|config|di"))
        elif e["kind"] in ("read", "write", "serve") and not (
                kind_of.get(e["to"]) == "store" if e["kind"] != "serve" else kind_of.get(e["from"]) == "entry"):
            errs.append(at + ": read/write must end at a store, serve start at an entry")
        # The owner check takes read/write evidence from `from` and serve evidence from `to`: that side must own files.
        if e["kind"] in ("read", "write") and v2 and kind_of.get(e["from"]) != "module":
            errs.append(at + ": read/write must start at a kind:module")
        elif e["kind"] == "serve" and v2 and kind_of.get(e["to"]) != "module":
            errs.append(at + ": serve must end at a kind:module")
        if not _line(e["label"], NAME_MAX, empty=True):
            errs.append(at + ".label: <= %d chars" % NAME_MAX)
        if "est" in e and e["est"] not in (0, 1):     # True/False compare equal to 1/0
            errs.append(at + ".est: 0|1")
        ev = e["evidence"]
        if not isinstance(ev, list) or not 1 <= len(ev) <= EV_MAX:
            errs.append(at + ".evidence: 1..%d" % EV_MAX)
            continue
        for k, x in enumerate(ev):
            if not (isinstance(x, dict) and set(x) == {"file", "line", "symbol"} and _line(x["file"], PATH_MAX)
                    and _int(x["line"]) and _line(x["symbol"], SYM_MAX) and x["symbol"].strip() == x["symbol"]):
                errs.append("%s.evidence[%d]: {file, line>=1, symbol}" % (at, k))
    return errs
