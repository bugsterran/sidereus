"""Usage judgement of osv-scanner findings: does the repo use the feature an advisory's precondition names?

A rule maps advisory ids (GHSA / CVE) to fixed strings; the runner `scripts/arch_checks.py` greps its source export
(git archive HEAD, or the `--no-tests` copy) and stores per item `use` = {s: unused | used | none, r, at, hf, hl}.
Rules: the tracked pack `templates/osv-usage/pack.json` + the user file `<ARCH_DIR>/osv-rules.json` (written only by
`scripts/osv_rules.py --append`). ⚠Only the rule name, its date and the first hit's file:line are stored — never the
matched line text or the patterns. ⚠An incomplete grep (any limit, read error or skipped file) is `none`, never
`unused`. No subprocess; Sidereus itself never runs the grep or writes a rule file. Stdlib only, Python 3.9.
"""
import datetime
import fnmatch
import json
import os
import re
import stat
import time

from sidereus import arch_verify as AV
from sidereus import sec_checks as SC
from sidereus.config import ASSET_DIR

PACK_FILE = None   # None = <ASSET_DIR>/templates/osv-usage/pack.json resolved per call (no path constant under the data dir)
USER_NAME = "osv-rules.json"
USER_FILE = None   # None = <AV.ARCH_DIR>/osv-rules.json resolved per call (tests patch either)
TOOL = "osv-scanner"
STATES = ("unused", "used", "none")

PAT_MIN, PAT_MAX, PATS_MAX, GLOBS_MAX, IDS_MAX = 3, 80, 20, 12, 20
RULES_MAX, RULE_FILE_MAX, SRC_MAX = 500, 256 * 1024, 300
FILE_MAX, NUL_PEEK, TOTAL_MAX, FILES_MAX, GREP_S = 1024 * 1024, 8192, 64 * 1024 * 1024, 20000, 30

NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,47}")
ID_RE = re.compile(r"GHSA(?:-[a-z0-9]{4}){3}|CVE-\d{4}-\d{4,7}")
PAT_RE = re.compile(r"[\x20-\x7e]{%d,%d}" % (PAT_MIN, PAT_MAX))
GLOB_RE = re.compile(r"[A-Za-z0-9_.*?\[\]-]{1,40}")   # basename only: no "/"
SRC_RE = re.compile(r"https://[\x21-\x7e]{1,%d}" % (SRC_MAX - 8))
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
KEYS = {"name", "ids", "any", "globs", "src", "at"}
_clock = time.monotonic   # tests patch this, never the real clock


def pack_file():
    return PACK_FILE or os.path.join(ASSET_DIR, "templates", "osv-usage", "pack.json")


def user_file():
    return USER_FILE or os.path.join(AV.ARCH_DIR, USER_NAME)


def _date(s):
    if not (isinstance(s, str) and DATE_RE.fullmatch(s)):
        return False
    try:
        datetime.datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _strs(v, lo, hi, rx):
    return isinstance(v, list) and lo <= len(v) <= hi and len(set(v)) == len(v) \
        and all(isinstance(x, str) and rx.fullmatch(x) for x in v)


def check_rule(r):
    """Shape errors of one rule ([] = valid). Fixed strings only: no regex is ever compiled from a rule."""
    if not isinstance(r, dict):
        return ["rule must be an object"]
    errs = []
    if set(r) != KEYS:
        errs.append("keys must be exactly %s" % ", ".join(sorted(KEYS)))
    if not (isinstance(r.get("name"), str) and NAME_RE.fullmatch(r["name"])):
        errs.append("name")
    if not _strs(r.get("ids"), 1, IDS_MAX, ID_RE):
        errs.append("ids (1-%d GHSA/CVE ids)" % IDS_MAX)
    if not _strs(r.get("any"), 1, PATS_MAX, PAT_RE):
        errs.append("any (1-%d patterns, %d-%d printable ASCII)" % (PATS_MAX, PAT_MIN, PAT_MAX))
    if not _strs(r.get("globs"), 1, GLOBS_MAX, GLOB_RE):
        errs.append("globs (1-%d basename globs)" % GLOBS_MAX)
    if not (isinstance(r.get("src"), str) and SRC_RE.fullmatch(r["src"])):
        errs.append("src (https URL)")
    if not _date(r.get("at")):
        errs.append("at (YYYY-MM-DD)")
    return errs


def read_file(fp, missing_ok=True):
    """(rules, errors) of one rule file. ⚠Symlinked, non-regular or oversized files are refused whole; a bad rule is
    dropped (its ids stay unjudged) and named in errors."""
    try:
        st = os.lstat(fp)
    except FileNotFoundError:
        return [], ([] if missing_ok else ["%s: missing" % fp])
    except OSError as e:
        return [], ["%s: %s" % (fp, e.strerror)]
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return [], ["%s: not a regular file" % fp]
    if st.st_size > RULE_FILE_MAX:
        return [], ["%s: over %d bytes" % (fp, RULE_FILE_MAX)]
    try:
        with open(fp, "rb") as f:
            j = json.loads(f.read(RULE_FILE_MAX + 1).decode("utf-8"))
    except (OSError, ValueError) as e:
        return [], ["%s: unreadable (%s)" % (fp, type(e).__name__)]
    if not (isinstance(j, dict) and set(j) == {"v", "rules"} and j["v"] == 1 and isinstance(j["rules"], list)):
        return [], ["%s: top level must be {v: 1, rules: [...]}" % fp]
    if len(j["rules"]) > RULES_MAX:
        return [], ["%s: over %d rules" % (fp, RULES_MAX)]
    out, errs, seen = [], [], set()
    for i, r in enumerate(j["rules"]):
        e = check_rule(r)
        if not e and r["name"] in seen:
            e = ["duplicate name"]
        if e:
            errs.append("%s: rules[%d]: %s" % (fp, i, "; ".join(e)))
            continue
        seen.add(r["name"])
        out.append(r)
    return out, errs


def load_rules():
    """(rules, errors): pack first, then the user file; a user rule reusing a pack name is dropped."""
    pack, e1 = read_file(pack_file(), missing_ok=False)
    user, e2 = read_file(user_file())
    names = {r["name"] for r in pack}
    errs = e1 + e2 + ["%s: name %s already in the pack" % (user_file(), r["name"]) for r in user if r["name"] in names]
    return pack + [r for r in user if r["name"] not in names], errs


def item_ids(x):
    return {i for i in [x.get("rule")] + list(x.get("cve") or ()) if isinstance(i, str) and ID_RE.fullmatch(i)}


def relevant(items, rules):
    """Rules naming an id of some osv-scanner item (only those are grepped)."""
    ids = set()
    for x in items:
        if x.get("tool") == TOOL:
            ids |= item_ids(x)
    return [r for r in rules if ids & set(r["ids"])]


def _under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _match(name, rules):
    return [r for r in rules if any(fnmatch.fnmatchcase(name, g) for g in r["globs"])]


def grep(root, rules):
    """{rule name: {"s": "used", "hf", "hl"} | {"s": "unused"} | {"s": "none"}} over files under root whose basename
    matches the rule's globs. A hit is kept even if the scan later stops; without a hit, any skipped matching file,
    read error or limit (FILE_MAX, TOTAL_MAX, FILES_MAX, GREP_S) leaves the rule `none`."""
    root = os.path.realpath(root)
    hit, bad, pats = {}, set(), {r["name"]: [p.encode("ascii") for p in r["any"]] for r in rules}
    t0, total, nfiles, stop = _clock(), 0, 0, False
    for d, dirs, files in os.walk(root, onerror=lambda _e: bad.update(pats)):
        dirs.sort()
        for x in list(dirs):
            if os.path.islink(os.path.join(d, x)):   # ⚠not followed: a link out of root leaves every rule unknown
                if not _under(os.path.realpath(os.path.join(d, x)), root):
                    bad.update(pats)
        for fn in sorted(files):
            todo = [r for r in _match(fn, rules) if r["name"] not in hit]
            if not todo:
                continue
            if nfiles >= FILES_MAX or total >= TOTAL_MAX or _clock() - t0 > GREP_S:
                stop = True
                break
            fp = os.path.join(d, fn)
            data = _read(fp, root)
            nfiles += 1
            if data is None:   # symlink, special file, over FILE_MAX, NUL (binary / UTF-16) or read error
                bad.update(r["name"] for r in todo)
                continue
            total += len(data)
            rel = os.path.relpath(fp, root).replace(os.sep, "/")
            for r in todo:
                pos = min((p for p in (data.find(b) for b in pats[r["name"]]) if p >= 0), default=-1)
                if pos < 0:
                    continue
                if AV.safe_rel(rel) != rel:   # unstorable path: the hit cannot be shown, so the rule stays unknown
                    bad.add(r["name"])
                    continue
                hit[r["name"]] = {"s": "used", "hf": rel, "hl": data.count(b"\n", 0, pos) + 1}
        if stop:
            break
    out = {}
    for r in rules:
        n = r["name"]
        out[n] = hit.get(n) or ({"s": "none"} if stop or n in bad else {"s": "unused"})
    return out


def _read(fp, root):
    """File bytes, or None when the file must not or cannot be read in full."""
    try:
        st = os.lstat(fp)
        if not stat.S_ISREG(st.st_mode) or st.st_size > FILE_MAX or not _under(os.path.realpath(fp), root):
            return None
        with open(fp, "rb") as f:
            data = f.read(FILE_MAX + 1)
    except OSError:
        return None
    if len(data) > FILE_MAX or b"\0" in data[:NUL_PEEK]:
        return None
    return data


def judge(x, rules, hits):
    """Item `use` for one osv-scanner item. Several rules on one id: a hit in any -> used; unused only when every
    matching rule completed without a hit; else none."""
    ids = item_ids(x)
    rs = [r for r in rules if ids & set(r["ids"])]
    for r in rs:
        h = hits.get(r["name"]) or {}
        if h.get("s") == "used":
            return {"s": "used", "r": r["name"], "at": r["at"], "hf": h["hf"], "hl": h["hl"]}
    if rs and all((hits.get(r["name"]) or {}).get("s") == "unused" for r in rs):
        return {"s": "unused", "r": rs[0]["name"], "at": rs[0]["at"]}
    return {"s": "none"}


def annotate(items, rules, hits):
    """Items with `use` set on every osv-scanner item (others unchanged). `at` = the rule's judged date."""
    return [dict(x, use=judge(x, rules, hits)) if x.get("tool") == TOOL else x for x in items]


def apply(root, items):
    """Runner entry: load rules, grep only the relevant ones under root, annotate. No osv-scanner item = unchanged."""
    if not any(x.get("tool") == TOOL for x in items):
        return items
    rules, _errs = load_rules()
    rel = relevant(items, rules)
    return annotate(items, rel, grep(root, rel) if rel else {})


def counts(items):
    """{unused, used, none} over osv-scanner items carrying `use`, or None when none carries it."""
    c = {k: 0 for k in STATES}
    seen = False
    for x in items:
        u = x.get("use") if isinstance(x, dict) and x.get("tool") == TOOL else None
        if isinstance(u, dict) and u.get("s") in STATES:
            c[u["s"]] += 1
            seen = True
    return c if seen else None


def clean_use(u):
    """The stored `use` dict re-validated (strict key sets per state), or None."""
    if not isinstance(u, dict) or u.get("s") not in STATES:
        return None
    s = u["s"]
    if s == "none":
        return {"s": "none"} if set(u) == {"s"} else None
    keys = {"s", "r", "at"} | ({"hf", "hl"} if s == "used" else set())
    if set(u) != keys or not (isinstance(u["r"], str) and NAME_RE.fullmatch(u["r"])) or not _date(u["at"]):
        return None
    if s == "used":
        hl = u["hl"]
        if AV.safe_rel(u["hf"]) != u["hf"] or not isinstance(hl, int) or isinstance(hl, bool) or hl < 1:
            return None
    return dict(u)


def clean_counts(c):
    """Top-level `osv_use` {unused, used, none} re-validated, or None."""
    if not (isinstance(c, dict) and set(c) == set(STATES)):
        return None
    if not all(isinstance(c[k], int) and not isinstance(c[k], bool) and c[k] >= 0 for k in STATES):
        return None
    return {k: c[k] for k in STATES}


def unjudged(j):
    """Sorted (id, package, cves) of osv-scanner items whose use is none in a checks file dict."""
    out = set()
    for x in j.get("items") or () if isinstance(j, dict) else ():
        if isinstance(x, dict) and x.get("tool") == TOOL and (clean_use(x.get("use")) or {}).get("s") == "none":
            pk = x.get("pkg") if isinstance(x.get("pkg"), str) and SC.PKG_RE.fullmatch(x["pkg"]) else ""
            cv = ",".join(SC.cves(x.get("cve") or ()))
            out.add((str(x.get("rule") or ""), pk, cv))
    return sorted(out)
