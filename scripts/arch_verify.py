#!/usr/bin/python3
"""Gate of the arch-map pipeline: verify a stored map.json against its commit (sidereus/arch_verify.py).

usage: arch_verify.py --last | --repo <path> --commit <sha>
Prints one line with the rate; exit 0 if rate >= ARCH_GATE_MIN, 1 on schema error or a low rate, 2 on usage.
Flows (flows.json) add an advisory suffix to that line; they never change the exit code.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sidereus import arch_verify as AV  # noqa: E402  (path set just above)
from sidereus import arch_flow as AF  # noqa: E402


def main(argv):
    if argv == ["--last"]:
        try:
            repo, commit = AV.last()
        except ValueError as e:
            print("arch_verify: %s" % e)
            return 1
    elif len(argv) == 4 and argv[0] == "--repo" and argv[2] == "--commit":
        repo, commit = argv[1], argv[3]
        if not os.path.isdir(repo):
            print("arch_verify: repo is not a directory")
            return 1
    else:
        print(__doc__.strip().splitlines()[2])
        return 2
    rc, line = AV.run(os.path.realpath(repo), commit)
    if not line.startswith("arch_verify: schema:"):
        # ⚠Flows are advisory: any failure here only changes the suffix, never rc.
        try:
            line += AF.run(os.path.realpath(repo), commit)
        except Exception as e:  # noqa: BLE001
            line += " · flows error (%s)" % type(e).__name__
    print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
