#!/usr/bin/python3
"""Pipeline evaluation CLI (core: sidereus/pl_eval.py). Writes only temp clones and DATA_DIR/eval/.

usage: pl_eval.py seeds --repo R (--set F | --check) | score --repo R --pipeline P.json [--findings F] [--auto] | redcheck --pipeline P.json --stage <title> --repo R [--timeout 600]
  seeds     validate seeds.json F and store it (0600), or validate the stored one; prints counts, never holdout ids.
  score     match the stored seeds against each stage's findings at HEAD (checks-* gate mode -> its checks file;
            --findings F = extra tool-less findings [{file, line, rule?}]) -> eval.json + one evidence row (kind eval).
            Prints «caught a/b · holdout c/d»; exit 0 only if every public seed was caught.
            --auto (pl_flow hook at run end, detached): waits out an in-progress commit, then scores only once per
            (pipeline, commit) — claim file eval/<key>/<commit>/auto-<pipeline> holds «run» then «done»; a «run» older
            than AUTO_STALE_S (crashed) is retaken. --since T (run closed by a `git commit` Pre): score only when HEAD's
            commit time >= T, i.e. the commit landed (a denied or cancelled commit leaves the old HEAD).
  redcheck  clone R (--shared) to a temp dir, inject one break for the stage's gate mode, run the producer and the gate
            there (MAILBOX_DIR / SIDEREUS_EVIDENCE in the temp dir) and record pass|fail|skip under sha1(gate)[:16].
            ⚠R itself must be unchanged (HEAD + status) or the verdict is fail «target changed». Missing tool = skip.
"""
import base64
import hashlib
import json
import os
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_UP = os.path.dirname(_HERE)
if not os.path.isdir(os.path.join(_UP, "sidereus")):   # pipx/uv: sidereus/_bundle/scripts -> site-packages
    _UP = os.path.dirname(os.path.dirname(_UP))
sys.path.insert(0, _UP)
sys.path.insert(0, _HERE)
from sidereus import config  # noqa: E402  (path set just above)
from sidereus import pl_eval as PE  # noqa: E402
from sidereus import arch_verify as AV  # noqa: E402
from sidereus.gitinfo import git_argv, git_env  # noqa: E402
from sidereus.pipeline_schema import gate_mode  # noqa: E402
import evidence_rec  # noqa: E402

_which = shutil.which   # tests patch this, never PATH
_now = time.time        # tests patch this
_sleep = time.sleep      # tests patch this
AUTO_SETTLE_S, AUTO_LOCK_MAX_S = 2.0, 300   # --auto: the hook fires on a `git commit` Pre, before the commit lands
AUTO_STALE_S = 600
_SKIP = {".git", "node_modules", "build", "target", "dist", "out", ".venv", "venv", "__pycache__", ".gradle"}
_SHELL = ("&&", "||", ";", "|", ">", "<", "&")
RED_TOOLS = {"checks-security": ("gitleaks",)}
RED_RC = {"pass": 0, "fail": 1, "skip": 2}


def _git(repo, args, timeout=60):
    """stdout of one git command, None on failure."""
    try:
        r = subprocess.run(git_argv(repo, args), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=git_env(), stdin=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError):
        return None
    return r.stdout if r.returncode == 0 else None


def _snap(repo):
    """(HEAD, porcelain) of repo, None when it is not a git repo with a commit."""
    head = (_git(repo, ["rev-parse", "HEAD"]) or "").strip()
    if not AV.COMMIT_RE.fullmatch(head):
        return None
    return head, _git(repo, ["status", "--porcelain"])


def _run(argv, cwd, env, timeout):
    """(rc, timed_out). Output is discarded (metadata only). ⚠Own process group, killed whole on timeout."""
    try:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return 127, False
    try:
        return p.wait(timeout=max(1, timeout)), False
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        p.wait()
        return -1, True


def _kill_tree(p):
    """Kill p and its children. ⚠Windows has no killpg/SIGKILL: taskkill /T walks the tree."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, AttributeError, subprocess.SubprocessError):
        pass
    try:
        p.kill()   # the direct child too, in case the tree kill failed
    except OSError:
        pass


def _load(fp):
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _record(row):
    """Append one evidence row (best effort: never changes the exit code)."""
    try:
        ev = os.environ.get("SIDEREUS_EVIDENCE") or os.path.join(config.DATA_DIR, "evidence.jsonl")
        return evidence_rec.append(ev, json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:   # noqa: BLE001 — recording is best effort
        return False


def _fmt(c):
    return "seeds: %d (public %d · holdout %d)" % (c["n"], c["public"], c["holdout"])


def cmd_seeds(repo, set_f, check):
    if set_f:
        d = _load(set_f)
        errs = PE.seed_errors(d)
        if errs:
            return 1, "seeds: invalid: " + "; ".join(errs[:5])
        PE.save_seeds(repo, d)
        return 0, _fmt(PE.counts(d))
    d = _load(os.path.join(PE.EVAL_DIR, AV.repo_key(repo), "seeds.json"))
    if d is None:
        return 1, "seeds: none stored for this repo"
    errs = PE.seed_errors(d)
    return (1, "seeds: invalid: " + "; ".join(errs[:5])) if errs else (0, _fmt(PE.counts(d)))


def _settle(repo):
    """--auto: wait while a commit is in progress (index.lock), at most AUTO_LOCK_MAX_S."""
    _sleep(AUTO_SETTLE_S)
    lock = (_git(repo, ["rev-parse", "--git-path", "index.lock"]) or "").strip()
    if not lock:
        return
    lock = lock if os.path.isabs(lock) else os.path.join(repo, lock)
    end = _now() + AUTO_LOCK_MAX_S
    while os.path.exists(lock) and _now() < end:
        _sleep(1.0)


def _claim(repo, head, name):
    """Claim path once per (pipeline, commit), else None: O_EXCL «run»; «done» never again; a stale «run» is retaken."""
    fp = os.path.join(PE.EVAL_DIR, AV.repo_key(repo), head, "auto-" + name)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    try:
        fd = os.open(fp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            with open(fp, encoding="utf-8") as f:
                st = f.read().strip()
            age = time.time() - os.path.getmtime(fp)   # ⚠file clock, not _now: mtime is wall time
        except OSError:
            return None
        if st == "done" or age < AUTO_STALE_S:
            return None
        fd = os.open(fp, os.O_WRONLY | os.O_TRUNC)
    os.write(fd, b"run")
    os.close(fd)
    return fp


def _claim_done(fp):
    with open(fp, "w", encoding="utf-8") as f:
        f.write("done")


def cmd_score(repo, pfile, findings_f, auto=False, since=None):
    P = _load(pfile)
    stages = [s for s in (P.get("stages") if isinstance(P, dict) else None) or [] if isinstance(s, dict)]
    if not stages:
        return 2, "score: pipeline has no stages"
    stem = os.path.basename(pfile)[:-5] if pfile.endswith(".json") else ""
    name = P.get("name") if isinstance(P.get("name"), str) and P.get("name") else stem   # files need not carry their name
    seeds = PE.load_seeds(repo)
    if seeds is None:
        return 2, "score: no valid seeds stored — run `seeds --set` first"
    if auto:
        if not PE.SEED_ID.fullmatch(name or ""):
            return 2, "score: pipeline name"
        _settle(repo)
    snap = _snap(repo)
    if snap is None:
        return 2, "score: not a git repo with a commit"
    if since is not None:
        ct = (_git(repo, ["log", "-1", "--format=%ct", "HEAD"]) or "").strip()
        if not ct.isdigit() or int(ct) < since:
            return 0, "score: the commit did not land"
    claim = _claim(repo, snap[0], name) if auto else None
    if auto and claim is None:
        return 0, "score: already scored at this commit"
    extra = PE.clean_findings(_load(findings_f)) if findings_f else []
    head, at = snap[0], round(_now(), 3)
    st, hold, unres = PE.score(seeds["seeds"], stages, lambda i: PE.checks_items(repo, head, gate_mode(stages[i].get("gate"))),
                               extra)
    PE.save_eval(repo, head, name, at, st, hold)
    if claim:
        _claim_done(claim)
    row = PE.eval_row(repo, head, st, at)
    if unres:
        row["rc"] = 1
    _record(row)
    n = sum(s["n"] for s in st) + unres
    c = sum(s["caught"] for s in st)
    line = "caught %d/%d · holdout %d/%d" % (c, n, hold["caught"], hold["n"]) + (" · unresolved %d" % unres if unres else "")
    return (0 if c == n else 1), line


# ── red check ──

def _files(root, exts, prefer="src"):
    """Repo-relative regular files with one of `exts` (no symlinks, skip dirs pruned), `prefer` dir component first."""
    out = []
    for d, dirs, fs in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in _SKIP and not x.startswith("."))
        for f in sorted(fs):
            fp = os.path.join(d, f)
            if f.endswith(exts) and not f.endswith(".d.ts") and not os.path.islink(fp) and os.path.isfile(fp):
                out.append(os.path.relpath(fp, root).replace(os.sep, "/"))
    return sorted(out, key=lambda r: (prefer not in r.split("/")[:-1], r))


def _append(fp, text):
    """Append `text` after 3 blank lines; returns the 1-based line number where `text` starts."""
    with open(fp, encoding="utf-8", errors="replace") as f:
        body = f.read()
    if body and not body.endswith("\n"):
        body += "\n"
    body += "\n\n\n"
    start = body.count("\n") + 1
    with open(fp, "w", encoding="utf-8") as f:
        f.write(body + text)
    return start


def _commit_in(clone, rel):
    """Commit `rel` in the temp clone (fixed identity, no signing, hooks off via GIT_SAFE_OPTS). True on success."""
    if _git(clone, ["add", "--", rel]) is None:
        return False
    return _git(clone, ["-c", "user.name=sidereus-redcheck", "-c", "user.email=redcheck@sidereus.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", "redcheck"]) is not None


def inject(mode, clone):
    """(expected findings, why). Expected = pseudo-seeds for checks-* modes ([] for rc-judged modes); None = nothing
    to break. ⚠Writes inside the clone only (symlinked files are never chosen)."""
    if mode == "checks-security":
        rel = "sidereus-redcheck.cfg"
        # Token derived at run time so no secret-looking literal sits in this source.
        tok = base64.urlsafe_b64encode(hashlib.sha256(("sidereus-red:" + clone).encode()).digest()).decode().rstrip("=")
        with open(os.path.join(clone, rel), "w", encoding="utf-8") as f:
            f.write('api_key = "%s"\n' % tok)
        # ⚠The security producer scans a `git archive HEAD` export, so an untracked injection is never seen: commit it.
        if not _commit_in(clone, rel):
            return None, "commit in clone failed"
        return [{"kind": "secret", "file": rel, "line": 1}], "fake api key in " + rel
    if mode in ("fast", "full"):
        py = _files(clone, (".py",), prefer="sidereus")
        if not py:
            return None, "no .py file to break"
        _append(os.path.join(clone, py[0]), "def sidereus_red_check(:\n")
        return [], "syntax error in " + py[0]
    return None, "gate mode not graded"


def _gate_cwd(pfile, repo, clone):
    """Where the gate runs: the pipeline's project dir, mapped into the clone when it lies inside repo."""
    d = os.path.dirname(os.path.realpath(pfile))
    if os.path.basename(d) == "pipelines" and os.path.basename(os.path.dirname(d)) == ".claude":
        d = os.path.dirname(os.path.dirname(d))
    r = os.path.realpath(repo)
    nd, nr = os.path.normcase(os.path.abspath(d)), os.path.normcase(os.path.abspath(r))   # ⚠Windows: case-blind
    if nd == nr or nd.startswith(nr.rstrip(os.sep) + os.sep):
        return os.path.normpath(os.path.join(clone, os.path.relpath(nd, nr)))
    return d


def _producer(argv, cwd, clone, mode):
    """The runner a checks-* gate verifies: same interpreter + arch_checks.py, `--repo <clone>`."""
    i = next((k for k, x in enumerate(argv) if x.endswith("arch_checks.py")), None)
    if i is None:
        return None
    script = argv[i] if os.path.isabs(argv[i]) else os.path.join(cwd, argv[i])
    return (argv[:i] or [sys.executable]) + [script, "--repo", clone] + \
        (["--category", "security"] if mode == "checks-security" else [])


def _link_modules(repo, clone):
    """Symlink node_modules (top level and one folder down) so JS tools resolve in the clone. Returns rels not linked."""
    missed = []
    for rel in ["node_modules"] + [os.path.join(x, "node_modules") for x in sorted(os.listdir(repo))
                                   if x not in _SKIP and os.path.isdir(os.path.join(repo, x))]:
        src, dst = os.path.join(repo, rel), os.path.join(clone, rel)
        if os.path.isdir(src) and not os.path.lexists(dst) and os.path.isdir(os.path.dirname(dst)):
            if not _link_dir(src, dst):
                missed.append(rel)
    return missed


def _link_dir(src, dst):
    """⚠Windows symlinks need admin or Developer Mode: fall back to a junction (no privilege). False if neither."""
    try:
        os.symlink(src, dst, target_is_directory=True)
        return True
    except (OSError, NotImplementedError, AttributeError):
        if os.name != "nt":
            return False
    try:
        import _winapi   # ⚠never `cmd /c mklink`: cmd parses &|^% in folder names (command injection)
        _winapi.CreateJunction(src, dst)
        return True
    except Exception:
        return False


def _judge_checks(store, clone, head, mode, expect):
    j = _load(os.path.join(store, "arch", AV.repo_key(clone), head, PE.CHECKS_FILES[mode]))
    tools = j.get("tools") if isinstance(j, dict) and isinstance(j.get("tools"), list) else []
    need = RED_TOOLS[mode]
    if not any(isinstance(t, dict) and t.get("id") in need and t.get("status") == "ok" for t in tools):
        return "skip", "tool missing: " + ", ".join(need)
    items = [c for c in (PE._clean(x, lambda t: isinstance(t, str) and t != "") for x in j.get("items") or []) if c]
    if any(PE.matches(s, x) for s in expect for x in items):
        return "pass", "injected item reported"
    return "fail", "injected break not reported"


def _split_gate(gate):
    """argv of a gate. ⚠posix shlex eats backslashes in Windows paths: on nt split non-posix and strip outer quotes."""
    nt = os.name == "nt"
    try:
        argv = shlex.split(gate, posix=not nt)
    except ValueError:
        return []
    if nt:
        argv = [x[1:-1] if len(x) >= 2 and x[0] == x[-1] and x[0] in "\"'" else x for x in argv]
    return argv


def _rmtree(path):
    """Remove the temp tree; never raises. ⚠Windows read-only files (git objects) need chmod before unlink.
    Junctions are not followed (rmtree treats them as links since 3.8), so the real node_modules is safe."""
    def onerror(fn, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            fn(p)
        except Exception:
            pass
    try:
        shutil.rmtree(path, onerror=onerror)
    except Exception:
        pass


def red(pfile, gate, mode, repo, timeout):
    """(verdict, why, head). ⚠checks-* modes: red = the injected item is in the temp checks file (their verify exits 0
    with findings); fast/full: red = gate rc != 0."""
    argv = _split_gate(gate)
    if mode is None:
        return "skip", "gate mode not graded", ""
    if not argv or any(x in _SHELL for x in argv):
        return "skip", "gate is not one plain command", ""
    if not ((os.path.isabs(argv[0]) and os.access(argv[0], os.X_OK)) or _which(argv[0])):
        return "skip", "tool missing: " + os.path.basename(argv[0]), ""
    before = _snap(repo)
    if before is None:
        return "skip", "target is not a git repo with a commit", ""
    t_end = _now() + timeout
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-red-"))
    try:
        clone, store = os.path.join(tmp, "repo"), os.path.join(tmp, "store")
        os.makedirs(store)
        if _git(tmp, ["clone", "--shared", "-q", os.path.realpath(repo), clone], timeout=300) is None:
            verdict, why = "skip", "clone failed"
        else:
            verdict, why = _red_in(pfile, argv, mode, repo, clone, store, tmp, before[0], t_end)
    finally:
        _rmtree(tmp)
    if _snap(repo) != before:
        return "fail", "target changed", before[0]
    return verdict, why, before[0]


def _red_in(pfile, argv, mode, repo, clone, store, tmp, head, t_end):
    missed = _link_modules(repo, clone)
    v, why = _red_gate(pfile, argv, mode, repo, clone, store, tmp, head, t_end)
    if missed and v != "skip":   # a gate failing only because JS tools did not resolve proves nothing
        return "skip", "node_modules not linked: " + ", ".join(missed)
    return v, why


def _red_gate(pfile, argv, mode, repo, clone, store, tmp, head, t_end):
    expect, why = inject(mode, clone)
    if expect is None:
        return "skip", why
    cwd = _gate_cwd(pfile, repo, clone)
    env = dict(os.environ, MAILBOX_DIR=store, SIDEREUS_EVIDENCE=os.path.join(tmp, "ev.jsonl"))
    if mode in PE.CHECKS_FILES:
        prod = _producer(argv, cwd, clone, mode)
        if prod is None:
            return "skip", "no arch_checks.py in the gate"
        _rc, late = _run(prod, cwd, env, t_end - _now())
        if late:
            return "skip", "producer timeout"
    rc, late = _run(argv, cwd, env, t_end - _now())
    if late:
        return "skip", "gate timeout"
    if mode in PE.CHECKS_FILES:   # the producer keys its file by the clone's HEAD, which inject() moved
        return _judge_checks(store, clone, (_snap(clone) or (head,))[0], mode, expect)
    return ("pass", "gate rc %d on a broken repo" % rc) if rc != 0 else ("fail", "gate passed on a broken repo")


def cmd_redcheck(pfile, title, repo, timeout):
    P = _load(pfile)
    st = next((s for s in (P.get("stages") if isinstance(P, dict) else None) or []
               if isinstance(s, dict) and s.get("title") == title), None)
    if st is None:
        return 2, "redcheck: no stage with that title"
    gate = st.get("gate") if isinstance(st.get("gate"), str) else ""
    if not gate.strip():
        return 2, "redcheck: stage has no gate"
    mode, t0 = gate_mode(gate), _now()
    verdict, why, head = red(pfile, gate, mode, repo, timeout)
    PE.save_red(gate, {"pipeline": P.get("name") if isinstance(P.get("name"), str) else "", "stage": title,
                       "mode": mode or "", "key": AV.repo_key(repo), "verdict": verdict, "why": why, "at": round(t0, 3),
                       "ms": int(max(0, _now() - t0) * 1000)})
    _record(PE.red_row(repo, head, mode or "none", verdict, t0))
    return RED_RC[verdict], "redcheck: %s — %s" % (verdict, why)


def _args(argv):
    if not argv or argv[0] not in ("seeds", "score", "redcheck"):
        return None
    a = {"cmd": argv[0], "repo": None, "set": None, "check": False, "pipeline": None, "findings": None, "stage": None,
         "timeout": "600", "auto": False, "since": None}
    it = iter(argv[1:])
    for x in it:
        if x == "--check":
            a["check"] = True
        elif x == "--auto" and argv[0] == "score":
            a["auto"] = True
        elif x == "--since" and argv[0] == "score":
            v = next(it, "")
            if not v.isdigit():
                return None
            a["since"] = int(v)
        elif x in ("--repo", "--set", "--pipeline", "--findings", "--stage", "--timeout"):
            a[x[2:]] = next(it, None)
            if not a[x[2:]]:
                return None
        else:
            return None
    if not (a["repo"] and os.path.isdir(a["repo"])) or not a["timeout"].isdigit():
        return None
    a["repo"], a["timeout"] = os.path.realpath(a["repo"]), int(a["timeout"])
    if a["cmd"] == "seeds":
        return a if bool(a["set"]) != a["check"] else None
    if a["cmd"] == "score":
        return a if a["pipeline"] else None
    return a if a["pipeline"] and a["stage"] else None


def main(argv):
    a = _args(argv)
    if a is None:
        print(__doc__.strip().splitlines()[2])
        return 2
    if a["cmd"] == "seeds":
        rc, line = cmd_seeds(a["repo"], a["set"], a["check"])
    elif a["cmd"] == "score":
        rc, line = cmd_score(a["repo"], a["pipeline"], a["findings"], a["auto"], a["since"])
    else:
        rc, line = cmd_redcheck(a["pipeline"], a["stage"], a["repo"], a["timeout"])
    print(line)
    return rc


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # ⚠Windows console codepage cannot encode the em dash / Korean
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
