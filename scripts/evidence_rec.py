#!/usr/bin/python3
"""Append one gate-run record to the evidence file (called from check.sh's EXIT trap).

usage: evidence_rec.py <file> <mode: fast|full|checks-security> <rc> <repo> <head> <dirty> <steps.tsv> [<screen.json>]

steps.tsv lines: name<TAB>rc<TAB>n<TAB>failed<TAB>secs. Metadata only: counts and step names,
never log lines, file names or test names. Never fails the gate: any problem -> exit 0, nothing written.
"""
import json
import os
import re
import sys
import time

try:
    import fcntl
except ImportError:   # Windows: no flock, so no row (same as hooks/ev_hook.py; never a partial write)
    fcntl = None

EV_CAP = 400    # rotate once the file grows past this many lines
EV_KEEP = 200   # lines kept after rotation
MAX_STEPS = 32
# Gate modes a row may carry; ⚠hooks/pl_guard.py GATE_MODES maps gates to these (add new modes here first).
MODES = ('fast', 'full', 'checks-security')
MAX_SCREEN = 24
_NAME = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
_HEAD = re.compile(r'^[0-9a-f]{4,40}$')
_LANG = re.compile(r'^[a-z]{2,5}$')


def _int(s):
    try:
        v = int(str(s).strip())
    except (TypeError, ValueError):
        return None
    return v if -1 <= v < 10 ** 9 else None


def read_steps(path):
    """Valid lines only; malformed lines are dropped, a missing file gives []."""
    out = []
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for ln in lines:
        p = ln.split('\t')
        if len(p) != 5 or not _NAME.match(p[0]):
            continue
        nums = [_int(x) for x in p[1:]]
        if any(x is None for x in nums):
            continue
        out.append({'name': p[0], 'rc': nums[0], 'n': nums[1], 'failed': nums[2], 'secs': nums[3]})
        if len(out) >= MAX_STEPS:
            break
    return out


def read_screen(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    out = []
    for x in data[:MAX_SCREEN]:
        if not isinstance(x, dict):
            continue
        w, d, lang = _int(x.get('w')), _int(x.get('diff')), x.get('lang')
        if w is None or d is None or not isinstance(lang, str) or not _LANG.match(lang):
            continue
        out.append({'w': w, 'lang': lang, 'ok': x.get('ok') is True, 'diff': d})
    return out


def build(argv, ts):
    """Record dict or None when the arguments are unusable."""
    if len(argv) not in (7, 8):
        return None
    _f, mode, rc, repo, head, dirty, steps = argv[:7]
    rc = _int(rc)
    if mode not in MODES or rc is None:
        return None
    rec = {'v': 1, 'kind': 'check', 'ts': int(ts), 'mode': mode,
           'repo': os.path.realpath(repo) if repo else '',
           'head': head if _HEAD.match(head or '') else '',
           'dirty': dirty == '1', 'rc': rc, 'steps': read_steps(steps)}
    if len(argv) == 8:
        sc = read_screen(argv[7])
        if sc is not None:
            rec['screen'] = sc
    return rec


def append(path, line):
    """Append under flock; past EV_CAP lines, rewrite the last EV_KEEP via tmp + rename."""
    if fcntl is None:
        return False
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    for _ in range(5):
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            # ⚠ a rotation by another writer replaced the inode while we waited: retry on the new file
            try:
                same = os.fstat(fd).st_ino == os.stat(path).st_ino
            except OSError:
                same = False
            if not same:
                continue
            os.write(fd, line.encode('utf-8'))
            with open(path, encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines(True)
            if len(lines) > EV_CAP:
                tmp = path + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-EV_KEEP:])
                os.replace(tmp, path)
            return True
        finally:
            os.close(fd)
    return False


def main(argv, ts=None):
    try:
        rec = build(argv, time.time() if ts is None else ts)
        if rec is None:
            return 0
        append(argv[0], json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')
    except Exception:  # noqa: BLE001 — the recorder must never fail the gate
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
