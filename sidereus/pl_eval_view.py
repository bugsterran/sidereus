"""GET /api/pipelines/eval — per-stage evaluation of one pipeline (catch rate · red check · unstable) for the pipeline header.
Metadata only: counts, verdict words and stage titles. ⚠Missed case ids and holdout cases never leave this module.
`sugg` = rule-based improvement suggestions (codes + parameters, no tool text): see suggest()."""
import math
import os
import shlex
import subprocess
import time

from sidereus import config, gitinfo, pipeline, pipeline_projects, pl_scorecard
from sidereus.arch_verify import COMMIT_RE, repo_key
from sidereus.pipeline_schema import gate_mode
from sidereus.warn import warn_once

EV_VERDICTS = ("pass", "fail", "skip", "none")
EV_TITLE_MAX = 80
EV_STAGES_MAX = 40
EV_INT_MAX = 1_000_000
EV_SUGG_MAX = 40
# Seed kind -> tools whose findings catch it (= pl_eval.KIND_TOOLS; logic seeds have no tool gate).
SG_KIND_TOOLS = {"secret": ("gitleaks",), "dep": ("npm-audit", "osv-scanner"), "sast": ("semgrep", "bandit")}
SG_KINDS = ("secret", "dep", "sast", "logic")
# Gate mode -> the flags that make an empty or broken run fail (arch_checks --verify fails when no tool ran / 0 files).
SG_FLAGS = {"checks-security": "--verify --last --category security", "fast": "--fast", "full": "--full"}
SG_REVIEW_GROUPS = ("review", "test")


def _pe():
    """sidereus.pl_eval or None — ⚠imported lazily: the view degrades to «no evaluation yet» while the core is absent."""
    try:
        from sidereus import pl_eval
        return pl_eval
    except Exception:
        return None


def _now():
    return time.time()


def _int(v):
    return max(0, min(EV_INT_MAX, v)) if isinstance(v, int) and not isinstance(v, bool) else 0


def _title(v):
    return v[:EV_TITLE_MAX] if isinstance(v, str) else ""


def _head(proj):
    """Full HEAD sha (read-only rev-parse through git_argv) or ""."""
    try:
        r = gitinfo._git_run(proj, ["rev-parse", "HEAD"], 2, wait=0.5)
        h = (r.stdout or "").strip() if r.returncode == 0 else ""
        return h if COMMIT_RE.fullmatch(h) else ""
    except Exception:
        return ""


def wilson(k, n, z=1.96):
    """95% Wilson score interval of k/n as {lo, hi} in whole percent, or None when n is 0 (stays inside 0..100 at k=0 or n)."""
    if not n or n < 0 or k < 0 or k > n:
        return None
    p, zz = k / n, z * z
    d = 1 + zz / n
    c, m = (p + zz / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + zz / (4 * n * n)) / d
    pct = lambda x: max(0, min(100, int(x * 100 + 0.5)))
    return {"lo": pct(c - m), "hi": pct(c + m)}


def _agree(a):
    return {"k": min(_int(a.get("k")), _int(a.get("n"))), "n": _int(a.get("n"))} if isinstance(a, dict) and _int(a.get("n")) else None


def _counts(d, a, b):
    """{a: int, b: int} from a dict, or None — only these two keys survive (no ids, no case text)."""
    if not isinstance(d, dict):
        return None
    return {a: _int(d.get(a)), b: _int(d.get(b))}


def _graded(g):
    if not isinstance(g, dict):
        return None
    un = [_title(t) for t in (g.get("unstable") or []) if isinstance(t, str)][:EV_STAGES_MAX]
    ur = g.get("unred")
    ur = len(ur) if isinstance(ur, list) else _int(ur)    # pl_eval returns the titles; only the count leaves
    return {"n": _int(g.get("n")), "m": _int(g.get("m")), "unred": min(ur, EV_INT_MAX), "unstable": un}


def tpl_for_kind(kind, templates):
    """Id of the catalog template whose gate brings a tool for this seed kind (fewest tools first), or ""."""
    want = SG_KIND_TOOLS.get(kind) or ()
    best = None
    for t in templates or []:
        if not (isinstance(t, dict) and isinstance(t.get("id"), str) and isinstance(t.get("gate"), str) and t["gate"].strip()):
            continue
        ids = [x.get("id") for x in t.get("tools") or [] if isinstance(x, dict)]
        if any(w in ids for w in want) and (best is None or len(ids) < best[0]):
            best = (len(ids), t["id"])
    return best[1] if best else ""


def tpl_for_mode(mode, templates):
    """Id of the first catalog template whose gate records `mode`, or ""."""
    return next((t["id"] for t in templates or [] if isinstance(t, dict) and isinstance(t.get("id"), str)
                 and mode and gate_mode(t.get("gate") or "") == mode), "")


def _review_tpl(templates):
    ts = [t for t in templates or [] if isinstance(t, dict) and isinstance(t.get("id"), str) and t.get("group") in SG_REVIEW_GROUPS]
    return next((t["id"] for t in ts if t["id"] == "review"), ts[0]["id"] if ts else "")


def _is_review(s, templates):
    """A stage that reviews or tests: its title is a review/test catalog template, or its agent name says so."""
    ko = {(t.get("title") or {}).get("ko") for t in templates or [] if isinstance(t, dict) and t.get("group") in SG_REVIEW_GROUPS}
    ag = s.get("agent") if isinstance(s.get("agent"), str) else ""
    return s.get("title") in ko or any(w in ag.lower() for w in ("review", "test", "verif"))


def suggest(stages, ev, red, unstable, kinds, templates, cmd_of):
    """Deterministic suggestions [{code, stage?, kind?, tpl?, mode?, flags?, cmd?}] (no AI, no tool text).
    stages = pipeline stage dicts · ev = load_eval (or None) · red = {title: verdict} (None = core absent: no red rules) ·
    unstable = titles · kinds = {title: [seed kinds of missed public seeds]} · cmd_of(title) = red-check command."""
    out = []
    by = {s.get("title"): s for s in (ev or {}).get("stages") or [] if isinstance(s, dict)}
    for s in stages:
        t, g = s.get("title"), s.get("gate") if isinstance(s.get("gate"), str) else ""
        if not isinstance(t, str):
            continue
        c = by.get(t) or {}
        if not g.strip():
            if _int(c.get("n")) > _int(c.get("caught")):   # (a) ungated stage missed seeds -> a template with a real gate
                for k in [k for k in SG_KINDS if k in (kinds.get(t) or ())]:
                    tp = tpl_for_kind(k, templates)
                    if tp:
                        out.append({"code": "add-gate", "stage": t, "kind": k, "tpl": tp})
            continue
        mode, v = gate_mode(g) or "", (red or {}).get(t)
        if red is not None and v == "fail":                  # (b) gate stayed green on a broken repo
            out.append({"code": "tighten-gate", "stage": t, "mode": mode, "flags": SG_FLAGS.get(mode, ""),
                        "tpl": tpl_for_mode(mode, templates)})
        if t in unstable:                                    # (c) passed and failed on the same commit
            out.append({"code": "unstable", "stage": t, "mode": mode})
        if red is not None and v not in ("pass", "fail", "skip"):   # (e) never red-checked, or the gate text changed
            out.append({"code": "redcheck", "stage": t, "cmd": cmd_of(t)})
    h = (ev or {}).get("holdout") if isinstance((ev or {}).get("holdout"), dict) else {}
    if _int(h.get("n")) > _int(h.get("caught")) and not any(_is_review(s, templates) for s in stages):   # (d)
        tp = _review_tpl(templates)
        if tp:
            out.append({"code": "add-review", "tpl": tp})
    return out[:EV_SUGG_MAX]


def redcheck_cmd(proj, name, title, code_dir=None, nt=None):
    """Copyable red-check command for one stage: `py` + list2cmdline on Windows, `python3` + POSIX quoting elsewhere."""
    nt = os.name == "nt" if nt is None else nt
    argv = ["py" if nt else "python3", os.path.join(code_dir or config.CODE_DIR, "scripts", "pl_eval.py"), "redcheck",
            "--pipeline", os.path.join(proj, ".claude", "pipelines", name + ".json"), "--stage", title, "--repo", proj]
    return subprocess.list2cmdline(argv) if nt else " ".join(shlex.quote(a) for a in argv)


def _missed_kinds(pe, proj, ev):
    """{stage title: [kinds]} of missed public seeds. ⚠Seeds hold holdout ids: only kinds leave this function."""
    ld = getattr(pe, "load_seeds", None)
    seeds = ld(proj) if ev and ld else None
    kind = {s.get("id"): s.get("kind") for s in (seeds or {}).get("seeds") or [] if isinstance(s, dict) and not s.get("holdout")}
    out = {}
    for s in (ev or {}).get("stages") or []:
        if isinstance(s, dict) and isinstance(s.get("title"), str):
            out[s["title"]] = sorted({kind[i] for i in s.get("missed") or [] if kind.get(i) in SG_KINDS})
    return out


def _sec(sec):
    """Scorecard block reduced to {n, m, checks:[{id, v}]} with known ids/verdicts only (R4: no paths, no contents), or None."""
    if not isinstance(sec, dict):
        return None
    cs = [{"id": c["id"], "v": c["v"]} for c in sec.get("checks") or [] if isinstance(c, dict)
          and c.get("id") in pl_scorecard.SC_IDS and c.get("v") in pl_scorecard.SC_VERDICTS]
    return {"n": _int(sec.get("n")), "m": _int(sec.get("m")), "checks": cs}


def body(name, titles, ev, red, graded, commit, sugg=None, agree=None, sec=None):
    """Response body from already-loaded parts (pure; tests drive it directly). agree = {title: {k, n}} (gate_agreement) ·
    sec = pl_scorecard.score() result."""
    by = {}
    for s in (ev or {}).get("stages") or []:
        if isinstance(s, dict) and isinstance(s.get("title"), str):
            by[s["title"]] = {"caught": _int(s.get("caught")), "n": _int(s.get("n"))}
    g = _graded(graded)
    un = set(g["unstable"]) if g else set()
    stages = []
    for t in titles[:EV_STAGES_MAX]:
        v = ((red or {}).get(t) or {}).get("verdict") if isinstance((red or {}).get(t), dict) else None
        c = by.get(t)
        stages.append({"title": _title(t), "catch": c, "red": v if v in EV_VERDICTS else "none", "unstable": t in un,
                       "ci": wilson(min(c["caught"], c["n"]), c["n"]) if c else None,
                       "agree": _agree((agree or {}).get(t)) if isinstance(agree, dict) else None})
    ho = _counts((ev or {}).get("holdout"), "n", "caught") if isinstance(ev, dict) else None
    ho = dict(ho, ci=wilson(min(ho["caught"], ho["n"]), ho["n"])) if ho and ho["n"] else None   # pl_eval fills an absent holdout with zeros
    return {"ok": True, "name": name, "graded": g, "stages": stages, "holdout": ho, "commit": commit[:12] if commit else "",
            "sugg": list(sugg or [])[:EV_SUGG_MAX], "security": _sec(sec)}


def pl_eval(proj, name):
    """(code, body) for GET /api/pipelines/eval?proj=&name= — same project allow-list as /api/pipelines."""
    if not pipeline_projects._proj_ok(proj):
        return 400, {"ok": False, "msg": "unknown project"}    # ⚠not 404: the page reads 404 as «feature off»
    if not isinstance(name, str) or not pipeline._NAME.fullmatch(name) or name not in pipeline._names(proj):
        return 400, {"ok": False, "msg": "unknown pipeline"}
    _raw, P, err = pipeline._read_pipe(proj, name)
    if err or not isinstance(P, dict):
        return 400, {"ok": False, "msg": "unreadable pipeline"}
    stages = [s for s in P.get("stages") or [] if isinstance(s, dict)]
    titles = [s["title"] for s in stages if isinstance(s.get("title"), str)]
    commit = _head(proj)
    sec = None
    try:
        sec = pl_scorecard.scorecard(proj, commit)
    except Exception as e:   # independent of the eval core: shown even when pl_eval is absent
        warn_once("pl_scorecard", "Pipeline evaluation could not be read: {e}", soft=True, vars={"e": type(e).__name__})
    pe = _pe()
    if pe is None:
        return 200, body(name, titles, None, None, None, commit, sec=sec)
    ev = red = graded = agree = None
    sugg = []
    try:
        ev = pe.load_eval(repo_key(proj), commit) if commit else None
        red = pe.redcheck_status(name, stages)
        graded = pe.graded_summary(dict(P, name=name), proj, _now())   # the file need not carry its own name
        ga = getattr(pe, "gate_agreement", None)
        agree = ga(P, proj, _now(), commit) if ga else None
        ev, red = ev if isinstance(ev, dict) else None, red if isinstance(red, dict) else None
        rv = {t: (v or {}).get("verdict") if isinstance(v, dict) else None for t, v in (red or {}).items()}
        un = set((_graded(graded) or {}).get("unstable") or [])
        sugg = suggest(stages, ev, rv if red is not None else None, un, _missed_kinds(pe, proj, ev), _catalog(),
                       lambda t: redcheck_cmd(proj, name, t))
    except Exception as e:   # partial results still render; the header falls back to the editor count when graded is missing
        warn_once("pl_eval_view", "Pipeline evaluation could not be read: {e}", soft=True, vars={"e": type(e).__name__})
    return 200, body(name, titles, ev if isinstance(ev, dict) else None, red if isinstance(red, dict) else None, graded, commit,
                     sugg, agree, sec)


def _catalog():
    try:
        from sidereus import stage_catalog
        return stage_catalog.load()["templates"]
    except Exception:
        return []

