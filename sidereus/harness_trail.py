"""Harness «Results» trail: `trail(rows, repo, git)` → «Red→Green» (FAIL→PASS pairs per mode) and «Pass stability» (did each PASS hold).

⚠Metadata only: reads ts · head/tree hashes · counts · whitelisted step names. Git is read-only and hash-only
  (rev-parse · merge-base --is-ancestor · log %H%x09%T · rev-list --count) — never subjects, file names, diffs or --stat.
"""
import re
import subprocess
import time

from sidereus import gitinfo

TR_MAX = 5                 # newest pairs / newest PASS rows returned
TR_GIT_TIMEOUT = 2
TR_GIT_WAIT = 0.5          # slot wait; a miss reads as a git failure (not cached)
TR_SPAWN_MAX = 12          # git processes per call (HEAD lookup included)
TR_LOG_MAX = 50            # commits after a PASS head scanned for a tree rollback
TR_HEAD_TTL = 20           # seconds the resolved HEAD is reused, so a repaint spawns nothing
TR_CACHE_MAX = 64
TR_STATES_MAX = 30         # PASS rows states() returns
TR_STATES_GIT = 4          # git processes budgeted per PASS in states() (merge-base · rev-parse · log, + slack)
TR_INC_MAX = 20            # newest incident cards report() returns
TR_HEX = re.compile(r"[0-9a-f]{4,40}")
TR_MODE = re.compile(r"[a-z0-9_-]{0,20}")
TR_STEP = re.compile(r"[a-z0-9_-]{1,20}")
_TR_CACHE = {}             # (repo, HEAD, newest ts) -> result · ("head", repo) -> (at, HEAD)
_now = time.time


def _git(repo, args):
    """(returncode, stdout) of a read-only git call, or None on timeout/spawn failure. Tests patch this."""
    try:
        r = gitinfo._git_run(repo, args, TR_GIT_TIMEOUT, wait=TR_GIT_WAIT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.returncode, r.stdout or ""


def _norm(r):
    """Whitelisted copy of one evidence row, or None for junk."""
    if not isinstance(r, dict) or r.get("kind") != "check":
        return None
    ts, rc, mode = r.get("ts"), r.get("rc"), r.get("mode")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts <= 0:
        return None
    if isinstance(rc, bool) or not isinstance(rc, int) or not isinstance(mode, str) or not TR_MODE.fullmatch(mode):
        return None
    steps, failed = [], 0
    for s in r.get("steps") if isinstance(r.get("steps"), list) else []:
        if isinstance(s, dict) and isinstance(s.get("name"), str) and TR_STEP.fullmatch(s["name"]) \
                and isinstance(s.get("rc"), int) and not isinstance(s.get("rc"), bool):
            steps.append((s["name"], s["rc"]))
            f = s.get("failed")
            failed += f if isinstance(f, int) and not isinstance(f, bool) and f > 0 else 0
    head = r.get("head") if isinstance(r.get("head"), str) and TR_HEX.fullmatch(r["head"]) else ""
    return {"ts": float(ts), "mode": mode, "rc": rc, "head": head, "dirty": r.get("dirty") is True, "steps": steps,
            "failed": failed}


class _Ctx(object):
    """Per-call git budget + memo; `ok` drops to False on the first git failure."""

    def __init__(self, repo, on, cap=None):
        self.repo, self.on, self.ok, self.n, self.memo = repo, on, True, 0, {}
        self.cap = cap or TR_SPAWN_MAX

    def run(self, args):
        key = tuple(args)
        if key in self.memo:
            return self.memo[key]
        if not self.on:
            return None
        if self.n >= self.cap:
            self.ok = False   # capped rows are incomplete — never cache them as a final answer
            return None
        self.n += 1
        out = _git(self.repo, args)
        if out is None:
            self.ok = False
        self.memo[key] = out
        return out


def _head(ctx):
    hit = _TR_CACHE.get(("head", ctx.repo))
    if hit and _now() - hit[0] < TR_HEAD_TTL:
        return hit[1]
    out = ctx.run(["rev-parse", "--verify", "-q", "HEAD"])
    h = out[1].strip() if out and out[0] == 0 else ""
    if not TR_HEX.fullmatch(h):
        return ""
    _TR_CACHE[("head", ctx.repo)] = (_now(), h)
    return h


def _pairs(rows):
    """[(fail, pass)] per mode, oldest first: the latest FAIL before a PASS pairs with that PASS."""
    last, out = {}, []
    for r in rows:
        if r["rc"] != 0:
            last[r["mode"]] = r
        elif r["mode"] in last:
            out.append((last.pop(r["mode"]), r))
    return out


def _fix(f, p, ctx):
    fs, ps = dict(f["steps"]), dict(p["steps"])
    flipped = [n for n in fs if fs[n] != 0 and ps.get(n) == 0]
    still = [n for n in fs if n in ps and fs[n] != 0 and ps[n] != 0]   # failed in both runs; a step only one run had is not «still»
    commits = None
    if f["head"] and p["head"] and not p["dirty"]:
        if f["head"] == p["head"]:
            commits = 0
        else:
            out = ctx.run(["rev-list", "--count", "%s..%s" % (f["head"], p["head"])])
            commits = int(out[1].strip()) if out and out[0] == 0 and out[1].strip().isdigit() else None
    pub = lambda r: {"ts": r["ts"], "head": r["head"], "dirty": r["dirty"]}
    return {"mode": p["mode"], "fail": pub(f), "pass": pub(p), "commits": commits, "flipped": flipped, "still": still}


def _evidence_state(p, later):
    """(state, steps, at) from later rows of the same mode: an overlapping FAIL breaks it, a PASS after that refixes it."""
    ok = set(n for n, rc in p["steps"] if rc == 0)
    st, steps, at = "held", [], 0
    for r in later:
        if r["rc"] != 0:
            hit = [n for n, rc in r["steps"] if rc != 0 and n in ok]
            if hit and st != "broke":
                st, steps, at = "broke", hit, r["ts"]
        elif st == "broke":
            st = "refixed"
    return st, steps, at


def _git_state(p, ctx, head):
    """(state, git) for a clean «held» PASS: gone when not an ancestor of HEAD, reverted when a later commit's tree equals head^'s."""
    if p["head"] == head[:len(p["head"])]:
        return "held", True
    anc = ctx.run(["merge-base", "--is-ancestor", p["head"], "HEAD"])
    if not anc or anc[0] not in (0, 1):
        return "held", False
    if anc[0] == 1:
        return "gone", True
    par = ctx.run(["rev-parse", "--verify", "-q", p["head"] + "^^{tree}"])
    if par is None:
        return "held", False
    tree = par[1].strip() if par[0] == 0 else ""
    if not TR_HEX.fullmatch(tree):
        return "held", True   # root commit: nothing to roll back to
    log = ctx.run(["log", "-n", str(TR_LOG_MAX), "--format=%H%x09%T", "%s..HEAD" % p["head"]])
    if not log or log[0] != 0:
        return "held", False
    # ⚠Exact one-commit tree rollback only; a partial revert reads as held.
    hit = any(ln.split("\t")[-1].strip() == tree for ln in log[1].splitlines() if "\t" in ln)
    return ("reverted" if hit else "held"), True


def _held(p, rows, ctx, head):
    later = [r for r in rows if r["mode"] == p["mode"] and r["ts"] > p["ts"]]
    st, steps, at = _evidence_state(p, later)
    git = False
    if st == "held" and p["dirty"]:
        st = "unchecked"
    elif st == "held" and p["head"] and head:
        st, git = _git_state(p, ctx, head)
    return {"mode": p["mode"], "ts": p["ts"], "head": p["head"], "dirty": p["dirty"], "state": st, "steps": steps,
            "at": at, "git": git}


def trail(rows, repo, git=True):
    """{"fixes": [...], "held": [...]} newest first (≤TR_MAX each) from newest-first evidence rows of `repo`."""
    rows = sorted((r for r in (_norm(x) for x in (rows if isinstance(rows, list) else [])) if r), key=lambda r: r["ts"])
    if not rows:
        return {"fixes": [], "held": []}
    ctx = _Ctx(repo, bool(git and isinstance(repo, str) and repo))
    head = _head(ctx) if ctx.on else ""
    ctx.on = bool(head)   # no HEAD = not a repo / git down: evidence only, no further spawns
    key = (repo, head, rows[-1]["ts"])
    if head and key in _TR_CACHE:
        return _TR_CACHE[key]
    held = [_held(p, rows, ctx, head) for p in reversed([r for r in rows if r["rc"] == 0][-TR_MAX:])]
    fixes = [_fix(f, p, ctx) for f, p in reversed(_pairs(rows)[-TR_MAX:])]
    out = {"fixes": fixes, "held": held}
    if head and ctx.ok:
        if len(_TR_CACHE) >= TR_CACHE_MAX:
            _TR_CACHE.clear()
        _TR_CACHE[key] = out
    return out


def _cp(mode):
    return mode if mode in ("fast", "full") else "other"


def report(rows, repo, git=True):
    """{counts: {caught, held, again, reverted, gone, unchecked, checked}, incidents, checkpoints: {fast|full|other: {runs, caught, listed}}, since} from
    newest-first evidence rows of `repo`. caught = every FAIL→PASS pair; incidents = the newest TR_INC_MAX pairs, each with
    its PASS state (states() rules) — the state counts tally those incidents only and sum to len(incidents)
    (again = broke | refixed: a later same-mode FAIL of an overlapping step, step-level only). since = oldest row ts read.
    ⚠A git miss or exhausted budget turns a clean «held» into «unchecked» (never «held») and the result is not cached;
    git=False (demo) keeps the evidence-only state."""
    rows = sorted((r for r in (_norm(x) for x in (rows if isinstance(rows, list) else [])) if r), key=lambda r: r["ts"])
    cps = dict((k, {"runs": 0, "caught": 0, "listed": 0}) for k in ("fast", "full", "other"))
    if not rows:
        return {"counts": dict((k, 0) for k in ("caught", "held", "again", "reverted", "gone", "unchecked", "checked")), "incidents": [], "checkpoints": cps, "since": 0}
    pairs = _pairs(rows)
    inc = list(reversed(pairs[-TR_INC_MAX:]))
    on = bool(git and isinstance(repo, str) and repo)
    # own budget: per incident one rev-list (_fix) + the states() share, plus the HEAD lookup
    ctx = _Ctx(repo, on, 1 + (TR_STATES_GIT + 1) * max(1, len(inc)))
    head = _head(ctx) if ctx.on else ""
    ctx.on = bool(head)
    key = ("report", repo, head, rows[-1]["ts"])
    if head and key in _TR_CACHE:
        return _TR_CACHE[key]
    incidents = []
    for f, p in inc:
        fx, h = _fix(f, p, ctx), _held(p, rows, ctx, head)
        st = h["state"]
        if on and st == "held" and h["head"] and not h["dirty"] and not h["git"]:
            st = "unchecked"   # head known but git never answered: not evidence that it held
        fx["fail"].update(rc=f["rc"], failed=f["failed"] or None)   # 0 = no failure count recorded (ev_hook rows), not «0 failed»
        incidents.append(dict(fx, cp=_cp(p["mode"]), state=st, at=h["at"]))
    for r in rows:
        cps[_cp(r["mode"])]["runs"] += 1
    for f, p in pairs:
        cps[_cp(p["mode"])]["caught"] += 1
    for x in incidents:
        cps[x["cp"]]["listed"] += 1   # caught > listed = older pairs past TR_INC_MAX
    tally = lambda s: sum(1 for x in incidents if x["state"] == s)
    # ⚠every state lands in exactly one count — a state with no count vanished from the tiles (refixed did)
    out = {"counts": {"caught": len(pairs), "held": tally("held"), "again": tally("broke") + tally("refixed"),
                      "reverted": tally("reverted"), "gone": tally("gone"), "unchecked": tally("unchecked"),
                      "checked": sum(1 for x in incidents if x["state"] != "unchecked")},
           "incidents": incidents, "checkpoints": cps, "since": rows[0]["ts"]}
    if head and ctx.ok:
        if len(_TR_CACHE) >= TR_CACHE_MAX:
            _TR_CACHE.clear()
        _TR_CACHE[key] = out
    return out


def states(rows, repo, since, git=True, only=None):
    """Held state of every PASS with ts >= since (and ts in `only` when given), newest first (<= TR_STATES_MAX).
    Same rules as trail()["held"]; ⚠a git miss or exhausted budget turns a clean «held» into «unchecked», never «held».
    Not cached here (pl_outcome caches its whole result)."""
    rows = sorted((r for r in (_norm(x) for x in (rows if isinstance(rows, list) else [])) if r), key=lambda r: r["ts"])
    ps = [r for r in rows if r["rc"] == 0 and r["ts"] >= since and (only is None or r["ts"] in only)][-TR_STATES_MAX:]
    if not ps:
        return []
    ctx = _Ctx(repo, bool(git and isinstance(repo, str) and repo), 1 + TR_STATES_GIT * len(ps))
    head = _head(ctx) if ctx.on else ""
    ctx.on = bool(head)
    out = [_held(p, rows, ctx, head) for p in reversed(ps)]
    for h in out:
        if h["state"] == "held" and h["head"] and not h["dirty"] and not h["git"]:
            h["state"] = "unchecked"   # head known but git never answered: not evidence that it held
    return out
