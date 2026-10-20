"""Quality checks over a schema-valid arch map + its flows -> S/quality.json (gate of the arch-map pipeline).

Evidence checks prove an edge exists; these catch maps that are formally valid but say nothing: copy-paste flows,
labels that only repeat the target's name, duplicate entry points. Flow overlap is measured but warn-only. Pure `check`; `run` reads the store and writes.
⚠Metadata only: items carry module/flow ids and entry labels, never source text or edge labels.
"""
import json
import os
import re

from sidereus import arch_verify as AV
from sidereus import arch_flow as AF

# ★Thresholds set from two real maps (Codex FAIL: overlap J 0.949, label-target 165/179 = 0.92; Claude PASS: J 0.705, 1/355).
QUAL_OVERLAP_J = 0.80        # flow pair Jaccard over distinct (from, to) pairs at or above this warns
QUAL_OVERLAP_MIN = 3         # flows with fewer distinct pairs are exempt (short flows legitimately coincide)
QUAL_LABEL_N = 3             # label-target fails only with at least this many edges ...
QUAL_LABEL_RATIO = 0.25      # ... and at least this share of all edges
QUAL_ISOLATED_MIN = 3        # isolated-module warning only for maps with at least this many modules
QUAL_ITEMS = 20

# Words: runs of [0-9a-z] or Hangul syllables (escaped so the source holds no Hangul).
_WORD_SPLIT = re.compile("[^0-9a-z\uac00-\ud7a3]+")
_ACCESSOR = re.compile(r"^(?:(?:get|set|is|has)(?:[A-Z][a-z0-9]*){1,2}|get|set|put|add|remove|contains|size|isEmpty"
                       r"|toString|equals|hashCode|valueOf|getString|getInt|getLong|getBoolean)$")
_SEG_SPLIT = re.compile(r"[.#:/>\s]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _words(s):
    # camelCase/PascalCase split before lowercasing: id `sessionStore` echoes the label "session store".
    return set(w for w in _WORD_SPLIT.split(_CAMEL.sub(" ", str(s or "")).lower()) if w)


def _last_seg(sym):
    s = re.sub(r"\(.*$", "", str(sym or "").strip())
    segs = [x for x in _SEG_SPLIT.split(s) if x]
    return segs[-1] if segs else ""


def _item(check, n, of, items, mx=None):
    d = {"check": check, "n": n, "of": of, "items": items[:QUAL_ITEMS]}
    if mx is not None:
        d["max"] = mx
    return d


def _overlap(flows):
    sets = [(f["id"], set((s["from"], s["to"]) for s in f["steps"])) for f in flows]
    sets = [x for x in sets if len(x[1]) >= QUAL_OVERLAP_MIN]
    bad, best = [], 0.0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i][1], sets[j][1]
            jac = len(a & b) / float(len(a | b))
            best = max(best, jac)
            if jac >= QUAL_OVERLAP_J:
                bad.append(sets[i][0] + "~" + sets[j][0])
    return bad, best, len(sets)


def _label_target(m):
    mods = dict((d["id"], d) for d in m["modules"])
    bad = []
    for e in m["edges"]:
        w, t = _words(e.get("label")), mods.get(e.get("to"))
        if w and t and w <= (_words(t["id"]) | _words(t.get("name"))):
            bad.append("%s>%s" % (e["from"], e["to"]))
    return bad


def _entry_dup(flows):
    seen, bad = {}, []
    for f in flows:
        k = (f["entry"]["kind"], f["entry"]["label"].strip().lower())
        seen.setdefault(k, []).append(f["id"])
    for (kind, label), ids in seen.items():
        if len(ids) > 1:
            bad.append("%s %s" % (kind, label[:AF.ENTRY_MAX]))
    return bad


def check(m, flows):
    """{v, commit, fail: [...], warn: [...]} for a schema-valid map and its kept flows (list, may be empty)."""
    fail, warn = [], []
    edges = m["edges"]
    bad, best, nf = _overlap(flows)
    # ⚠Warn only: two entries sharing one long downstream chain (GET /items, GET /items/{id}) reach J 0.80 legitimately.
    if bad:
        warn.append(_item("flow-overlap", len(bad), nf, bad, round(best, 3)))
    bad = _label_target(m)
    if len(bad) >= QUAL_LABEL_N and edges and len(bad) / float(len(edges)) >= QUAL_LABEL_RATIO:
        fail.append(_item("label-target", len(bad), len(edges), bad))
    bad = _entry_dup(flows)
    if bad:
        fail.append(_item("entry-dup", len(bad), len(flows), bad))
    calls = [e for e in edges if e.get("kind") == "call"]
    # ⚠Warn only: accessor-named calls are often real (a getter on another module's DTO); never fail on names.
    acc = ["%s>%s" % (e["from"], e["to"]) for e in calls
           if e.get("evidence") and all(_ACCESSOR.match(_last_seg(x.get("symbol"))) for x in e["evidence"])]
    if acc:
        warn.append(_item("accessor-call", len(acc), len(calls), acc, round(len(acc) / float(len(calls)), 3)))
    if len(m["modules"]) >= QUAL_ISOLATED_MIN:
        touched = set(e["from"] for e in edges) | set(e["to"] for e in edges)
        iso = [d["id"] for d in m["modules"] if d["id"] not in touched]
        if iso:
            warn.append(_item("isolated", len(iso), len(m["modules"]), iso))
    if m.get("v") == 2:
        rw = set()
        for e in edges:
            if e.get("kind") in ("read", "write"):
                rw.update((e["from"], e["to"]))
        stores = [d["id"] for d in m["modules"] if d.get("kind") == "store"]
        dead = [s for s in stores if s not in rw]
        if dead:
            warn.append(_item("store-rw", len(dead), len(stores), dead))
    return {"v": 1, "commit": m.get("commit"), "fail": fail, "warn": warn}


def run(repo, commit):
    """(failed, suffix) after writing S/quality.json; (False, "") when the map is missing or not schema-valid.
    Flows: kept flows of a valid flows.json, else none."""
    try:
        d = AV.store_dir(repo, commit)
        m = AV.read_json(os.path.join(d, "map.json"))
    except (OSError, ValueError):
        return False, ""
    if AV.schema_errors(m, repo, commit):
        return False, ""
    try:
        f = AV.read_json(os.path.join(d, "flows.json"))
    except (OSError, ValueError):
        f = None                                   # no or unreadable flows.json: map checks still run
    errs, kept, _n = AF.flow_errors(f, repo, commit) if f is not None else ([], [], 0)
    q = check(m, [] if errs else kept)
    if errs:
        q["flows"] = "skipped"                     # invalid flows.json: flow checks did not run, say so
    AV._write(os.path.join(d, "quality.json"), json.dumps(q, ensure_ascii=False) + "\n")
    line = " · quality flows skipped" if errs else ""
    if q["fail"]:
        line += " · quality FAIL (%s)" % ", ".join(x["check"] for x in q["fail"])
    if q["warn"]:
        line += " · warn %s" % ", ".join(x["check"] for x in q["warn"])
    return bool(q["fail"]), line
