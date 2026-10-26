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
_OC_MEMO = {}   # (repo, name, review, HEAD, newest evidence ts, ledger mtime, 10-min bucket) -> outcome
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
            "dc": {c: _int(dc.get(c)) for c in OC_DENY_CODES if _int(dc.get(c))}, "h0": hx(d.get("h0")), "h1": hx(d.get("h1"))}


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
    out = []
    for ln in lines:
        try:
            r = _row(json.loads(ln.decode("utf-8")))
        except ValueError:
            continue
        if r and r["end"] >= since:
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
    """[(pass row, run end)] of PASS evidence in a run window, newest first, ≤ OC_PASS_MAX."""
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
            out.append(({"ts": ts, "head": head, "dirty": r.get("dirty") is True}, w["end"]))
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


def _result(proj, rows, runs, now, git):
    """n = PASSes whose commit was resolved; unchecked = attributed PASSes that could not be (dirty with no landed commit,
    or git did not answer); partial = some git call failed or ran out of budget."""
    since = now - OC_WIN_S
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
    for p, end in ps:
        h = st.get(p["ts"]) or {}
        i = _resolve(p, end, log)
        aft = _after(proj, log[i][0], budget, memo) if i >= 0 else None
        if i < 0 or aft is None or (h.get("state") == "unchecked" and not p["dirty"]):
            res["unchecked"] += 1
            res["partial"] = res["partial"] or i >= 0   # unresolved dirty PASS is a fact; a git miss is not
            continue
        sha, ct, files = log[i]
        fs = set(files)
        fixed = bool(fs) and any(c[0] in aft and c[1] - p["ts"] <= OC_FIX_S and fs & set(c[2]) for c in log[:i])
        broke = h.get("state") in ("broke", "reverted", "gone")
        res["n"] += 1
        res["broke"] += broke
        res["fixed"] += fixed
        res["list"].append({"sha": sha[:12], "files": sorted(fs)[:OC_FILES_MAX], "broke": broke, "fixed": fixed})
    return res


def outcome(proj, name, review_titles, now=None, git=True):
    """{proc: {runs, jump}, lb: {cur: {n, k}, prev: {n, k}}, result: {n, broke, fixed, list: [{sha, files, broke, fixed}]}}.
    ⚠`list` carries file names: the report writes it, the API body drops it (pl_eval_view)."""
    now = _now() if now is None else now
    key = repo_key(proj)
    runs = [r for r in ledger(key, now - 2 * OC_WIN_S) if r["name"] == name]
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
    ck = (os.path.realpath(proj), name, tuple(sorted(review)), head, rows[0]["ts"] if rows else 0, mt, int(now // 600))
    if head and ck in _OC_MEMO:
        return _OC_MEMO[ck]
    out = {"proc": {"runs": len(cur), "jump": sum(r["dc"].get("jump", 0) for r in cur)},
           "lb": {"cur": _lb(cur, review), "prev": _lb(prev, review)},
           "result": _result(proj, rows, cur + prev, now, bool(head))}
    if head:
        if len(_OC_MEMO) >= OC_CACHE_MAX:
            _OC_MEMO.clear()
        _OC_MEMO[ck] = out
    return out


def counts(oc):
    """outcome() without the per-PASS list (what the API may carry), or None."""
    if not isinstance(oc, dict):
        return None
    p, lb, r = oc.get("proc") or {}, oc.get("lb") or {}, oc.get("result") or {}
    nk = lambda d: {"n": _int((d or {}).get("n")), "k": min(_int((d or {}).get("k")), _int((d or {}).get("n")))}
    return {"proc": {"runs": _int(p.get("runs")), "jump": _int(p.get("jump"))},
            "lb": {"cur": nk(lb.get("cur")), "prev": nk(lb.get("prev"))},
            "result": {"n": _int(r.get("n")), "broke": _int(r.get("broke")), "fixed": _int(r.get("fixed")),
                       "unchecked": _int(r.get("unchecked")), "partial": r.get("partial") is True}}


def latest_report(proj):
    """{date, path} of the newest eval/<key>/reports/YYYY-MM-DD.md, or None."""
    d = os.path.join(OC_EVAL_DIR, repo_key(proj), "reports")
    try:
        names = sorted(n for n in os.listdir(d) if OC_DATE.fullmatch(n))
    except OSError:
        return None
    return {"date": names[-1][:10], "path": os.path.join(d, names[-1])} if names else None


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
