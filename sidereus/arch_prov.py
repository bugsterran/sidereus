"""Provenance of a verified arch map: which platform, model and session drew it (`/api/arch` `prov`).

Stored at DATA_DIR/arch-prov/<repo_key>/<commit>.json = {v: 1, plat, sid, model, stages: [{t, model}], at, vt}
(vt = verify.json mtime it belongs to). Written only here, from Sidereus' own session metadata.
⚠Never beside map.json: the drawing agent may write anything under arch/<key>/<commit>/, so a file there could be forged.
⚠Metadata only (AGENTS.md rule 1): transcripts are read for `model`/`timestamp` fields only — never bodies or tool input.
"""
import glob
import json
import os
import re
import time

from sidereus.config import DATA_DIR
from sidereus.bus import _atomic_write
from sidereus import arch_verify, claude_roots, plat_codex, pl_runs, work
from sidereus.transcript import CLAUDE_PROJECTS, _model_label, iso_epoch
from sidereus.ext_store import EXT_PLAT
from sidereus.arch_verify import COMMIT_RE, repo_key

PROV_DIR = os.path.join(DATA_DIR, "arch-prov")
PROV_LATE_S = 6 * 3600       # = pl_runs.PLR_KEEP_S: a map verified longer ago never gets a late (fallback) provenance
PROV_READ_MAX = 4 << 20      # bytes of one transcript / rollout scanned for model fields
PROV_SLACK_S = 5             # run window slack around [t0, end|t1]
PROV_MISS_S = 60             # a failed late match is not retried for this long
PROV_GAP_S = 1800            # tagged agents of one run follow each other within this (run start when runs.json has no run)
PROV_FILE_MAX = 65536
_PL = "arch-map"
_PLATS = frozenset(["cc"]) | frozenset(EXT_PLAT.values())
_MODEL_RE = re.compile(r"^[A-Za-z0-9._:/ -]{1,40}$")
_SID_RE = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
_AID_RE = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")
_MISS = {}                   # (key, commit, vt) -> time of the last failed late match
_now = time.time


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _model(m):
    m = _model_label(m) if isinstance(m, str) else ""
    return m if _MODEL_RE.match(m) and m != "<synthetic>" else ""


def _path(root, commit):
    return os.path.join(PROV_DIR, repo_key(root), commit + ".json")


def _clean(d, vt):
    """Validated prov or None (shape, value sets, vt within ±2 s of the current verify.json mtime)."""
    if not isinstance(d, dict) or d.get("v") != 1 or d.get("plat") not in _PLATS:
        return None
    sid, model, stages = d.get("sid"), d.get("model"), d.get("stages")
    if not (isinstance(sid, str) and _SID_RE.match(sid) and isinstance(model, str) and _MODEL_RE.match(model)):
        return None
    if not isinstance(stages, list) or len(stages) > pl_runs.PLR_STAGES_MAX or abs(_num(d.get("vt")) - vt) > 2:
        return None
    out = []
    for s in stages:
        if not (isinstance(s, dict) and isinstance(s.get("t"), str) and s["t"] and isinstance(s.get("model"), str)
                and _MODEL_RE.match(s["model"])):
            return None
        out.append({"t": s["t"][:80], "model": s["model"]})
    return {"v": 1, "plat": d["plat"], "sid": sid, "model": model, "stages": out, "at": _num(d.get("at")),
            "vt": _num(d.get("vt"))}


def get(root, commit, vt):
    """Stored prov of (root, commit) for verify mtime vt, None when missing or invalid."""
    if not COMMIT_RE.fullmatch(commit or ""):
        return None
    try:
        with open(_path(root, commit), "rb") as f:
            return _clean(json.loads(f.read(PROV_FILE_MAX)), vt)
    except (OSError, ValueError):
        return None


def _save(root, commit, prov):
    _atomic_write(_path(root, commit), json.dumps(prov, separators=(",", ":")).encode("utf-8"),
                  prefix=".prov-", mkdir=True, mode=0o600)


def _lines(fp, want, head):
    """Parsed JSON lines of fp that contain every byte string in want; head = from the start, else the last
    PROV_READ_MAX bytes (first partial line dropped)."""
    try:
        with open(fp, "rb") as f:
            if not head:
                sz = os.fstat(f.fileno()).st_size
                if sz > PROV_READ_MAX:
                    f.seek(sz - PROV_READ_MAX)
                    f.readline()
            data = f.read(PROV_READ_MAX)
    except OSError:
        return
    for ln in data.split(b"\n"):
        if all(w in ln for w in want):
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            if isinstance(o, dict):
                yield o


def _cc_models(fp, head=False):
    """[(t, model)] of assistant lines (`message.model`, `<synthetic>` skipped); only those two fields are kept."""
    out = []
    for o in _lines(fp, (b'"assistant"', b'"model"'), head):
        msg = o.get("message")
        m = _model(msg.get("model")) if o.get("type") == "assistant" and isinstance(msg, dict) else ""
        if m:
            out.append((iso_epoch(o.get("timestamp")), m))
            if head:
                break
    return out


def _cx_models(fp):
    """[(t, model)] of a Codex rollout's turn_context lines."""
    out = []
    for o in _lines(fp, (b'"turn_context"',), False):
        p = o.get("payload")
        m = _model(p.get("model")) if o.get("type") == "turn_context" and isinstance(p, dict) else ""
        if m:
            out.append((iso_epoch(o.get("timestamp")), m))
    return out


def _at(seq, t):
    """Model of the last entry at/before t, "" if none."""
    xs = [m for ts, m in seq if ts and ts <= t + PROV_SLACK_S]
    return xs[-1] if xs else ""


def _cc_path(cwd, sid):
    """Claude transcript of sid, "" when not found or present in more than one account (owner unknown)."""
    fp = work._sid_path(cwd or "", sid)
    if not fp:
        return ""
    n = sum(len(glob.glob(os.path.join(glob.escape(p), "*", sid + ".jsonl")))
            for p in claude_roots.projects_dirs(CLAUDE_PROJECTS))
    return fp if n <= 1 else ""


def _rollout(sid):
    """Codex rollout of sid (live sessions/ copy before an archived one), "" if none."""
    hits = [p for p in plat_codex._files(plat_codex.root())
            if p.endswith("-" + sid + ".jsonl") and plat_codex.path_ok(p)]
    hits.sort(key=lambda p: ("archived_sessions" not in p, os.path.getmtime(p) if os.path.exists(p) else 0))
    return hits[-1] if hits else ""


def _asked(sid, root, vt, req):
    """True when the page's newest arch-map request to sid as of vt names root (req = pl_reqs.req_repo, via arch_map)."""
    try:
        rq = req(sid, _PL, vt) if req and sid else ""
    except (OSError, ValueError, TypeError):
        return False
    return isinstance(rq, str) and bool(rq) and os.path.realpath(rq) == os.path.realpath(root)


def _ags(sid, now):
    """Tagged arch-map subagents [{t, aid, t0, t1}] of sid's Claude session (metadata only), [] without a transcript."""
    fp = _cc_path("", sid)
    return list((pl_runs._ag_by_name(fp[:-len(".jsonl")], now) or {}).get(_PL) or ()) if fp else []


def _targets(r, root, sid="", vt=0.0, req=None):
    """True when a runs.json run worked on root: its session `cwd` is root, inside root, or inside root's arch store dir,
    or the page asked sid to map root (a cross-repo run: cwd is the requesting session's own repo).
    ⚠Not `proj`: that is the pipeline owner (the Sidereus repo for every arch-map run). No cwd, no request -> False."""
    if _asked(sid, root, vt, req):
        return True
    c = pl_runs._proj(r.get("cwd"))
    if not c:
        return False
    rc, rr = os.path.realpath(c), os.path.realpath(root)
    store = os.path.join(os.path.realpath(arch_verify.ARCH_DIR), repo_key(root))
    return rc == rr or rc.startswith(rr + os.sep) or rc == store or rc.startswith(store + os.sep)


def _run_of(sid, vt, now, root=None, req=None):
    """(t0, end|t1, validated st) of sid's arch-map runs (current + past) whose window covers vt; root = target must match.
    ⚠An open run's t1 is the current stage's start: its window runs to the newest tagged agent end instead."""
    doc = pl_runs._load_doc(sid, now)
    raws = []
    cur = (doc.get("runs") or {}).get(_PL) if isinstance(doc.get("runs"), dict) else None
    if isinstance(cur, dict):
        raws.append(cur)
    past = (doc.get("past") or {}).get(_PL) if isinstance(doc.get("past"), dict) else None
    raws += [r for r in (past if isinstance(past, list) else ()) if isinstance(r, dict)]
    out, ags = [], None
    for r in raws:
        if root is not None and not _targets(r, root, sid, vt, req):
            continue
        t0, t1 = _num(r.get("t0")), _num(r.get("end")) or _num(r.get("stop"))
        if not t1:
            ags = _ags(sid, now) if ags is None else ags
            t1 = max([_num(r.get("t1"))] + [a["t1"] for a in ags if a["t0"] >= t0 - PROV_SLACK_S])
        if t0 and t0 - PROV_SLACK_S <= vt <= t1 + PROV_SLACK_S:
            out.append((t0, t1, pl_runs._stages(r.get("st"))))
    return out


def _cc_stages(fp, t0, t1, st, now, main):
    """[(start, title, model)]: tagged arch-map subagents in [t0, t1] (first observed model of each agent), plus
    run stages with no agent (main's model at the stage time)."""
    sess = fp[:-len(".jsonl")]
    out, seen = [], set()
    ags = (pl_runs._ag_by_name(sess, now) or {}).get(_PL) or ()
    tried = set()   # ⚠a stage run by an agent with no model line is omitted, never labelled with main's model
    for a in sorted(ags, key=lambda a: a["t0"]):
        if not (t0 - PROV_SLACK_S <= a["t0"] <= t1 + PROV_SLACK_S) or a["t"] in seen or not _AID_RE.match(a["aid"]):
            continue
        tried.add(a["t"])
        ms = _cc_models(os.path.join(sess, "subagents", "agent-%s.jsonl" % a["aid"]), head=True)
        if ms:
            seen.add(a["t"])
            out.append((a["t0"], a["t"], ms[0][1]))
    seen |= tried
    mains = None
    for title, s in st.items():
        if title in seen:
            continue
        mains = _cc_models(fp) if mains is None else mains
        m = _at(mains, s["t1"] or s["t0"]) or main
        if m:
            out.append((s["t0"], title, m))
    return out


def _cx_stages(seq, st, main):
    out = []
    for title, s in st.items():
        inw = [m for ts, m in seq if s["t0"] <= ts <= (s["t1"] or s["t0"])]
        m = inw[-1] if inw else (_at(seq, s["t0"]) or main)
        if m:
            out.append((s["t0"], title, m))
    return out


def _build(plat, sid, cwd, row_model, t0, t1, st, vt, now):
    """prov dict or None (no model known)."""
    stages = []
    main = _model(row_model)
    if plat == "cc":
        fp = _cc_path(cwd, sid)
        if fp:
            main = _at(_cc_models(fp), t1) or main
            stages = _cc_stages(fp, t0, t1, st, now, main)
    elif plat == plat_codex.KEY:
        rp = _rollout(sid)
        seq = _cx_models(rp) if rp else []
        main = _at(seq, t1) or main
        stages = _cx_stages(seq, st, main)
    stages = [(t, title[:80], m) for t, title, m in sorted(stages)][:pl_runs.PLR_STAGES_MAX]
    ms = {m for _t, _ti, m in stages}
    if len(ms) == 1:
        main, stages = ms.pop(), []
    if not main:
        return None
    return {"v": 1, "plat": plat, "sid": sid, "model": main, "stages": [{"t": ti, "model": m} for _t, ti, m in stages],
            "at": now, "vt": vt}


def record(root, commit, vt, row, t0, now=None):
    """Primary capture: a tracked arch-map run of session row `row` ended with verify.json (mtime vt > t0).
    Writes nothing when a valid prov for vt already exists. plat/model/sid come from the session row, never from map.json."""
    now = _now() if now is None else now
    if not (isinstance(row, dict) and COMMIT_RE.fullmatch(commit or "") and vt and vt > t0) or get(root, commit, vt):
        return None
    sid, plat = str(row.get("sid") or ""), row.get("plat") or "cc"
    k = (repo_key(root), commit, vt, sid)
    if not _SID_RE.match(sid) or plat not in _PLATS or now - _MISS.get(k, -1e18) < PROV_MISS_S:
        return None
    runs = sorted(_run_of(sid, vt, now), key=lambda r: r[0])
    r0, r1, st = runs[-1] if runs else (t0, vt, {})
    prov = _build(plat, sid, row.get("cwd"), row.get("model"), min(t0, r0) if t0 else r0, max(r1, vt), st, vt, now)
    if prov:
        _save(root, commit, prov)
    else:   # ⚠runs() calls this every poll while the run reads finished: no model -> retry only after PROV_MISS_S
        _miss(k, now)
    return prov


def _tagged(sid, root, vt, now, req):
    """(sid, t0, t1, {}) from sid's tagged arch-map agents when the page asked sid to map root and one agent spans vt,
    else None. ⚠A session whose cwd has its own pipelines gets no runs.json arch-map run: agents are the only record."""
    if not _asked(sid, root, vt, req):
        return None
    ags = _ags(sid, now)
    hit = [a for a in ags if a["t0"] - PROV_SLACK_S <= vt <= a["t1"] + PROV_SLACK_S]
    if not hit:
        return None
    t0 = min(a["t0"] for a in hit)
    for a in sorted(ags, key=lambda a: -a["t0"]):   # walk back over the run's earlier stages, stop at a long gap
        if a["t0"] < t0 and a["t1"] >= t0 - PROV_GAP_S:
            t0 = a["t0"]
    return sid, t0, max(a["t1"] for a in hit), {}


def _late(root, commit, vt, now, req=None):
    """Fallback after a restart mid-run: exactly one plmark arch-map run for root whose window covers vt records;
    several are narrowed to those with a stage covering vt (the verify stage's session wins); with no run at all, one
    requested session whose tagged agents span vt; else unknown."""
    cands, sids = [], []
    try:
        names = os.listdir(pl_runs.PLR_DIR)
    except OSError:
        return None
    for fn in names:
        sid = fn[:-len(".runs.json")] if fn.endswith(".runs.json") else ""
        if _SID_RE.match(sid):
            sids.append(sid)
            cands += [(sid,) + r for r in _run_of(sid, vt, now, root, req)]
    if not cands:
        cands = [c for c in (_tagged(sid, root, vt, now, req) for sid in sids) if c]
    if len(cands) > 1:
        cands = [c for c in cands if any(s["t0"] - PROV_SLACK_S <= vt <= (s["t1"] or s["t0"]) + PROV_SLACK_S
                                         for s in c[3].values())]
    if len(cands) != 1:
        return None
    sid, t0, t1, st = cands[0]
    if _cc_path("", sid):
        plat = "cc"
    elif _rollout(sid):
        plat = plat_codex.KEY
    else:
        return None
    prov = _build(plat, sid, "", "", t0, max(t1, vt), st, vt, now)
    if prov:
        _save(root, commit, prov)
    return prov


def load_prov(root, commit, vt, now=None, req=None):
    """`/api/arch` `prov`: stored prov, else a late match for a map verified within PROV_LATE_S, else None («unknown»).
    req = the page's request source (fn(sid, pl, at) -> repo), so a cross-repo run still matches its target."""
    now = _now() if now is None else now
    p = get(root, commit, vt)
    if p or not vt or now - vt > PROV_LATE_S or not COMMIT_RE.fullmatch(commit or ""):
        return p
    k = (repo_key(root), commit, vt)
    if now - _MISS.get(k, -1e18) < PROV_MISS_S:
        return None
    try:
        p = _late(root, commit, vt, now, req) and get(root, commit, vt)
    except (OSError, ValueError, TypeError, KeyError):
        p = None   # unreadable run/transcript: «unknown», retried after PROV_MISS_S
    if p is None:
        _miss(k, now)
    return p


def _miss(k, now):
    if len(_MISS) >= 64:
        _MISS.clear()
    _MISS[k] = now
