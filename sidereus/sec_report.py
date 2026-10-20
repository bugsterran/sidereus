"""One Markdown security report per `scripts/arch_checks.py --category security` run: scanner status and counts,
findings, triage state from security-log.jsonl, the delta since the previous scan and the dependency/runtime audit.

Written as arch/<repo key>/security-report-YYYYMMDD-HHMM.md beside security-log.jsonl; the newest KEEP are kept.
⚠Metadata only: rule id · file:line · severity (+ package) and runner-composed status words. Never tool message text,
secret values or the AI-review `desc` (model-written prose about the code). No subprocess here. Stdlib only, Python 3.9.
"""
import os
import re
import stat
import sys
import time

from sidereus.arch_checks_parse import SEVS
from sidereus.arch_verify import safe_rel
from sidereus.bus import _atomic_write
from sidereus.sec_checks import LOG_ITEMS_MAX

REPORT_RE = re.compile(r"security-report-\d{8}-\d{4}\.md")
KEEP = 10
MAX_BYTES = 256 * 1024
ROWS_MAX = 300
_NET = re.compile(r"offline|network", re.I)


def _cell(s, n=200):
    """One table cell / list fragment: no control chars, no pipes or backticks that would break the Markdown."""
    s = "".join(c for c in str(s) if ord(c) >= 32 and ord(c) != 127)[:n]
    return s.replace("\\", "/").replace("|", "\\|").replace("`", "'")


def _loc(x):
    f = safe_rel(x.get("file")) or "?"
    return "%s:%s" % (_cell(f), x.get("line") if isinstance(x.get("line"), int) else "?")


def status_label(t):
    """ok / skipped — offline / missing / failed, plus the runner's own short reason (never tool output)."""
    st, why = t.get("status"), _cell(t.get("why") or "", 60)
    if st == "ok":
        return "ok"
    if st == "skipped":
        return "skipped — offline" if _NET.search(why) else "skipped" + (" — " + why if why else "")
    if st == "missing":
        return "missing" + (" — " + why if why else "")
    return "failed — " + ("timeout" if st == "timeout" else why or "error")


def scan_pair(records, at):
    """(prev_items, cur_items) of the last two scan records when the newest is this run's (at); else (None, None).
    prev keeps only tools that ran ok this time — a skipped tool's findings are not «gone»."""
    scans = [r for r in records if r.get("src") == "scan"]
    if not scans or scans[-1].get("at") != at:
        return None, None
    cur = scans[-1]
    if len(scans) < 2:
        return None, cur["items"]
    ran = set(cur.get("tools") or ())
    return [x for x in scans[-2]["items"] if x["key"].split(":", 1)[0] in ran], cur["items"]


def _ident(x):
    return (x.get("key"), x.get("file"))


def _rule(x):
    """Rule id plus its CVE aliases (dependency findings), e.g. `GHSA-… · CVE-…`."""
    cv = [c for c in x.get("cve") or () if isinstance(c, str)] if isinstance(x.get("cve"), list) else []
    return " · ".join([str(x.get("rule") or "")] + cv)


def render(j, view, prev_items, cur_items, deps):
    """Markdown text. j = checks-security dict; view = sec_checks.log_view(); prev/cur = scan_pair();
    deps = [(level, item, detail)] or None when not applicable."""
    at = j.get("at") or 0
    out = ["# Security report", "",
           "- Repo: `%s`" % _cell(j.get("repo") or "?", 400),
           "- Commit: `%s`%s" % (_cell(str(j.get("commit") or "?")[:12]), " (uncommitted changes)" if j.get("dirty") else ""),
           "- Run: %s (local time)" % time.strftime("%Y-%m-%d %H:%M", time.localtime(at))]
    if j.get("src_changed"):
        out.append("- ⚠A tool changed files in the repo during the run")
    tools = [t for t in j.get("tools") or () if isinstance(t, dict)]
    out += ["", "## Tools", ""]
    if tools:
        out += ["| Tool | Status | Files | Critical | High | Medium | Low | Time |", "|---|---|---|---|---|---|---|---|"]
        for t in tools:
            n = t.get("n") if isinstance(t.get("n"), dict) else {}
            out.append("| %s | %s | %d | %d | %d | %d | %d | %.1f s |" % (
                (_cell(t.get("id")), status_label(t), int(t.get("files") or 0))
                + tuple(int(n.get(k) or 0) for k in SEVS) + (int(t.get("ms") or 0) / 1000.0,)))
    else:
        out.append("The repo configures no scanner this runner knows.")
    ok = [t for t in tools if t.get("status") == "ok"]
    items = [x for x in j.get("items") or () if isinstance(x, dict)]
    total = sum(int((t.get("n") or {}).get(k) or 0) for t in tools for k in SEVS)
    out += ["", "## Findings (%d)" % max(total, len(items)), ""]
    if len(items) < total:
        out.append("Showing the first %d (most severe first); checks-security.json keeps the same cap." % len(items))
    if not ok:
        out.append("⚠No tool ran — this is not a clean result.")
    elif not items:
        out.append("No findings from the tools that ran.")
    if items:
        out += ["| Severity | Tool | Rule | Location | Package |", "|---|---|---|---|---|"]
        for x in items[:ROWS_MAX]:
            out.append("| %s | %s | %s | %s | %s |" % (_cell(x.get("sev")), _cell(x.get("tool")), _cell(_rule(x), 100),
                                                     _loc(x), _cell(x.get("pkg") or "", 100)))
    v = view or {}
    op, rs, fp = v.get("open") or [], v.get("resolved") or [], v.get("fp") or []
    ai = sum(1 for x in op if x.get("ai"))
    out += ["", "## Triage (security-log.jsonl)", "",
            "- open %d (scan %d · AI review %d) · resolved %d · false-positive %d" % (len(op), len(op) - ai, ai, len(rs), len(fp))]
    if op:
        out += ["", "| Severity | Source | Key | Location |", "|---|---|---|---|"]
        for x in op[:ROWS_MAX]:   # ⚠no desc: for AI rows it is model-written prose
            out.append("| %s | %s | %s | %s |" % (_cell(x.get("sev")), "AI review" if x.get("ai") else "scan",
                                                 _cell(x.get("key"), 80), _loc(x)))
    out += ["", "## Since the previous scan", ""]
    if prev_items is None or cur_items is None:
        out.append("n/a — no earlier scan record to compare with" if cur_items is not None else
                   "n/a — no tool ran ok in this run")
    else:
        pi, ci = {_ident(x) for x in prev_items}, {_ident(x) for x in cur_items}
        new = [x for x in cur_items if _ident(x) not in pi]
        gone = [x for x in prev_items if _ident(x) not in ci]
        out.append("- new %d · gone %d" % (len(new), len(gone)))
        if max(len(prev_items), len(cur_items)) >= LOG_ITEMS_MAX:   # ⚠a capped record makes «gone» unreliable
            out.append("- ⚠the log keeps %d findings per scan; past that, new/gone also count findings that moved "
                       "in or out of the kept set" % LOG_ITEMS_MAX)
        for tag, rows in (("new", new), ("gone", gone)):
            for x in rows[:ROWS_MAX]:
                out.append("- %s: %s · %s · %s" % (tag, _cell(x.get("key"), 80), _loc(x), _cell(x.get("sev"))))
    out += ["", "## Dependencies and runtimes", ""]
    if deps is None:
        out.append("not applicable (covers the Sidereus checkout only)")
    else:
        for lv, item, det in deps:
            out.append("- %s %s — %s" % (_cell(lv, 8), _cell(item, 120), _cell(det, 400)))
        if not deps:
            out.append("no lines")
    return "\n".join(out) + "\n"


def name_for(at):
    return "security-report-%s.md" % time.strftime("%Y%m%d-%H%M", time.localtime(at))


def _reports(kdir):
    """Report names that are regular files (symlinks and other names are never touched), newest first."""
    try:
        names = os.listdir(kdir)
    except OSError:
        return []
    out = []
    for n in names:
        if REPORT_RE.fullmatch(n) and not os.path.islink(os.path.join(kdir, n)) and os.path.isfile(os.path.join(kdir, n)):
            out.append(n)
    return sorted(out, reverse=True)


def write(kdir, at, text):
    """Write the report atomically (a same-minute rerun replaces it), then prune to KEEP. Name, or "" on failure.
    ⚠Pruning removes for real: reports are generated data, rebuilt by the next run (the «delete never deletes»
    rule covers tool config only)."""
    name = name_for(at)
    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        data = data[:MAX_BYTES - 64].decode("utf-8", "ignore").encode("utf-8") + b"\n\n(truncated)\n"
    try:
        os.makedirs(kdir, exist_ok=True)
        _atomic_write(os.path.join(kdir, name), data, prefix=".sec-report-", mode=0o644)
    except OSError:
        return ""
    for old in _reports(kdir)[KEEP:]:
        try:
            os.remove(os.path.join(kdir, old))
        except OSError as e:   # a stale extra report is harmless: note it on the runner's stderr, keep the new one
            sys.stderr.write("sec_report: prune %s failed (%s)\n" % (old, type(e).__name__))
    return name


def newest(kdir):
    r = _reports(kdir)
    return r[0] if r else ""


def read_text(kdir, name):
    """Report text, or None for a bad name, a symlink, a non-file, an oversized file or a path outside kdir."""
    if not isinstance(name, str) or not REPORT_RE.fullmatch(name):
        return None
    fp = os.path.join(kdir, name)
    try:
        st = os.lstat(fp)
        if not os.path.isfile(fp) or os.path.islink(fp) or st.st_size > MAX_BYTES:
            return None
        if os.path.dirname(os.path.realpath(fp)) != os.path.realpath(kdir):
            return None
        # ⚠O_NOFOLLOW + fstat: a symlink swapped in after the checks above must not be followed (0 on Windows, no such flag).
        fd = os.open(fp, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as f:
            fs = os.fstat(f.fileno())
            if not stat.S_ISREG(fs.st_mode) or fs.st_size > MAX_BYTES:
                return None
            raw = f.read(MAX_BYTES + 1)
    except OSError:
        return None
    return None if len(raw) > MAX_BYTES else raw.decode("utf-8", "replace")
