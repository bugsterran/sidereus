"""Pipeline «Result layer»: per pipeline, did its PASSes hold, did a fix follow them, how often did review loop back.

Sources: the run ledger `eval/<key>/runs.jsonl` (appended by hooks/pl_flow.py at every run end: titles, counts, hashes),
evidence rows (harness_evidence) and read-only git. ⚠Metadata only: counts, stage titles, short shas and file names —
git argv is `rev-parse`, `log --name-only` and `rev-list --ancestry-path`; never -p/--patch/--stat, `show <sha>:` or cat-file.
"""
import hashlib
import json
import os
import re
import subprocess
import time

from sidereus import config, gitinfo, harness_evidence, harness_trail

OC_DAY = 86400
OC_WIN_S = 30 * OC_DAY         # «last 30 days» (PASSes, procedure, current loop-back window)
OC_FIX_S = 14 * OC_DAY         # a commit this soon after a PASS touching its files = «fix followed»
# a commit up to this long after a run ended still belongs to that run (orchestrator commits last); = harness_person
# PS_GRACE_S. ★141 fix runs: first commit after run end within 60 s = 104, 300 s = 111, 900 s = 128, 1800 s = 137
OC_FIX_GRACE_S = 900
OC_NONCODE_DIRS = ("docs", "refactor", "tests", "test")
OC_PRE_S, OC_POST_S = 5, 60    # PASS ↔ run window [t0-5, end+60], same as harness_flow
OC_PASS_MAX = 30               # newest attributed PASSes examined
OC_SPAWN_MAX = 2 + OC_PASS_MAX  # git per outcome(): rev-parse + log + one rev-list per resolved commit (states() has its own)
OC_LOG_MAX = 500               # commits read by the one `log --name-only`
OC_FILES_MAX = 20              # file names kept per PASS in the report list
OC_LEDGER_MAX = 2000           # = hooks/pl_flow.py OC_LEDGER_MAX (rows kept)
OC_LEDGER_READ_MAX = 1024 * 1024
OC_GIT_TIMEOUT = 3
OC_GIT_WAIT = 0.5
OC_CACHE_MAX = 32
OC_EVAL_DIR = os.path.join(config.DATA_DIR, "eval")   # same folder as pl_eval.EVAL_DIR; tests patch it here
OC_DENY_CODES = ("jump", "agent", "model", "tag", "stage", "stop", "gate", "skipgate")   # = hooks/pl_flow.py DENY_CODES
OC_NAME = re.compile(r"[a-z0-9-]{1,40}")
OC_HEX = re.compile(r"[0-9a-f]{4,40}")
OC_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})\.md")
OC_TITLE_MAX = 80
OC_SS = ("done", "skip", "back", "fail")   # = hooks/pl_flow.py per-stage outcome in the ledger row's "ss"
OC_SS_MAX = 32                 # stages kept per row / per «Stage cost» table
# English source of every result-layer sentence (panel: web/js/48i via TV; report: scripts/pl_report.py).
OC_SENT = {
    "gate": "Gate: {g} of {m} gates confirmed able to fail",
    "proc": "Procedure: {runs} runs, {jump} order violations blocked",
    "result": "Result: {broke} of {n} passes broke later, fix followed {fixed}",
    "lb": "Review loop-backs: {cur}% of runs (last 30 days) vs {prev}% (30 days before)",
    "lb1": "Review loop-backs: {cur}% of runs (last 30 days), no earlier data",
    "rep": "Latest report {date} · {path}",
    "norep": "No report yet",
}
OC_LB_RISE_PP = 15   # R1 loop-back rise (percentage points) that flags a pipeline; provisional, to be set from 30-day data
# R1 one verdict per pipeline, English source. ⚠Keyed twice: web PLE_VD carries the same sentences; change both.
# ⚠pl_too_few spells OC_VERDICT_MIN_RUNS as «5» here, in PLE_VD and in the ko dictionary; change all three with it.
OC_VERDICT = {
    "pl_broke": "A pass from this pipeline broke later.",
    "pl_too_few": "Fewer than 5 runs in the last 30 days, too few to judge.",
    "pl_loopback": "Review loop-backs rose sharply against the 30 days before.",
    "healthy": "No pass broke, enough runs, loop-backs steady.",
}
OC_VERDICT_MIN_RUNS = 5
_OC_MEMO = {}   # (repo, name, review, HEAD, newest evidence ts, ledger mtime, 10-min bucket, fix pipes) -> outcome
_now = time.time


def _git(repo, args):
    """(returncode, stdout) of a read-only git call, or None on timeout/spawn failure. Tests patch this."""
    try:
        r = gitinfo._git_run(repo, args, OC_GIT_TIMEOUT, wait=OC_GIT_WAIT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.returncode, r.stdout or ""


def repo_key(proj):
    """= arch_verify.repo_key / hooks/pl_flow.py ledger key (sha1 of realpath, 16 hex)."""
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- persisted path key, not security
    return hashlib.sha1(os.path.realpath(proj).encode("utf-8", "surrogateescape"), usedforsecurity=False).hexdigest()[:16]


def _code(f):
    """False for docs, tests, refactor notes, screen baselines and changelogs: an overlap there is bookkeeping that
    nearly every commit touches, not a sign the later commit fixed the PASS's code."""
    if not isinstance(f, str) or not f:
        return False
    parts = f.split("/")
    base = parts[-1]
    return not (any(x in OC_NONCODE_DIRS for x in parts[:-1]) or f.startswith("scripts/screen_baseline/")
                or base.endswith(".md") or base.startswith("CHANGELOG"))


def _owner(ct, runs):
    """Ledger row a commit at `ct` belongs to: window [t0-5, end+OC_FIX_GRACE_S], nearest end wins, or None.
    ⚠Nearest end, not first match: a long fix run can span a short change run whose own commit lands at its end."""
    best = None
    for r in runs:
        if r["t0"] - OC_PRE_S <= ct <= r["end"] + OC_FIX_GRACE_S and (best is None or abs(r["end"] - ct) < abs(best["end"] - ct)):
            best = r
    return best


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else 0.0


def _int(v):
    return max(0, min(10 ** 6, v)) if isinstance(v, int) and not isinstance(v, bool) else 0


def _title(v):
    return v[:OC_TITLE_MAX] if isinstance(v, str) else ""


def _row(d):
    """Whitelisted ledger row, or None for junk."""
    if not isinstance(d, dict) or not isinstance(d.get("name"), str) or not OC_NAME.fullmatch(d["name"]):
        return None
    end = _num(d.get("end"))
    if not end:
        return None
    lb = [{"f": _title(e.get("f")), "g": _title(e.get("g")), "n": _int(e.get("n"))}
          for e in (d.get("lb") if isinstance(d.get("lb"), list) else [])[:32] if isinstance(e, dict)]
    dc = d.get("dc") if isinstance(d.get("dc"), dict) else {}
    hx = lambda v: v if isinstance(v, str) and OC_HEX.fullmatch(v) else ""
    return {"name": d["name"], "t0": _num(d.get("t0")) or end, "end": end, "lb": lb, "deny": _int(d.get("deny")),
            "dc": {c: _int(dc.get(c)) for c in OC_DENY_CODES if _int(dc.get(c))}, "h0": hx(d.get("h0")), "h1": hx(d.get("h1")),
            "ss": _ss(d.get("ss"))}


def _tok(v):
    return min(v, 10 ** 12) if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None   # ⚠not _int: a stage tops 10**6 tokens


def _ss(v):
    """Per-stage {title: {s, sec, n, tok}} of a ledger row; old rows and junk entries -> dropped. tok None = unknown."""
    out = {}
    for t, e in (v.items() if isinstance(v, dict) else ()):
        t = _title(t)
        if t and isinstance(e, dict) and e.get("s") in OC_SS and len(out) < OC_SS_MAX:
            out[t] = {"s": e["s"], "sec": _int(e.get("sec")), "n": _int(e.get("n")), "tok": _tok(e.get("tok"))}
    return out


def _med(xs):
    xs = sorted(xs)
    k = len(xs)
    return (xs[k // 2] if k % 2 else int((xs[k // 2 - 1] + xs[k // 2]) / 2 + 0.5)) if k else None


def stage_eff(rows):
    """{title: {n, sec, tok, tn}} over ledger rows: n runs that reached the stage, median seconds, median of the known
    token counts (None when none known), tn = how many were known. Skipped stages are not counted."""
    acc = {}
    for r in rows or ():
        for t, e in ((r or {}).get("ss") or {}).items():
            if e.get("s") == "skip" or (t not in acc and len(acc) >= OC_SS_MAX):
                continue
            a = acc.setdefault(t, ([], []))
            a[0].append(e.get("sec") or 0)
            if e.get("tok") is not None:
                a[1].append(e["tok"])
    return {t: {"n": len(s), "sec": _med(s), "tok": _med(k), "tn": len(k)} for t, (s, k) in acc.items()}


def run_cost(rows):
    """{share: {title: pct}, med, mn, last: {tok, sec}} over ledger rows (oldest first), or None for no rows.
    Same stage loop as stage_eff so titles match. ⚠Unknown tok is left out, never counted as 0: a run with no known
    tok is not in med/mn, and last.tok is None."""
    if not rows:
        return None
    acc, per, last, kn = {}, [], None, set()
    for r in rows:
        known = None
        for t, e in ((r or {}).get("ss") or {}).items():
            if e.get("s") == "skip" or (t not in acc and len(acc) >= OC_SS_MAX):
                continue
            acc.setdefault(t, 0)   # counted for the OC_SS_MAX cap even when unknown, so titles match stage_eff
            if e.get("tok") is not None:
                acc[t] += e["tok"]
                kn.add(t)
                known = (known or 0) + e["tok"]
        if known is not None:   # ⚠a run with some unknown stages counts its known part only (a lower bound)
            per.append(known)
        last = known
    tot = sum(acc.values())
    # A stage with no known tok in any run has no share (dash on screen), not 0%.
    share = {t: int(v * 100 / tot + 0.5) for t, v in acc.items() if t in kn} if tot else {}
    r = rows[-1] or {}
    sec = int(max(0, (r.get("end") or 0) - (r.get("t0") or 0)))
    return {"share": share, "med": _med(per), "mn": len(per), "last": {"tok": last, "sec": sec}}


def _ledger_path(key):
    return os.path.join(OC_EVAL_DIR, key, "runs.jsonl")


def ledger(key, since):
    """Ledger rows of repo `key` that ended at/after `since`, oldest first; [] when missing or unreadable."""
    try:
        with open(_ledger_path(key), "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - OC_LEDGER_READ_MAX))
            lines = f.read(OC_LEDGER_READ_MAX).split(b"\n")
    except (OSError, ValueError):
        return []
    if size > OC_LEDGER_READ_MAX:
        lines = lines[1:]   # ⚠first line of a mid-file seek is partial
    out, seen = [], {}
    for ln in lines:
        try:
            r = _row(json.loads(ln.decode("utf-8")))
        except ValueError:
            continue
        if not (r and r["end"] >= since):
            continue
        k = (r["name"], r["t0"])
        if k in seen:   # ⚠same run closed from two sessions' runs files (older ledgers): one run, the later close wins
            out[seen[k]] = r
            continue
        seen[k] = len(out)
        out.append(r)
    return out


def _log(repo, since, budget):
    """[(sha, ct, [files])] newest first from one `git log --name-only` back to `since`, or None on a git miss."""
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    out = _git(repo, ["log", "-n", str(OC_LOG_MAX), "--since=@%d" % int(since), "--format=%x1e%H%x1f%ct", "--name-only", "HEAD"])
    if not out or out[0] != 0:
        return None
    rows = []
    for rec in out[1].split("\x1e")[1:]:
        head, _, rest = rec.partition("\n")
        sha, _, ct = head.partition("\x1f")
        if not OC_HEX.fullmatch(sha.strip()) or not ct.strip().isdigit():
            continue
        rows.append((sha.strip(), int(ct.strip()), [x for x in (ln.strip() for ln in rest.splitlines()) if x]))
    return rows


def _resolve(p, end, log):
    """Index in `log` of the commit the PASS checked: its head when clean, else the first commit after the PASS that
    landed before its run ended (+60 s); -1 = unchecked."""
    if p["head"] and not p["dirty"]:
        return next((i for i, c in enumerate(log) if c[0].startswith(p["head"])), -1)
    hit = [i for i, c in enumerate(log) if p["ts"] <= c[1] <= end + OC_POST_S]
    return hit[-1] if hit else -1   # log is newest first: the last hit is the first commit


def _passes(rows, runs, since):
    """[(pass row, run row)] of PASS evidence in a run window, newest first, ≤ OC_PASS_MAX."""
    out = []
    for r in rows:
        if not (isinstance(r, dict) and r.get("kind") == "check" and r.get("rc") == 0):
            continue
        ts = _num(r.get("ts"))
        if ts < since:
            continue
        w = next((x for x in runs if x["t0"] - OC_PRE_S <= ts <= x["end"] + OC_POST_S), None)
        if w:
            head = r.get("head") if isinstance(r.get("head"), str) and OC_HEX.fullmatch(r["head"]) else ""
            out.append(({"ts": ts, "head": head, "dirty": r.get("dirty") is True}, w))
    out.sort(key=lambda x: -x[0]["ts"])
    return out[:OC_PASS_MAX]


def _lb(runs, review):
    k = sum(1 for r in runs if any(e["f"] in review for e in r["lb"]))
    return {"n": len(runs), "k": k}


def _after(proj, sha, budget, memo):
    """Set of commits on the ancestry path sha..HEAD (descendants of sha), or None on a git miss / spent budget.
    ⚠Not «newer in log order»: a side-branch commit merged later is not a fix of this PASS."""
    if sha in memo:
        return memo[sha]
    out = None
    if budget[0] > 0:
        budget[0] -= 1
        r = _git(proj, ["rev-list", "--ancestry-path", "%s..HEAD" % sha])
        if r and r[0] == 0:
            out = set(x.strip() for x in r[1].splitlines() if OC_HEX.fullmatch(x.strip()))
    memo[sha] = out
    return out


def _result(proj, rows, runs, now, git, every=None, fix=()):
    """n = distinct commits the PASSes resolved to; unchecked = dirty PASSes with no landed commit plus commits git did
    not answer for; partial = some git call failed or ran out of budget. `every` = ledger rows of all pipelines (commit
    ownership), `fix` = bug-fix pipeline names: only a commit owned by a fix run can be «fix followed»."""
    since = now - OC_WIN_S
    every = runs if every is None else every
    fix = set(fix or ())
    ps = _passes(rows, runs, since)
    res = {"n": 0, "broke": 0, "fixed": 0, "unchecked": 0, "partial": False, "list": []}
    if not ps:
        return res
    st = {s["ts"]: s for s in harness_trail.states(rows, proj, since, git=git, only=set(p["ts"] for p, _e in ps))}
    budget, memo = [OC_SPAWN_MAX], {}
    log = _log(proj, since - OC_DAY, budget) if git else None
    if not log:
        res["unchecked"], res["partial"] = len(ps), bool(git)
        return res
    groups = {}   # resolved log index -> [(pass, run row)]: several PASSes on one commit are one entry
    for p, w in ps:
        i = _resolve(p, w["end"], log)
        if i < 0:
            res["unchecked"] += 1   # unresolved dirty PASS is a fact, not a git miss
            continue
        groups.setdefault(i, []).append((p, w))
    for i in sorted(groups, key=lambda j: -max(p["ts"] for p, _e in groups[j])):
        g = groups[i]
        aft = _after(proj, log[i][0], budget, memo)
        known = [st.get(p["ts"]) or {} for p, _w in g
                 if not ((st.get(p["ts"]) or {}).get("state") == "unchecked" and not p["dirty"])]
        if aft is None or not known:
            res["unchecked"] += 1
            res["partial"] = True
            continue
        sha, ct, files = log[i]
        fs = set(files)
        ts = max(p["ts"] for p, _w in g)
        own = set(id(w) for _p, w in g)
        floor = max(w["end"] for _p, w in g) + OC_POST_S
        code = set(f for f in fs if _code(f))
        # ⚠any later commit sharing a file read as a fix (feature follow-ups, CHANGELOG): it counts only when a fix
        # run made it, the run is not the PASS's own, and the overlap is on code files
        # ⚠floor: a fix run nested in the PASS's own run and ending with it would otherwise own that run's last commit
        fixed = bool(code) and any(c[0] in aft and floor < c[1] and c[1] - ts <= OC_FIX_S and code & set(c[2])
                                   and _isfix(c[1], every, fix, own) for c in log[:i])
        broke = any(h.get("state") in ("broke", "reverted", "gone") for h in known)
        res["n"] += 1
        res["broke"] += broke
        res["fixed"] += fixed
        res["list"].append({"sha": sha[:12], "files": sorted(fs)[:OC_FILES_MAX], "broke": broke, "fixed": fixed})
    return res


def _isfix(ct, every, fix, own):
    o = _owner(ct, every)
    return o is not None and o["name"] in fix and id(o) not in own


def outcome(proj, name, review_titles, now=None, git=True, fix=()):
    """{proc: {runs, jump}, lb: {cur: {n, k}, prev: {n, k}}, result: {n, broke, fixed, list: [{sha, files, broke, fixed}]}}.
    `fix` = bug-fix pipeline names (`pipeline.fix_pipes`), passed in: this core module must not import the pipeline feature.
    ⚠`list` carries file names: the report writes it, the API body drops it (pl_eval_view)."""
    now = _now() if now is None else now
    key = repo_key(proj)
    every = ledger(key, now - 2 * OC_WIN_S)
    runs = [r for r in every if r["name"] == name]
    fix = sorted(set(f for f in fix or () if isinstance(f, str)))
    cur = [r for r in runs if r["end"] >= now - OC_WIN_S]
    prev = [r for r in runs if r["end"] < now - OC_WIN_S]
    review = set(t for t in review_titles or () if isinstance(t, str))
    rows = harness_evidence.scan(proj)[0]
    head = ""
    if git:
        h = _git(proj, ["rev-parse", "--verify", "-q", "HEAD"])
        head = h[1].strip() if h and h[0] == 0 else ""
    try:
        mt = os.path.getmtime(_ledger_path(key))
    except OSError:
        mt = 0
    ck = (os.path.realpath(proj), name, tuple(sorted(review)), head, rows[0]["ts"] if rows else 0, mt, int(now // 600), tuple(fix))
    if head and ck in _OC_MEMO:
        return _OC_MEMO[ck]
    out = {"proc": {"runs": len(cur), "jump": sum(r["dc"].get("jump", 0) for r in cur)},
           "lb": {"cur": _lb(cur, review), "prev": _lb(prev, review)},
           "result": _result(proj, rows, cur + prev, now, bool(head), every, fix), "eff": stage_eff(cur),
           "cost": run_cost(cur)}
    if head:
        if len(_OC_MEMO) >= OC_CACHE_MAX:
            _OC_MEMO.clear()
        _OC_MEMO[ck] = out
    return out


def counts(oc):
    """outcome() without the per-PASS list (what the API may carry), or None. `eff` = stage titles and numbers only."""
    if not isinstance(oc, dict):
        return None
    p, lb, r = oc.get("proc") or {}, oc.get("lb") or {}, oc.get("result") or {}
    ef = oc.get("eff") if isinstance(oc.get("eff"), dict) else {}
    eff = {_title(t): {"n": _int(e.get("n")), "sec": _int(e.get("sec")), "tok": _tok(e.get("tok")), "tn": _int(e.get("tn"))}
           for t, e in list(ef.items())[:OC_SS_MAX] if _title(t) and isinstance(e, dict) and _int(e.get("n"))}
    nk = lambda d: {"n": _int((d or {}).get("n")), "k": min(_int((d or {}).get("k")), _int((d or {}).get("n")))}
    out = {"proc": {"runs": _int(p.get("runs")), "jump": _int(p.get("jump"))},
            "lb": {"cur": nk(lb.get("cur")), "prev": nk(lb.get("prev"))},
            "result": {"n": _int(r.get("n")), "broke": _int(r.get("broke")), "fixed": _int(r.get("fixed")),
                       "unchecked": _int(r.get("unchecked")), "partial": r.get("partial") is True}}
    if eff:   # absent when empty: rows without per-stage data keep the earlier body shape
        out["eff"] = eff
    co = oc.get("cost") if isinstance(oc.get("cost"), dict) else {}
    sh = co.get("share") if isinstance(co.get("share"), dict) else {}
    la = co.get("last") if isinstance(co.get("last"), dict) else {}
    if co:   # same «absent when empty» rule as eff
        out["cost"] = {"share": {_title(t): min(100, _int(v)) for t, v in sh.items() if _title(t) in eff},
                       "med": _tok(co.get("med")), "mn": _int(co.get("mn")),
                       "last": {"tok": _tok(la.get("tok")), "sec": _int(la.get("sec"))}}
    out["verdict"] = _verdict(out)
    return out


def _verdict(c):
    """R1 on a counts() body: first match of broke, too few runs, loop-back rise, else healthy."""
    if c["result"]["broke"] >= 1:
        return "pl_broke"
    if c["proc"]["runs"] < OC_VERDICT_MIN_RUNS:
        return "pl_too_few"
    cur, prev = c["lb"]["cur"], c["lb"]["prev"]
    if prev["n"] and _pct(cur) - _pct(prev) >= OC_LB_RISE_PP:   # ⚠no earlier runs is unknown, never a 0% baseline
        return "pl_loopback"
    return "healthy"


def verdict(oc):
    """R1 verdict id (a key of OC_VERDICT) of an outcome() or counts() body; pure."""
    return (counts(oc) or counts({}))["verdict"]


def report_dir(proj, name):
    """eval/<key>/reports/<pipeline>/ — one folder per pipeline so each keeps its own weekly cadence."""
    return os.path.join(OC_EVAL_DIR, repo_key(proj), "reports", name)


def _legacy_reports(d, name):
    """Flat reports/YYYY-MM-DD.md written before the per-pipeline folders, kept only when its title names `name`."""
    out = []
    try:
        names = [n for n in os.listdir(d) if OC_DATE.fullmatch(n)]
    except OSError:
        return out
    head = "# Pipeline report: %s" % name
    for n in names:
        if _first_line(os.path.join(d, n)) == head:
            out.append((n, os.path.join(d, n)))
    return out


def _first_line(path):
    """First line of a small text file, "" when unreadable (an unreadable old report simply does not count)."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.readline().rstrip("\n")
    except (OSError, ValueError):
        return ""


def latest_report(proj, name):
    """{date, path} of the newest report of pipeline `name`, or None.
    ⚠Keyed by pipeline: with one folder per repo the first pipeline to close each week blocked every other one."""
    d = report_dir(proj, name)
    try:
        found = [(n, os.path.join(d, n)) for n in os.listdir(d) if OC_DATE.fullmatch(n)]
    except OSError:
        found = []
    found += _legacy_reports(os.path.dirname(d), name)
    if not found:
        return None
    n, p = max(found)
    return {"date": n[:10], "path": p}


def _pct(nk):
    return int(nk["k"] * 100 / nk["n"] + 0.5) if nk["n"] else 0   # round half up, same as the panel's Math.round


def sentences(gate, oc, lang="en"):
    """Result-layer fact sentences (OC_SENT, English) in panel order; the loop-back line is dropped with no runs at all.
    `lang` is reserved: the report is English, the panel translates the same keys through I18N."""
    g = gate if isinstance(gate, dict) else {}
    c = counts(oc) or counts({})
    out = [OC_SENT["gate"].format(g=_int(g.get("n")), m=_int(g.get("m"))),
           OC_SENT["proc"].format(**c["proc"]),
           OC_SENT["result"].format(**c["result"])]
    cur, prev = c["lb"]["cur"], c["lb"]["prev"]
    if prev["n"]:
        out.append(OC_SENT["lb"].format(cur=_pct(cur), prev=_pct(prev)))
    elif cur["n"]:
        out.append(OC_SENT["lb1"].format(cur=_pct(cur)))
    return out
