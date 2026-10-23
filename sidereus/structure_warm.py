"""Child entry for the idle structure warm-up: `python -m sidereus.structure_warm <root> <tests>`.

Computes one (root, tests) cell and writes it to the disk cache only; the viewer reads it from disk later.
⚠Inputs are re-checked here (absolute existing dir, not a denied root) — never call `_struct_src_root`/`_allowed_cwds`,
which would run a full sessions() scan in the child.
"""
import os
import sys

from sidereus import structure as _S


def main(argv):
    """-> 0 ok · 1 compute failed · 2 bad arguments (nothing computed)."""
    if len(argv) != 2 or argv[1] not in ("0", "1", "2"):
        return 2
    raw = argv[0]
    if not raw or not os.path.isabs(raw):
        return 2
    try:
        root = os.path.realpath(raw)
    except (OSError, ValueError, TypeError):
        return 2
    if not os.path.isdir(root) or root in _S._struct_denied_roots():
        return 2
    out = _S._structure_at(root, int(argv[1]), mem=False)
    return 0 if isinstance(out, dict) and out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
