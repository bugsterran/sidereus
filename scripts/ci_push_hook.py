"""PostToolUse hook (Bash): after a branch push, tell the session to wait for that commit's CI.

Registered in the project's own `.claude/settings.local.json`, so it fires only in this repo.
It never waits itself (a hook has a timeout and blocks the turn); it only injects one line asking
the session to run `scripts/ci_wait.sh` in the background, which notifies when CI concludes.
Tag-only pushes are skipped: the release pipeline's «CI check» stage covers them.
"""
import json
import os
import re
import shlex
import subprocess
import sys

_WORD = r"""('[^']*'|"[^"]*"|\S+)"""   # one shell word: quoted (spaces kept) or bare
# Only at a command position: `git push` quoted inside a commit message must not match.
_PUSH = re.compile(r"(?:^|[;&|(\n])\s*git\s+(?:-C\s+" + _WORD + r"\s+)?push\b")
_CD = re.compile(r"(?:^|[;&|(\n])\s*cd\s+" + _WORD)
# Options whose value is the next word; ⚠without skipping it `-o ci.skip origin dev` read «origin» as the branch.
_VALUED = ("-o", "--push-option", "--repo", "--receive-pack", "--exec")


def pushed_branch(cmd, current):
    """Branch a `git push` command sends, or None when it is not a branch push."""
    m = _PUSH.search(cmd or "")
    if not m:
        return None
    rest = re.split(r"[;&|]", cmd[m.end():], maxsplit=1)[0]
    try:
        args = shlex.split(rest)
    except ValueError:
        return None
    if any(a in ("--tags", "--delete", "-d", "--dry-run", "-n") for a in args):
        return None
    pos, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in _VALUED:
            skip = True
        elif not a.startswith("-"):
            pos.append(a)
    if len(pos) < 2:  # `git push` or `git push origin` sends the current branch
        return current
    if pos[1].lstrip("+").startswith(":"):  # `:old` / `+:old` = delete refspec, nothing to build
        return None
    ref = pos[1].split(":")[-1].lstrip("+")
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    if ref == "HEAD":
        return current
    if ref.startswith("refs/tags/") or re.match(r"^v\d", ref):
        return None
    return ref or None


def pushed_dir(cmd):
    """Directory the push runs in when the command moves there (`git -C d push`, or the last `cd d` before the
    push), else None. ⚠Without it a push of another repo was resolved in the event cwd (wrong sha, wrong CI)."""
    m = _PUSH.search(cmd or "")
    if not m:
        return None
    cds = []
    for c in _CD.finditer(cmd[:m.start()]):
        # ⚠A `cd` in a subshell closed before the push does not move it: `(cd /x && make) && git push`.
        if c.group(0).lstrip().startswith("(") and ")" in cmd[c.end():m.start()]:
            continue
        cds.append(_word(c.group(1)))
    cd = cds[-1] if cds else None
    d = _word(m.group(1)) if m.group(1) else cd
    if d and cd and m.group(1) and not os.path.isabs(d):
        d = os.path.join(cd, d)  # a relative `-C` is taken from the directory the earlier `cd` moved to
    return d or None


def _word(w):
    """One captured shell word as a path: unquoted, `~`/`$VAR` expanded; a bare `cd` (next token is an
    operator, e.g. `cd && git push`) means the home directory, like the shell."""
    if w[:1] in ("&", ";", "|", ")"):
        return os.path.expanduser("~")
    try:
        w = (shlex.split(w) or [""])[0]
    except ValueError:
        return None
    return os.path.expanduser(os.path.expandvars(w)) or None


def _git(cwd, *argv):
    try:
        r = subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main():
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return
    cmd = (ev.get("tool_input") or {}).get("command") or ""
    resp = ev.get("tool_response") or {}
    if isinstance(resp, dict) and (resp.get("interrupted") or resp.get("is_error")):
        return
    cwd = ev.get("cwd") or "."
    d = pushed_dir(cmd)
    if d:
        # The hook and ci_wait.sh belong to this repo: a push of any other repo gets no hint.
        top = _git(cwd, "rev-parse", "--show-toplevel")
        cwd = os.path.join(cwd, d)
        if not top or _git(cwd, "rev-parse", "--show-toplevel") != top:
            return
    branch = pushed_branch(cmd, _git(cwd, "rev-parse", "--abbrev-ref", "HEAD"))
    if not branch:
        return
    sha = _git(cwd, "rev-parse", "--verify", "--quiet", branch + "^{commit}")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return
    msg = ("Pushed %s (%s). Run `bash scripts/ci_wait.sh %s %s` once with run_in_background "
           "and report its verdict line when it finishes; on FAIL list the failing tests and "
           "fix through quick-fix (cause known) or sidereus-bugfix."
           # ⚠Quoted: git ref names may hold `$(...)` or backticks, and the session runs this line in a shell.
           % (branch, sha[:8], sha, shlex.quote(branch)))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": msg}}))


if __name__ == "__main__":
    main()
