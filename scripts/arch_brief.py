#!/usr/bin/python3
"""Overview (arch-brief) pipeline steps (sidereus/arch_brief.py).

usage: arch_brief.py --pre --repo <path> | --ready | --last
--pre: resolve HEAD, require a finished arch-map result, rewrite _brief_last.json; exit 1 on a miss.
--ready: exit 0 only when the last --pre found the arch-map result.
--last: check the brief.json of the last --pre and write brief.html; exit 1 on any FAIL, 2 on usage.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sidereus import arch_brief as AB  # noqa: E402  (path set just above)


def main(argv):
    if len(argv) == 3 and argv[0] == "--pre" and argv[1] == "--repo":
        rc, line = AB.pre(argv[2])
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
