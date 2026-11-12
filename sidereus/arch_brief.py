"""Overview (arch-brief): a one-page architecture brief drawn on top of a finished arch-map result.

An agent groups map.json modules into <= 12 boxes in bands and writes the decision order (how a request is routed
to a domain) as `brief.json`; this gate checks every box/arrow/evidence against map.json, verify.json and the commit,
then writes `brief.html` (sidereus/arch_brief_html.py). Same store dir as arch-map (arch_verify.store_dir).
Pointer: ARCH_DIR/_brief_last.json {repo, commit, ok} — arch-map's _last.json is never touched.
CLI wrapper: scripts/arch_brief.py. Stdlib only; metadata only (ids, names, file:line — never cited source text).

brief.json v1: {v:1, repo, commit, title<=80, heads?:{arch<=40, route<=40}, bands:[{id, name<=40, note?<=80}] 1..4 top to bottom,
  boxes:[{id, name<=40, band, note?<=80, modules:[map ids] 1..}] 1..12,
  arrows:[{from, to, label?<=40, edges:[map.json edge index] 1..5}] <=24,
  route: {na:<=120} | {by<=80, rows:[{when<=80, goes<=120, box?, evidence:{file, line}}] 1..16}}
brief.json v2 (containment: screens · components · externals · principles): schema, check and renderer in arch_brief_v2 / arch_brief_html_v2.
"""
import hashlib
import json
import os
import subprocess

from sidereus import arch_verify as AV
from sidereus import arch_brief_html as AH
from sidereus import arch_brief_html_v2 as AH2
from sidereus import arch_brief_v2 as B2

BOX_MAX, BAND_MAX, ARROW_MAX, AEDGE_MAX, ROW_MAX = 12, 4, 24, 5, 16
TITLE_MAX, NAME_MAX, NOTE_MAX, HEAD_MAX, WHEN_MAX, GOES_MAX, NA_MAX, BY_MAX = 80, 40, 80, 40, 80, 120, 120, 80
SAME_LABEL_MAX = 4        # arrows into one box sharing a label: from here on the gate refuses them
_KEYS = {"v", "repo", "commit", "title", "heads", "bands", "boxes", "arrows", "route"}

_line, _int, ID_RE = AV._line, AV._int, AV.ID_RE


def _fold(s):
    return s.strip().casefold()


def _pointer(repo, commit, ok):
    os.makedirs(AV.ARCH_DIR, exist_ok=True)
    AV._write(os.path.join(AV.ARCH_DIR, AV.BRIEF_LAST),
              json.dumps({"repo": repo, "commit": commit, "ok": bool(ok)}, ensure_ascii=False) + "\n")


def _map_ready(repo, commit):
    """(map, verdict) of a finished arch-map run for (repo, commit), or None."""
    try:
        d = AV.store_dir(repo, commit)
        m = AV.read_json(os.path.join(d, "map.json"))
        v = AV.read_json(os.path.join(d, "verify.json"))
    except (OSError, ValueError):
        return None
    if AV.schema_errors(m, repo, commit) or not isinstance(v, dict) or not isinstance(v.get("edges"), list):
        return None
    return m, v


def pre(repo):
    """Stage «Prepare»: resolve HEAD, require a finished arch-map result, rewrite the pointer. (rc, line)."""
    repo = os.path.realpath(repo)
    if not os.path.isdir(repo):
        return 1, "arch_brief: repo is not a directory"
    head = AV.head_of(repo)
    if not head:
        _pointer(repo, "", False)
        return 1, "arch_brief: %s has no readable HEAD" % repo
    ok = _map_ready(repo, head) is not None
    _pointer(repo, head, ok)
    if not ok:
        return 1, "arch_brief: no arch-map result for %s at %s; run arch-map first" % (repo, head[:7])
    return 0, "arch_brief: ready %s · S=%s" % (head[:7], AV.store_dir(repo, head))


def last():
    """(repo, commit, ok) from the pointer; raises ValueError when unreadable."""
    try:
        j = AV.read_json(os.path.join(AV.ARCH_DIR, AV.BRIEF_LAST))
    except (OSError, ValueError):
        raise ValueError("%s unreadable; run --pre first" % AV.BRIEF_LAST)
    if not isinstance(j, dict) or not isinstance(j.get("repo"), str) or not isinstance(j.get("commit"), str):
        raise ValueError("%s malformed" % AV.BRIEF_LAST)
    return j["repo"], j["commit"], j.get("ok") is True


def shape_errors(b, repo, commit):
    """Schema errors of brief.json (no map/commit checks)."""
    if not isinstance(b, dict):
        return ["brief.json is not an object"]
    if b.get("v") == 2 and _int(b.get("v")):
        return B2.shape_errors(b, repo, commit)
    errs = []
    if set(b) - _KEYS:
        errs.append("unknown keys %s" % sorted(set(b) - _KEYS))
    if b.get("v") != 1:
        errs.append("v must be 1")
    if b.get("repo") != repo or b.get("commit") != commit:
        errs.append("repo/commit differ from the store dir")
    if not _line(b.get("title"), TITLE_MAX):
        errs.append("title: 1..%d chars" % TITLE_MAX)
    h = b.get("heads", {})
    if not isinstance(h, dict) or set(h) - {"arch", "route"} or not all(_line(x, HEAD_MAX) for x in h.values()):
        errs.append("heads: {arch, route} <= %d chars" % HEAD_MAX)
    bands, boxes, arrows = b.get("bands"), b.get("boxes"), b.get("arrows", [])
    if not isinstance(bands, list) or not 1 <= len(bands) <= BAND_MAX:
        errs.append("bands: 1..%d" % BAND_MAX)
        bands = []
    if not isinstance(boxes, list) or not boxes:
        errs.append("boxes: at least 1")
        boxes = []
    elif len(boxes) > BOX_MAX:
        errs.append("too many boxes: %d > %d" % (len(boxes), BOX_MAX))
    if not isinstance(arrows, list) or len(arrows) > ARROW_MAX:
        errs.append("arrows: at most %d" % ARROW_MAX)
        arrows = []
    for x in bands:
        if not isinstance(x, dict) or set(x) - {"id", "name", "note"} or not {"id", "name"} <= set(x) \
                or not (isinstance(x["id"], str) and ID_RE.fullmatch(x["id"])) or not _line(x["name"], NAME_MAX) \
                or ("note" in x and not _line(x["note"], NOTE_MAX)):
            errs.append("band: {id, name<=%d, note?<=%d}" % (NAME_MAX, NOTE_MAX))
    for x in boxes:
        if not isinstance(x, dict) or set(x) - {"id", "name", "band", "note", "modules"} \
                or not (isinstance(x.get("id"), str) and ID_RE.fullmatch(x["id"])) or not _line(x.get("name"), NAME_MAX) \
                or not isinstance(x.get("band"), str) \
                or ("note" in x and not _line(x["note"], NOTE_MAX)) or not isinstance(x.get("modules"), list) \
                or not x["modules"] or not all(isinstance(i, str) for i in x["modules"]):
            errs.append("box: {id, name<=%d, band, note?<=%d, modules:[ids] 1..}" % (NAME_MAX, NOTE_MAX))
    for a in arrows:
        if not isinstance(a, dict) or set(a) - {"from", "to", "label", "edges"} \
                or not isinstance(a.get("from"), str) or not isinstance(a.get("to"), str) \
                or ("label" in a and not _line(a["label"], NAME_MAX)) or not isinstance(a.get("edges"), list) \
                or not 1 <= len(a["edges"]) <= AEDGE_MAX or not all(_int(i) for i in a["edges"]):
            errs.append("arrow: {from, to, label?<=%d, edges:[index] 1..%d}" % (NAME_MAX, AEDGE_MAX))
    r = b.get("route")
    if isinstance(r, dict) and set(r) == {"na"}:
        if not _line(r["na"], NA_MAX):
            errs.append("route.na: 1..%d chars" % NA_MAX)
    elif isinstance(r, dict) and set(r) == {"by", "rows"} and _line(r["by"], BY_MAX) and isinstance(r["rows"], list) \
            and 1 <= len(r["rows"]) <= ROW_MAX:
        for row in r["rows"]:
            ev = row.get("evidence") if isinstance(row, dict) else None
            if not isinstance(row, dict) or set(row) - {"when", "goes", "box", "evidence"} \
                    or not _line(row.get("when"), WHEN_MAX) or not _line(row.get("goes"), GOES_MAX) \
                    or ("box" in row and not isinstance(row["box"], str)) \
                    or not isinstance(ev, dict) or set(ev) != {"file", "line"} or not _int(ev["line"]):
                errs.append("route row: {when<=%d, goes<=%d, box?, evidence:{file, line}}" % (WHEN_MAX, GOES_MAX))
    else:
        errs.append("route: {na} or {by, rows 1..%d}" % ROW_MAX)
    return errs


def check(b, m, v, tree, read):
    """(errors, uncovered module count) for a shape-valid brief. `tree` = set of paths at the commit (None = unreadable);
    `read(rel)` = lines of rel at the commit (None = unreadable)."""
    if b.get("v") == 2:
        return B2.check(b, m, v, tree, read)
    errs = []
    mids = set(d["id"] for d in m["modules"])
    bands = set()
    for x in b["bands"]:
        if x["id"] in bands:
            errs.append("duplicate band id %s" % x["id"])
        bands.add(x["id"])
    owner, boxes = {}, {}
    for x in b["boxes"]:
        if x["id"] in boxes:
            errs.append("duplicate box id %s" % x["id"])
        boxes[x["id"]] = set(x["modules"])
        if x["band"] not in bands:
            errs.append("box %s: unknown band %s" % (x["id"], x["band"]))
        for i in x["modules"]:
            if i not in mids:
                errs.append("box %s: unknown module %s" % (x["id"], i))
            elif i in owner and owner[i] != x["id"]:
                errs.append("module %s in two boxes (%s, %s)" % (i, owner[i], x["id"]))
            else:
                owner[i] = x["id"]
    # A band that only repeats its one box's name, or 4+ same-labelled arrows into one box, says nothing a band note can't.
    for x in b["bands"]:
        mine = [y for y in b["boxes"] if y["band"] == x["id"]]
        if len(mine) == 1 and _fold(mine[0]["name"]) == _fold(x["name"]):
            errs.append("band %s «%s»: holds one box with its own name — merge it into another band or name the band for "
                        "what the box does" % (x["id"], x["name"]))
    same = {}
    for a in b.get("arrows", []):
        if a.get("label") and _fold(a["label"]):
            k = (a["to"], _fold(a["label"]))
            same[k] = same.get(k, 0) + 1
    for (to, lab), n in sorted(same.items()):
        if n >= SAME_LABEL_MAX:
            errs.append("box %s: %d arrows labelled «%s» — use a band note instead" % (to, n, lab))
    ok_ix = set(e["i"] for e in v["edges"] if isinstance(e, dict) and e.get("ok") is True and _int(e.get("i")))
    for a in b.get("arrows", []):
        tag = "arrow %s->%s" % (a["from"], a["to"])
        if a["from"] not in boxes or a["to"] not in boxes:
            errs.append("%s: unknown box" % tag)
            continue
        if a["from"] == a["to"]:
            errs.append("%s: arrow to its own box" % tag)
            continue
        for i in a["edges"]:
            if not 0 <= i < len(m["edges"]):
                errs.append("%s: edge %d does not exist" % (tag, i))
            elif i not in ok_ix:
                errs.append("%s: edge %d is not verified" % (tag, i))
            elif m["edges"][i]["from"] not in boxes[a["from"]] or m["edges"][i]["to"] not in boxes[a["to"]]:
                errs.append("%s: edge %d does not join these boxes" % (tag, i))
    for k, row in enumerate((b["route"].get("rows") or []), 1):
        if "box" in row and row["box"] not in boxes:
            errs.append("route row %d: unknown box %s" % (k, row["box"]))
        errs += B2._ev_errors("route row %d" % k, row["evidence"], tree, read)   # one evidence rule for v1 and v2
    return errs, len(mids - set(owner))


def render(b):
    """brief.html text for a gate-checked brief. ⚠v1 bytes are sha-gated (tests): the v1 path stays AH.render."""
    return AH2.render(b) if b.get("v") == 2 else AH.render(b)


def run(repo, commit):
    """Gate: check S/brief.json; on pass write S/brief.html then S/brief.ok.json {v, sha256, commit}, on FAIL remove
    a stale brief.ok.json. (rc, one line). ⚠Only this writes brief.ok.json: an html without a matching one is not gated."""
    repo = os.path.realpath(repo)
    try:
        d = AV.store_dir(repo, commit)
    except ValueError as e:
        return 1, "arch_brief: %s" % e
    ok_fp = os.path.join(d, AV.BRIEF_OK)
    rc, line, html_text = _gate(repo, commit, d)
    if rc:
        if os.path.lexists(ok_fp):
            os.remove(ok_fp)   # an OSError here propagates: a stamp that cannot be removed must not look valid
        return rc, line
    data = html_text.encode("utf-8")
    AV._write(os.path.join(d, AV.BRIEF_HTML), html_text)
    AV._write(ok_fp, json.dumps({"v": 1, "sha256": hashlib.sha256(data).hexdigest(), "commit": commit}) + "\n")
    return rc, line


def _gate(repo, commit, d):
    """(rc, line, html text or None) — writes nothing."""
    mv = _map_ready(repo, commit)
    if mv is None:
        return 1, "arch_brief: no arch-map result for %s at %s; run arch-map first" % (repo, commit[:7]), None
    m, v = mv
    try:
        b = AV.read_json(os.path.join(d, AV.BRIEF_JSON))
    except (OSError, ValueError) as e:
        return 1, "arch_brief: FAIL: brief.json unreadable (%s)" % type(e).__name__, None
    errs = shape_errors(b, repo, commit)
    # ⚠A new v1 brief would skip the v2 rules (containment, labelled arrows, principles); stored v1 html is served by sha only.
    if not errs and b.get("v") != 2:
        errs = ["v1 brief.json: redraw as v2"]
    if not errs:
        errs, unc = check(b, m, v, *_reader(repo, commit))
    if errs:
        return 1, "arch_brief: FAIL: %s%s" % ("; ".join(errs[:5]), " (+%d more)" % (len(errs) - 5) if len(errs) > 5 else ""), None
    return 0, "arch_brief: %s · %s" % (B2.ok_line(b, unc), os.path.join(d, AV.BRIEF_HTML)), render(b)


def check_v1(repo, commit, b, m, v):
    """check() of a v1 brief with the tree/read of the commit — kept for the v1 rules' tests; the gate refuses v1."""
    return check(b, m, v, *_reader(repo, commit))


def _reader(repo, commit):
    """(tree, read) at the commit: tree None = unreadable; read(rel) -> lines or None (memoised)."""
    try:
        tree = AV._tree(repo, commit)
    except (subprocess.SubprocessError, OSError):
        tree = None
    memo = {}

    def read(rel):
        if rel not in memo:
            try:
                memo[rel] = AV._show(repo, commit, rel)
            except (subprocess.SubprocessError, OSError):
                memo[rel] = None
        return memo[rel]
    return tree, read
