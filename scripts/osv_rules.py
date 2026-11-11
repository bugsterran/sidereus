#!/usr/bin/python3
"""Usage rules for osv-scanner findings (sidereus/osv_use.py): list unjudged ids, append a rule, validate the files.

usage: osv_rules.py --unjudged --repo <path> | --append '<json rule>' | --check
  --unjudged --repo R   print `id<TAB>package<TAB>cves` of every osv-scanner finding whose use is «none» in R's newest
                        checks-security.json (exit 1 when there is no result or usage was not judged in it).
  --append '<rule>'     validate one rule {name, ids, any, globs, src, at} and append it to <ARCH_DIR>/osv-rules.json
                        (atomic write; a duplicate name, a bad rule or a bad existing file leaves the file unchanged).
  --check               validate the pack (templates/osv-usage/pack.json) and the user file; exit 1 on any error.
⚠Rules hold fixed strings only. The Sidereus server never runs this or writes the rule file.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sidereus import arch_checks as AC  # noqa: E402  (path set just above)
from sidereus import arch_verify as AV  # noqa: E402
from sidereus import osv_use as OU  # noqa: E402
from sidereus import sec_checks as SC  # noqa: E402
from sidereus.bus import _atomic_write  # noqa: E402


def unjudged(repo):
    """(rc, lines) for the newest security result of repo."""
    repo = os.path.realpath(repo)
    rdir = os.path.join(AV.ARCH_DIR, AV.repo_key(repo))
    c = AC._newest(rdir, SC.SEC_FILE)
    if not c:
        return 1, ["osv_rules: no security result for this repo"]
    try:
        j = AV.read_json(os.path.join(rdir, c, SC.SEC_FILE))
    except (OSError, ValueError):
        return 1, ["osv_rules: newest result unreadable"]
    if AC.checks_errors(j, repo, c, SC.SEC_IDS):
        return 1, ["osv_rules: newest result fails the schema"]
    if not OU.clean_counts(j.get("osv_use")):   # ⚠older file or no osv-scanner items: unknown, not «nothing unjudged»
        return 1, ["osv_rules: usage was not judged in the newest result"]
    return 0, ["\t".join((i, p or "-", cv or "-")) for i, p, cv in OU.unjudged(j)]


def append(text):
    try:
        r = json.loads(text)
    except ValueError:
        return 1, ["osv_rules: rule is not JSON"]
    errs = OU.check_rule(r)
    if errs:
        return 1, ["osv_rules: " + e for e in errs]
    fp = OU.user_file()
    if os.path.lexists(fp):
        cur, errs = OU.read_file(fp)
        if errs:   # ⚠never rewrite a file we could not read whole: its bad rules would be silently dropped
            return 1, ["osv_rules: " + e for e in errs]
    else:
        cur = []
    pack, perr = OU.read_file(OU.pack_file(), missing_ok=False)
    if r["name"] in {x["name"] for x in pack + cur}:
        return 1, ["osv_rules: name %s already exists" % r["name"]]
    if len(cur) + 1 > OU.RULES_MAX:
        return 1, ["osv_rules: over %d rules" % OU.RULES_MAX]
    data = (json.dumps({"v": 1, "rules": cur + [r]}, ensure_ascii=True, indent=1) + "\n").encode("ascii")
    if len(data) > OU.RULE_FILE_MAX:
        return 1, ["osv_rules: file would exceed %d bytes" % OU.RULE_FILE_MAX]
    _atomic_write(fp, data, prefix=".osv-rules-", mkdir=True, mode=0o644)
    return 0, ["osv_rules: appended %s (%d user rules)%s" % (r["name"], len(cur) + 1, " · pack: " + perr[0] if perr else "")]


def check():
    pack, e1 = OU.read_file(OU.pack_file(), missing_ok=False)
    user, e2 = OU.read_file(OU.user_file())
    names = {r["name"] for r in pack}
    e3 = ["%s: name %s already in the pack" % (OU.user_file(), r["name"]) for r in user if r["name"] in names]
    errs = e1 + e2 + e3
    return (1 if errs else 0), errs + ["osv_rules: %d pack rules, %d user rules, %d errors" % (len(pack), len(user), len(errs))]


def main(argv):
    if argv[:2] == ["--unjudged", "--repo"] and len(argv) == 3:
        repo = argv[2]
        if not os.path.isdir(repo):
            rc, out = 1, ["osv_rules: repo is not a directory"]
        else:
            rc, out = unjudged(repo)
    elif len(argv) == 2 and argv[0] == "--append":
        rc, out = append(argv[1])
    elif argv == ["--check"]:
        rc, out = check()
    else:
        print(__doc__.strip().splitlines()[2])
        return 2
    for line in out:
        print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
