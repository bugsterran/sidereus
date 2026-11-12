"""Overview (arch-brief) v2: a containment diagram — users/screens on top, one system container with 3-7 components and
2-4 design principles, 1-4 external systems on the right — plus one role line per box.

Checked against a v2 map.json (store/external kinds) and verify.json (edge verdicts); principle evidence is a file:line
at the commit. Called from sidereus/arch_brief.py when brief.json has v:2; v1 stays in arch_brief.py unchanged.
Stdlib only, imports arch_verify only; metadata only (ids, names, file:line — never cited source text).
Schema: FORMAT below (the one schema text; also sent with an «Ask the session to draw» request). Optional `layout`: arch_brief_layout.
"""
from sidereus import arch_verify as AV

ACTOR_MAX, SCREEN_MAX, COMP_MIN, COMP_MAX, PKG_MIN, PKG_MAX = 2, 2, 3, 7, 2, 6
PRIN_MIN, PRIN_MAX, EXT_MAX, USE_MAX, ARROW_MAX, AEDGE_MAX = 2, 4, 4, 3, 12, 5
TITLE_MAX, WHAT_MAX, HEAD_MAX, ACTOR_NAME_MAX, NAME_MAX, NOTE_MAX, ROLE_MAX = 60, 120, 40, 30, 40, 80, 100
PKG_NAME_MAX, PKG_NOTE_MAX, USE_NAME_MAX, USE_NOTE_MAX, LABEL_MAX, PRIN_TEXT_MAX = 24, 40, 30, 40, 32, 100
_KEYS = {"v", "repo", "commit", "title", "what", "heads", "actors", "screens", "system", "externals", "arrows", "layout"}
# ⚠Built from the caps above, so the schema text a session is sent cannot drift from what shape_errors refuses.
FORMAT = """brief.json v2: {v:2, repo, commit, title<=%(t)d, what<=%(w)d, heads?:{arch, legend}<=%(h)d,
  actors:[{id, name<=%(an)d}] 1..%(a)d, screens:[{id, name<=%(n)d, note<=%(no)d, role<=%(r)d, modules:[ids] 1..}] 1..%(s)d,
  system:{name<=%(n)d, components:[{id, name<=%(n)d, note<=%(no)d, role<=%(r)d, modules:[ids] 1..}
                                | {id, name<=%(n)d, note<=%(no)d, role<=%(r)d, pkgs:[{name<=%(pn)d, note?<=%(pt)d, modules:[ids] 1..}] %(p0)d..%(p1)d}] %(c0)d..%(c1)d
                                (<= 1 with pkgs),
          principles:[{text<=%(pr)d, evidence:{file, line}}] %(r0)d..%(r1)d},
  externals:[{id, name<=%(n)d, role<=%(r)d, uses:[{name<=%(un)d, note?<=%(ut)d}] 1..%(u)d, modules:[ids] 1..}] 1..%(e)d,
  arrows:[{from, to, label<=%(l)d, use?:1..%(u)d, edges:[map edge index] 1..%(ae)d}] <=%(ar)d, layout?}
modules = map.json module ids (stores/external systems only in externals); edges = verified map.json edges joining the two boxes;
evidence = file:line at the commit.
""" % {"t": TITLE_MAX, "w": WHAT_MAX, "h": HEAD_MAX, "an": ACTOR_NAME_MAX, "a": ACTOR_MAX, "n": NAME_MAX, "no": NOTE_MAX,
       "r": ROLE_MAX, "s": SCREEN_MAX, "pn": PKG_NAME_MAX, "pt": PKG_NOTE_MAX, "p0": PKG_MIN, "p1": PKG_MAX, "c0": COMP_MIN,
       "c1": COMP_MAX, "pr": PRIN_TEXT_MAX, "r0": PRIN_MIN, "r1": PRIN_MAX, "un": USE_NAME_MAX, "ut": USE_NOTE_MAX, "u": USE_MAX,
       "e": EXT_MAX, "l": LABEL_MAX, "ae": AEDGE_MAX, "ar": ARROW_MAX}
V2_MAP = "v2 overview needs a v2 map (store/external kinds); run arch-map"

_line, _int, ID_RE = AV._line, AV._int, AV.ID_RE


def _id(x):
    return isinstance(x, str) and bool(ID_RE.fullmatch(x))


def _mods(x):
    return isinstance(x, list) and 1 <= len(x) <= AV.MOD_MAX and all(isinstance(i, str) for i in x)


def _ev_ok(x):
    return isinstance(x, dict) and set(x) == {"file", "line"} and isinstance(x["file"], str) and _int(x["line"])


def _ev_errors(tag, ev, tree, read):
    """Errors of one {file, line} evidence at the commit (shared by v1 route rows and v2 principles).
    ⚠tree None = unknown: «commit tree unreadable», never «not in the commit»."""
    rel, ln = AV.safe_rel(ev["file"]), ev["line"]
    if not rel:
        return ["%s: unsafe evidence path" % tag]
    if tree is None:
        return ["%s: commit tree unreadable" % tag]
    if rel not in tree:
        return ["%s: %s not in the commit" % (tag, rel)]
    lines = read(rel)
    if lines is None:
        return ["%s: %s unreadable" % (tag, rel)]
    if not 1 <= ln <= len(lines):
        return ["%s: %s:%d outside 1..%d" % (tag, rel, ln, len(lines))]
    return []


def _list(b, key, lo, hi, errs):
    x = b.get(key)
    if not isinstance(x, list) or not lo <= len(x) <= hi:
        errs.append("%s: %d..%d%s" % (key, lo, hi, (" (got %d)" % len(x)) if isinstance(x, list) else ""))
        return []
    return x


def _box_ok(x, keys, extra=()):
    return isinstance(x, dict) and set(x) == set(keys) | set(extra) and _id(x["id"]) and _line(x["name"], NAME_MAX) \
        and ("note" not in x or _line(x["note"], NOTE_MAX)) and _line(x["role"], ROLE_MAX)


def _pkg_ok(p):
    return isinstance(p, dict) and {"name", "modules"} <= set(p) <= {"name", "note", "modules"} \
        and _line(p["name"], PKG_NAME_MAX) and ("note" not in p or _line(p["note"], PKG_NOTE_MAX)) and _mods(p["modules"])


def _use_ok(u):
    return isinstance(u, dict) and {"name"} <= set(u) <= {"name", "note"} and _line(u["name"], USE_NAME_MAX) \
        and ("note" not in u or _line(u["note"], USE_NOTE_MAX))


def shape_errors(b, repo, commit):
    """Schema errors of a v2 brief.json (no map/commit-file checks). Caps refuse, never truncate."""
    errs = []
    if set(b) - _KEYS:
        errs.append("unknown keys %s" % sorted(set(b) - _KEYS))
    if b.get("repo") != repo or b.get("commit") != commit:
        errs.append("repo/commit differ from the store dir")
    if not _line(b.get("title"), TITLE_MAX):
        errs.append("title: 1..%d chars" % TITLE_MAX)
    if not _line(b.get("what"), WHAT_MAX):
        errs.append("what: 1..%d chars" % WHAT_MAX)
    h = b.get("heads", {})
    if not isinstance(h, dict) or set(h) - {"arch", "legend"} or not all(_line(x, HEAD_MAX) for x in h.values()):
        errs.append("heads: {arch, legend} <= %d chars" % HEAD_MAX)
    for a in _list(b, "actors", 1, ACTOR_MAX, errs):
        if not (isinstance(a, dict) and set(a) == {"id", "name"} and _id(a["id"]) and _line(a["name"], ACTOR_NAME_MAX)):
            errs.append("actor: {id, name<=%d}" % ACTOR_NAME_MAX)
    for x in _list(b, "screens", 1, SCREEN_MAX, errs):
        if not (_box_ok(x, ("id", "name", "note", "role", "modules")) and _mods(x["modules"])):
            errs.append("screen: {id, name<=%d, note<=%d, role<=%d, modules:[ids] 1..}" % (NAME_MAX, NOTE_MAX, ROLE_MAX))
    s = b.get("system")
    if not isinstance(s, dict) or set(s) != {"name", "components", "principles"} or not _line(s.get("name"), NAME_MAX):
        errs.append("system: {name<=%d, components, principles}" % NAME_MAX)
        s = {}
    comps = _list(s, "components", COMP_MIN, COMP_MAX, errs) if s else []
    for x in comps:
        plain = _box_ok(x, ("id", "name", "note", "role", "modules")) and _mods(x["modules"])
        grp = _box_ok(x, ("id", "name", "note", "role", "pkgs")) and isinstance(x["pkgs"], list) \
            and PKG_MIN <= len(x["pkgs"]) <= PKG_MAX and all(_pkg_ok(p) for p in x["pkgs"])
        if not (plain or grp):
            errs.append("component: {id, name<=%d, note<=%d, role<=%d, modules:[ids] 1..} or {..., pkgs:[{name<=%d, "
                        "note?<=%d, modules}] %d..%d}" % (NAME_MAX, NOTE_MAX, ROLE_MAX, PKG_NAME_MAX, PKG_NOTE_MAX, PKG_MIN, PKG_MAX))
    if sum(1 for x in comps if isinstance(x, dict) and "pkgs" in x) > 1:
        errs.append("components: at most one with pkgs")
    for p in (_list(s, "principles", PRIN_MIN, PRIN_MAX, errs) if s else []):
        if not (isinstance(p, dict) and set(p) == {"text", "evidence"} and _line(p["text"], PRIN_TEXT_MAX) and _ev_ok(p["evidence"])):
            errs.append("principle: {text<=%d, evidence:{file, line}} — every principle cites file:line" % PRIN_TEXT_MAX)
    for x in _list(b, "externals", 1, EXT_MAX, errs):
        if not (_box_ok(x, ("id", "name", "role", "uses", "modules")) and _mods(x["modules"])
                and isinstance(x["uses"], list) and 1 <= len(x["uses"]) <= USE_MAX and all(_use_ok(u) for u in x["uses"])):
            errs.append("external: {id, name<=%d, role<=%d, uses:[{name<=%d, note?<=%d}] 1..%d, modules:[ids] 1..}"
                        % (NAME_MAX, ROLE_MAX, USE_NAME_MAX, USE_NOTE_MAX, USE_MAX))
    for a in _list(b, "arrows", 0, ARROW_MAX, errs):
        if not (isinstance(a, dict) and {"from", "to", "label", "edges"} <= set(a) <= {"from", "to", "label", "use", "edges"}
                and isinstance(a["from"], str) and isinstance(a["to"], str) and _line(a["label"], LABEL_MAX)
                and ("use" not in a or (_int(a["use"]) and 1 <= a["use"] <= USE_MAX))
                and isinstance(a["edges"], list) and 1 <= len(a["edges"]) <= AEDGE_MAX and all(_int(i) for i in a["edges"])):
            errs.append("arrow: {from, to, label<=%d (required), use?:1..%d, edges:[index] 1..%d}" % (LABEL_MAX, USE_MAX, AEDGE_MAX))
    return errs


def boxes(b):
    """[(id, kind, box, module ids)] for screens, components (pkg modules included) and externals, in drawing order."""
    out = [(x["id"], "screen", x, list(x["modules"])) for x in b["screens"]]
    for x in b["system"]["components"]:
        out.append((x["id"], "component", x, [i for p in x["pkgs"] for i in p["modules"]] if "pkgs" in x else list(x["modules"])))
    return out + [(x["id"], "external", x, list(x["modules"])) for x in b["externals"]]


def check(b, m, v, tree, read):
    """(errors, uncovered module count) for a shape-valid v2 brief. `tree`/`read` as in arch_brief.check."""
    if m.get("v") != 2:
        return [V2_MAP], 0
    kind_of = dict((d["id"], d["kind"]) for d in m["modules"])
    errs, seen, owner, mods = [], set(), {}, {}
    actors = set(a["id"] for a in b["actors"])
    for i in [a["id"] for a in b["actors"]] + [x[0] for x in boxes(b)]:
        if i in seen:
            errs.append("duplicate id %s" % i)
        seen.add(i)
    for bid, kind, _x, ms in boxes(b):
        mods[bid] = set(ms)
        for i in ms:
            k = kind_of.get(i)
            if k is None:
                errs.append("%s %s: unknown module %s" % (kind, bid, i))
                continue
            if i in owner and owner[i] != bid:
                errs.append("module %s in two boxes (%s, %s)" % (i, owner[i], bid))
            owner[i] = bid
            if kind == "external" and k not in ("store", "external"):
                errs.append("external %s: %s is kind %s, not store/external" % (bid, i, k))
            elif kind != "external" and k in ("store", "external"):
                errs.append("%s %s: %s is kind %s — stores and external systems go in externals" % (kind, bid, i, k))
    ext = dict((x["id"], x) for x in b["externals"])
    ok_ix = set(e["i"] for e in v["edges"] if isinstance(e, dict) and e.get("ok") is True and _int(e.get("i")))
    for a in b["arrows"]:
        tag = "arrow %s->%s" % (a["from"], a["to"])
        if a["from"] in actors or a["to"] in actors:
            errs.append("%s: actor endpoint (actor to screen is drawn, never an arrow)" % tag)
            continue
        if a["from"] not in mods or a["to"] not in mods:
            errs.append("%s: unknown box" % tag)
            continue
        if a["from"] == a["to"]:
            errs.append("%s: arrow to its own box" % tag)
            continue
        if a["from"] in ext and a["to"] in ext:
            errs.append("%s: arrow between two externals" % tag)
        if "use" in a and (a["to"] not in ext or a["use"] > len(ext[a["to"]]["uses"])):
            errs.append("%s: use %d needs an external target with that many uses" % (tag, a["use"]))
        for i in a["edges"]:
            if not 0 <= i < len(m["edges"]):
                errs.append("%s: edge %d does not exist" % (tag, i))
            elif i not in ok_ix:
                errs.append("%s: edge %d is not verified" % (tag, i))
            elif m["edges"][i]["from"] not in mods[a["from"]] or m["edges"][i]["to"] not in mods[a["to"]]:
                errs.append("%s: edge %d does not join these boxes" % (tag, i))
    for k, p in enumerate(b["system"]["principles"], 1):
        errs += _ev_errors("principle %d" % k, p["evidence"], tree, read)
    return errs, len(set(kind_of) - set(owner))


def ok_line(b, unc):
    return "ok · v2 · %d components · %d externals · %d arrows · %d principles · uncovered modules %d" % (
        len(b["system"]["components"]), len(b["externals"]), len(b["arrows"]), len(b["system"]["principles"]), unc)
