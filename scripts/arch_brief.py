#!/usr/bin/python3
"""Overview (arch-brief) pipeline steps (sidereus/arch_brief.py).

usage: arch_brief.py --pre --repo <path> | --ready | --last | --check --repo <path> --commit <sha> [--by <session id>]
--pre: resolve HEAD, require a finished arch-map result, rewrite _brief_last.json; exit 1 on a miss.
--ready: exit 0 only when the last --pre found the arch-map result.
--last: check the brief.json of the last --pre and write brief.html; exit 1 on any FAIL, 2 on usage.
--check: same gate for an explicit commit (a session asked to draw); reads and writes no _brief_last.json.
  ⚠Another run's --pre rewrites the shared pointer at any time: --last could gate the wrong repo or commit.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sidereus import arch_brief as AB  # noqa: E402  (path set just above)
from sidereus.arch_verify import COMMIT_RE  # noqa: E402
from sidereus.bus import RELAY_SID  # noqa: E402  (the server's session id rule)


def _check(argv):
    """(rc, line) of --check --repo <p> --commit <sha> [--by <sid>]; usage errors are rc 2."""
    if len(argv) not in (5, 7) or argv[1] != "--repo" or argv[3] != "--commit" or (len(argv) == 7 and argv[5] != "--by"):
        return 2, __doc__.strip().splitlines()[2]
    repo, commit, by = argv[2], argv[4], argv[6] if len(argv) == 7 else ""
    if not COMMIT_RE.fullmatch(commit):
        return 2, "arch_brief: --commit must be a full commit id"
    if len(argv) == 7 and not RELAY_SID.fullmatch(by):
        return 2, "arch_brief: --by must be a session id"
    if not os.path.isdir(repo):
        return 1, "arch_brief: repo is not a directory"
    return AB.run(repo, commit, by)


def main(argv):
    if len(argv) == 3 and argv[0] == "--pre" and argv[1] == "--repo":
        rc, line = AB.pre(argv[2])
    elif argv[:1] == ["--check"]:
        rc, line = _check(argv)
    elif argv in (["--ready"], ["--last"]):
        try:
            repo, commit, ok = AB.last()
        except ValueError as e:
            print("arch_brief: %s" % e)
            return 1
        if not ok:
            print("arch_brief: no arch-map result for %s at %s; run arch-map first" % (repo, commit[:7]))
            return 1
        rc, line = (0, "arch_brief: ready %s" % commit[:7]) if argv == ["--ready"] else AB.run(repo, commit)
    else:
        print(__doc__.strip().splitlines()[2])
        return 2
    print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
