#!/usr/bin/python3
"""Runner + gate of the security-checks pipeline: run the repo's security scanners, write checks-security.json.

usage: arch_checks.py (--repo <path> | --last | --verify --last) --category security [--only <ids>] [--offline] [--dev]
  --repo / --last   detect scanners (sidereus/sec_checks.py), run each (300 s each, 900 s total), write
                    arch/<key>/<HEAD>/checks-security.json + its last pointer, and one Markdown report
                    arch/<key>/security-report-YYYYMMDD-HHMM.md (scanners, triage, delta, deps; newest 10 kept).
                    Deps = scripts/deps_audit.py lines, only when the repo is this Sidereus checkout;
                    --dev adds its dev tooling lines (node, Chrome, browser drivers).
                    --last = the repo of the last security checks (else of the last map run).
  --category        security (required): gitleaks, npm audit, osv-scanner, semgrep, bandit.
                    --only = comma-separated tool ids. Online lookups (npm audit, osv-scanner, semgrep registry
                    packs) run by default after one reachability probe; unreachable or --offline = skipped.
                    --net is accepted as a no-op (older callers).
  --verify --last   validate the last checks-security.json; exit 1 if invalid, if no tool ran or an ok tool examined
                    0 files (EMPTY).
  --log-review      (--repo | --last) append AI review findings to arch/<key>/security-log.jsonl from stdin TSV
                    `sev<TAB>file:line<TAB>slug<TAB>desc` (sev critical|high|medium|low).
  --log-show        print open AI review findings (sev, file:line, slug).
  --mark <slug>@<file> resolved|false-positive [--commit <sha>]   mark an AI review finding (default commit: HEAD).
Prints one summary line. Only file / line / rule / severity (+ package) are stored — never tool message text or secrets.
"""
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sidereus import arch_checks as AC  # noqa: E402  (path set just above)
from sidereus import arch_verify as AV  # noqa: E402
from sidereus import sec_checks as SC  # noqa: E402
from sidereus import sec_report as SR  # noqa: E402
from sidereus.bus import _atomic_write  # noqa: E402
from sidereus.gitinfo import git_argv, git_env  # noqa: E402


_which = shutil.which   # tests patch this, never PATH
HERE = os.path.dirname(os.path.abspath(__file__))
SIDEREUS_ROOT = os.path.realpath(os.path.dirname(HERE))   # deps lines describe this checkout only
PROBE_URL = "https://api.osv.dev/"


def _probe():
    """True when the advisory services look reachable (one HEAD, 3 s). Any answer counts, even an HTTP error."""
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request(PROBE_URL, method="HEAD"), timeout=3).close()
    except urllib.error.HTTPError:
        return True
    except Exception:   # DNS, connect, TLS, timeout: offline
        return False
    return True


def _git(repo, args):
    """stdout of a read-only git command, None on failure."""
    try:
        r = subprocess.run(git_argv(repo, args), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, env=git_env())
    except (subprocess.SubprocessError, OSError):
        return None
    return r.stdout if r.returncode == 0 else None


def _kill_tree(p):
    """Kill p and its children. ⚠Windows has no killpg/SIGKILL and ignores start_new_session: taskkill /T."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            os.killpg(p.pid, signal.SIGKILL)
            return
    except (OSError, AttributeError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
    except OSError:
        pass


def _rmtree(path):
    """rmtree that clears read-only bits (Windows refuses to delete them) and retries; never raises."""
    def onerr(func, fp, _exc):
        try:
            os.chmod(fp, stat.S_IWRITE)
            func(fp)
        except OSError:
            pass
    try:
        shutil.rmtree(path, onerror=onerr)
    except OSError:
        pass


def _exec(plan, timeout, tmp):
    """Run one plan: {rc, out, err, timeout, t0, ms}. ⚠Own process group, killed whole on timeout (gradlew -> java)."""
    env = dict(os.environ)
    env.update(plan.get("env") or {})
    t0 = time.time()
    res = {"rc": None, "out": "", "err": "", "timeout": False, "t0": t0}
    try:
        p = subprocess.Popen(plan["argv"], cwd=plan["cwd"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env, start_new_session=True)
    except OSError:
        return dict(res, rc=127, nostart=True, ms=0)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        try:
            p.communicate(timeout=10)   # ⚠a surviving daemon may hold the pipe open: never wait on it unbounded
        except (subprocess.SubprocessError, OSError):
            pass
        return dict(res, timeout=True, ms=int((time.time() - t0) * 1000))
    dec = lambda b: b[:AC.OUT_MAX].decode("utf-8", "replace")
    return dict(res, rc=p.returncode, out=dec(out), err=dec(err), ms=int((time.time() - t0) * 1000))


def _load_deps():
    """scripts/deps_audit.py as a module (it is a script, not a package member)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("deps_audit", os.path.join(HERE, "deps_audit.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _deps(repo, dev, offline):
    """deps_audit lines for this Sidereus checkout, None for any other repo (its dependencies are not ours to judge)."""
    if os.path.realpath(repo) != SIDEREUS_ROOT:
        return None
    try:
        return _load_deps().collect((["--dev"] if dev else []) + (["--offline"] if offline else []))
    except Exception as e:   # noqa: BLE001 — a deps failure is a report line, never a lost scan
        return [("WARN", "deps audit", "failed: %s" % type(e).__name__)]


def _report(kdir, j, ok, deps):
    """Write the run's Markdown report; its name, "" when not written."""
    recs = SC.log_read(kdir)
    prev, cur = SR.scan_pair(recs, j["at"]) if ok else (None, None)
    return SR.write(kdir, j["at"], SR.render(j, SC.log_view(kdir), prev, cur, deps))


def run(repo, only=None, offline=False, dev=False):
    """(exit code, summary line). Writes checks-security.json for the repo's HEAD and one Markdown report."""
    head = (_git(repo, ["rev-parse", "HEAD"]) or "").strip()
    if not AV.COMMIT_RE.fullmatch(head):
        return 1, "arch_checks: not a git repo with a commit"
    before = _git(repo, ["status", "--porcelain"])
    plans = [p for p in SC.detect(repo, _which, not offline) if not only or p["id"] in only]
    # ⚠probe only when an online tool would actually run; unreachable re-plans them as skipped, never «0 issues»
    if any(p.get("net") and not p.get("status") for p in plans) and not _probe():
        plans = [p for p in SC.detect(repo, _which, False) if not only or p["id"] in only]
    t_all, tools, items, cache = time.time(), [], [], {}
    tmp = tempfile.mkdtemp(prefix="sidereus-checks-")
    try:
        for p in plans:
            if p.get("status"):
                tools.append({"id": p["id"], "rules": p["rules"], "status": p["status"], "why": p.get("why"), "ms": 0,
                              "files": 0})
                continue
            if p.get("src") == "report":
                p = SC.bind(p, tmp)   # ⚠report lands in tmp only; judge deletes it after reading
            left = AC.TOTAL_S - (time.time() - t_all)
            key = tuple(p["argv"]) + (p["cwd"],)
            if key not in cache:
                if left < 5:
                    tools.append({"id": p["id"], "rules": p["rules"], "status": "skipped", "why": "time budget used",
                                  "ms": 0, "files": 0})
                    continue
                cache[key] = _exec(p, min(AC.TOOL_TIMEOUT_S, left), tmp)
            res = cache[key]
            st, why, its, nf = AC.judge(p, res, repo)
            left = AC.TOTAL_S - (time.time() - t_all)
            if st == "fail" and p.get("fallback") and left >= 5:   # e.g. eslint without the json-with-metadata format
                p2 = dict(p, argv=p["fallback"])
                r2 = _exec(p2, min(AC.TOOL_TIMEOUT_S, left), tmp)
                st, why, its, nf = AC.judge(p2, r2, repo)
                res = dict(r2, ms=res.get("ms", 0) + r2.get("ms", 0))
            tools.append({"id": p["id"], "rules": p["rules"], "status": st, "why": why, "ms": res.get("ms", 0), "files": nf})
            items += its
    finally:
        _rmtree(tmp)
    ign = _git(repo, ["ls-files", "-z", "-o", "-i", "--exclude-standard", "--directory"])
    if ign is not None:   # git failure keeps every item
        items = SC.drop_ignored(items, ign)
    after = _git(repo, ["status", "--porcelain"])
    changed = before is None or after is None or before != after
    j = AC.build(repo, head, bool((before or "").strip()), changed, round(time.time(), 3), tools, items)
    d = AV.store_dir(repo, head)
    os.makedirs(d, exist_ok=True)
    _atomic_write(os.path.join(d, SC.SEC_FILE), (json.dumps(j, ensure_ascii=False) + "\n").encode("utf-8"),
                  prefix=".arch-", mode=0o644)
    _atomic_write(os.path.join(AV.ARCH_DIR, SC.SEC_LAST), json.dumps({"repo": repo, "commit": head}).encode("utf-8"),
                  prefix=".arch-", mode=0o644)
    ok = [t["id"] for t in j["tools"] if t["status"] == "ok"]
    if ok:   # ⚠a run where no tool ran ok must not resolve anything; log failure keeps rc
        SC.log_append(os.path.dirname(d), SC.scan_record(head, j["at"], ok, j["items"]))
    deps = _deps(repo, dev, offline)
    name = _report(os.path.dirname(d), j, ok, deps)   # ⚠after log_append: the delta reads this run's scan record
    extra = " · report %s" % (name or "not written")
    if deps is None:
        extra += " · deps n/a"
    else:
        extra += " · deps %d FAIL/%d WARN" % (sum(1 for x in deps if x[0] == "FAIL"), sum(1 for x in deps if x[0] == "WARN"))
    return 0, summary(j, extra)


def summary(j, extra=""):
    ok = [t for t in j["tools"] if t["status"] == "ok"]
    e = sum(t["n"]["error"] for t in j["tools"])
    w = sum(t["n"]["warning"] for t in j["tools"])
    line = "arch_checks: security · %d tools · %d errors · %d warnings" % (len(ok), e, w)
    for st in ("fail", "timeout", "missing", "skipped"):
        ids = [t["id"] for t in j["tools"] if t["status"] == st]
        if ids:
            line += " · %s: %s" % (st, ",".join(ids))
    return line + extra + (" · source changed by a tool" if j.get("src_changed") else "")


def _last(need_commit):
    """(repo, commit) of the security last pointer; for a run, the last map repo is the fallback. ValueError if none."""
    for name in (SC.SEC_LAST,) + (() if need_commit else ("_last.json",)):
        try:
            j = AV.read_json(os.path.join(AV.ARCH_DIR, name))
        except (OSError, ValueError):
            continue
        if isinstance(j, dict) and isinstance(j.get("repo"), str) and os.path.isdir(j["repo"]):
            return os.path.realpath(j["repo"]), j.get("commit")
    raise ValueError("no last repo")


def verify(repo, commit):
    try:
        j = AV.read_json(os.path.join(AV.store_dir(repo, commit), SC.SEC_FILE))
    except (OSError, ValueError) as e:
        return 1, "arch_checks: schema: %s unreadable (%s)" % (SC.SEC_FILE, type(e).__name__)
    errs = AC.checks_errors(j, repo, commit, SC.SEC_IDS)
    if errs:
        return 1, "arch_checks: schema: %s" % "; ".join(errs[:5])
    # ⚠a run where nothing was examined must not pass as «0 issues»
    ok = [t for t in j["tools"] if t["status"] == "ok"]
    if not ok:
        if not j["tools"]:   # the repo configures nothing: nothing to install, the stage does not apply
            return 1, ("arch_checks: EMPTY: the repo configures no checks — skip the stage with "
                       "[pl-skip:security-checks/<stage title>]")
        miss = ["%s%s" % (t["id"], " (%s)" % t["why"] if t.get("why") else "") for t in j["tools"]]
        return 1, ("arch_checks: EMPTY: no tool ran (missing: %s) — install one or skip the stage with "
                   "[pl-skip:security-checks/<stage title>]" % ", ".join(miss))
    zero = [t["id"] for t in ok if t["files"] == 0]
    if zero:
        return 1, "arch_checks: EMPTY: %s examined 0 files — check its config/scope" % ", ".join(zero)
    return 0, summary(j)


_EV_PY = "/usr/bin/python3"
_EV_REC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence_rec.py")


def _record(rc, repo, commit):
    """One evidence row per gate run (hooks/pl_guard reads it, matched on the target repo root). Steps = one line per
    tool (n = files examined, failed = findings). ⚠Never changes the verify rc: any failure only returns False."""
    try:
        try:
            j = AV.read_json(os.path.join(AV.store_dir(repo, commit), SC.SEC_FILE))
        except (OSError, ValueError):
            j = {}
        tools = j.get("tools") if isinstance(j, dict) and isinstance(j.get("tools"), list) else []
        top = (_git(repo, ["rev-parse", "--show-toplevel"]) or "").strip()
        root = os.path.realpath(top if os.path.isdir(top) else repo)
        ev = os.environ.get("SIDEREUS_EVIDENCE") or os.path.join(
            os.environ.get("MAILBOX_DIR") or os.path.expanduser("~/.mailbox-mcp"), "evidence.jsonl")
        fd, tsv = tempfile.mkstemp(prefix="sidereus-checks-ev-", suffix=".tsv")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for t in tools:
                    if isinstance(t, dict) and isinstance(t.get("id"), str):
                        n = t.get("n") if isinstance(t.get("n"), dict) else {}
                        f.write("%s\t%d\t%d\t%d\t%d\n" % (t["id"], 0 if t.get("status") == "ok" else 1, int(t.get("files") or 0),
                                                          int(n.get("error") or 0) + int(n.get("warning") or 0),
                                                          int(t.get("ms") or 0) // 1000))
            subprocess.run([_EV_PY, _EV_REC, ev, "checks-security", str(rc), root, commit or "",
                            "1" if j.get("dirty") is True else "0", tsv], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        finally:
            os.remove(tsv)
    except Exception:   # noqa: BLE001 — recording is best effort, the gate verdict stands
        return False
    return True


_verify_record = _record   # tests stub `_record` and restore it from here


def _mark_arg(s):
    """(slug, file) of `<slug>@<file>`, None when either part is invalid."""
    k, _a, f = s.partition("@")
    return (k, f) if SC.SLUG_RE.fullmatch(k) and AV.safe_rel(f) == f else None


def review_items(text):
    """(items, skipped) from TSV `sev<TAB>file:line<TAB>slug<TAB>desc` lines; bad lines are counted, not kept."""
    its, bad = [], 0
    for ln in text.splitlines():
        if not ln.strip():
            continue
        p = ln.split("\t", 3)
        f, _c, n = p[1].rpartition(":") if len(p) == 4 else ("", "", "")
        x = SC._log_item({"sev": p[0].strip().lower(), "file": f.strip(), "line": int(n) if re.fullmatch(r"[0-9]{1,9}", n.strip()) else -1,
                          "key": p[2].strip(), "desc": p[3]}, "review") if len(p) == 4 else None
        if x and len(its) < SC.LOG_ITEMS_MAX:
            its.append(x)
        else:
            bad += 1
    return its, bad


def log_cmd(a):
    """--log-review / --log-show / --mark: (rc, output) on the repo's security log."""
    repo = os.path.realpath(a["repo"]) if a["repo"] else _last(False)[0]
    kdir = SC.log_dir(repo)
    if a["log-show"]:
        rows = [x for x in SC.log_view(kdir)["open"] if x["ai"]]
        return 0, "\n".join(["%s\t%s:%d\t%s" % (x["sev"], x["file"], x["line"], x["key"]) for x in rows]
                            + ["arch_checks: %d open AI findings" % len(rows)])
    head = a["commit"] or (_git(repo, ["rev-parse", "HEAD"]) or "").strip()
    if not AV.COMMIT_RE.fullmatch(head):
        return 1, "arch_checks: not a git repo with a commit"
    if a["mark"]:
        (k, f), st = a["mark"]
        rec = SC.mark_record(head, round(time.time(), 3), k, f, st)
        line = "arch_checks: marked %s@%s %s" % (k, f, st)
    else:
        its, bad = review_items(sys.stdin.read(4 * 1024 * 1024))
        rec = SC.review_record(head, round(time.time(), 3), its)
        line = "arch_checks: review · %d findings logged%s" % (len(its), " · %d lines skipped" % bad if bad else "")
    return (0, line) if SC.log_append(kdir, rec) else (1, "arch_checks: security log not writable")


def _args(argv):
    """{verify, last, net, offline, dev, repo, category, only, log-review, log-show, mark, commit} or None on a usage error."""
    a = {"verify": False, "last": False, "net": False, "offline": False, "dev": False, "repo": None, "category": None,
         "only": None,
         "log-review": False, "log-show": False, "mark": None, "commit": None}
    it = iter(argv)
    for x in it:
        if x in ("--verify", "--last", "--net", "--offline", "--dev", "--log-review", "--log-show"):
            a[x[2:]] = True
        elif x in ("--repo", "--category", "--only", "--commit"):
            a[x[2:]] = next(it, None)
            if not a[x[2:]]:
                return None
        elif x == "--mark":
            k, st = _mark_arg(next(it, "")), next(it, None)
            if not k or st not in SC.MARKS:
                return None
            a["mark"] = (k, st)
        else:
            return None
    logm = a["log-review"] + a["log-show"] + bool(a["mark"])
    if logm:   # log commands: one at a time, security only, --commit only with --mark (full hex id)
        if logm > 1 or a["verify"] or a["only"] or a["net"] or a["offline"] or a["dev"] or \
                a["category"] not in (None, "security") or \
                a["last"] == bool(a["repo"]) or (a["commit"] and not (a["mark"] and AV.COMMIT_RE.fullmatch(a["commit"]))):
            return None
        return a
    if a["commit"] or a["category"] not in SC.CATEGORIES + (None,) or a["last"] == bool(a["repo"]) or \
            (a["verify"] and (a["repo"] or a["only"] or a["net"] or a["offline"] or a["dev"])):
        return None
    if a["only"] is not None:
        a["only"] = set(a["only"].split(","))
        if not a["category"] or not a["only"] <= set(SC.SEC_IDS):
            return None
    return a


def main(argv):
    a = _args(argv)
    if a is None:
        print(__doc__.strip().splitlines()[2])
        return 2
    try:
        if a["log-review"] or a["log-show"] or a["mark"]:
            if a["repo"] and not os.path.isdir(a["repo"]):
                print("arch_checks: repo is not a directory")
                return 1
            rc, line = log_cmd(a)
        elif not a["category"]:   # ⚠the lint category was removed: a gate without --category must not pass
            rc, line = 1, "arch_checks: --category security required"
        elif a["verify"]:
            repo, commit = _last(True)
            rc, line = verify(repo, commit)
            _record(rc, repo, commit)
        elif a["last"]:
            rc, line = run(_last(False)[0], a["only"], a["offline"], a["dev"])
        else:
            if not os.path.isdir(a["repo"]):
                print("arch_checks: repo is not a directory")
                return 1
            rc, line = run(os.path.realpath(a["repo"]), a["only"], a["offline"], a["dev"])
    except ValueError as e:
        print("arch_checks: %s" % e)
        return 1
    print(line)
    return rc


if __name__ == "__main__":
    try:   # ⚠repo paths may be non-ASCII; a Windows console/pipe defaults to the ANSI code page
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass
    sys.exit(main(sys.argv[1:]))
