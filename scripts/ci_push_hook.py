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
# git's own failure lines for a push. ⚠`git push ... | tail` exits 0 when the push fails (the pipe takes the
# last command's status), so `is_error` alone sent the session to wait on CI for a commit that never left.
# ⚠Match the `error: ` prefix, not «failed to push»: a localized git translates the text but keeps the prefix
# (a ko locale printed `error: <Korean text>` and the hook still announced «Pushed»).
_FAILED = re.compile(r"^(?:error: |fatal: |\s*! \[(?:remote )?rejected\])", re.M)


def _mask(cmd):
    """`cmd` with every character inside quotes (and each backslash-escaped one) replaced by `_`, same length.
    Patterns are searched here and words taken from `cmd` at the same offsets.
    ⚠Searching the raw text read `git commit -m "fix; cd /x" && git push` as a push run in /x."""
    out, q, esc = [], "", False
    for ch in cmd:
        if esc:
            out.append("_")
            esc = False
        elif q:
            if q == '"' and ch == "\\":
                esc = True
                out.append("_")
            elif ch == q:
                q = ""
                out.append(ch)
            else:
                out.append("_")
        elif ch == "\\":
            esc = True
            out.append(ch)
        else:
            if ch in "'\"":
                q = ch
            out.append(ch)
    return "".join(out)


def pushed_branch(cmd, current):
    """First branch a `git push` command sends, or None when it is not a branch push."""
    b = pushed_branches(cmd, current)
    return b[0] if b else None


def _ref_branch(spec, current):
    """Branch one push refspec sends, or None (delete, tag, empty)."""
    if spec.lstrip("+").startswith(":"):  # `:old` / `+:old` = delete refspec, nothing to build
        return None
    ref = spec.split(":")[-1].lstrip("+")
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    if ref == "HEAD":
        return current
    # ⚠Only a version-shaped name (`v1.2`, `v0.20.0`) is a tag: a bare `^v\d` skipped branches like `v2-redesign`.
    if ref.startswith("refs/tags/") or re.match(r"^v\d+\.\d+", ref):
        return None
    return ref or None


def pushed_branches(cmd, current):
    """Every branch a `git push` command sends, in order (`git push origin a b` sends both); [] when none."""
    cmd = cmd or ""
    mk = _mask(cmd)
    m = _PUSH.search(mk)
    if not m:
        return []
    sep = re.search(r"[;&|]", mk[m.end():])
    rest = cmd[m.end():m.end() + sep.start()] if sep else cmd[m.end():]
    try:
        args = shlex.split(rest)
    except ValueError:
        return []
    if any(a in ("--tags", "--delete", "-d", "--dry-run", "-n") for a in args):
        return []
    pos, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in _VALUED:
            skip = True
        elif not a.startswith("-"):
            pos.append(a)
    if len(pos) < 2:  # `git push` or `git push origin` sends the current branch
        return [current] if current else []
    out = []
    for spec in pos[1:]:
        b = _ref_branch(spec, current)
        if b and b not in out:
            out.append(b)
    return out


def pushed_dir(cmd):
    """Directory the push runs in when the command moves there (`git -C d push`, or the last `cd d` before the
    push), else None. ⚠Without it a push of another repo was resolved in the event cwd (wrong sha, wrong CI)."""
    cmd = cmd or ""
    mk = _mask(cmd)
    m = _PUSH.search(mk)
    if not m:
        return None
    cds = []
    for c in _CD.finditer(mk[:m.start()]):
        # ⚠A `cd` in a subshell closed before the push does not move it: `(cd /x && make) && git push`.
        if c.group(0).lstrip().startswith("(") and ")" in mk[c.end():m.start()]:
            continue
        cds.append(_word(cmd[c.start(1):c.end(1)]))
    cd = cds[-1] if cds else None
    d = _word(cmd[m.start(1):m.end(1)]) if m.group(1) else cd
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


def _code(s):
    """`s` as a markdown code span whose fence is longer than any backtick run inside it (CommonMark).
    ⚠A single-backtick span ended at a backtick in the branch name and cut the command the session runs."""
    fence = "`" * (max((len(r) for r in re.findall(r"`+", s)), default=0) + 1)
    pad = " " if s[:1] == "`" or s[-1:] == "`" else ""
    return fence + pad + s + pad + fence


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
    # A long push moved to the background by Claude Code has not finished yet (backgroundTaskId, no exit code):
    # «Pushed» here would send the session to wait on CI for a commit that may never leave.
    if isinstance(resp, dict) and resp.get("backgroundTaskId"):
        return
    if isinstance(resp, dict) and _FAILED.search("%s\n%s" % (resp.get("stdout") or "", resp.get("stderr") or "")):
        return
    cwd = ev.get("cwd") or "."
    d = pushed_dir(cmd)
    if d:
        # The hook and ci_wait.sh belong to this repo: a push of any other repo gets no hint.
        top = _git(cwd, "rev-parse", "--show-toplevel")
        cwd = os.path.join(cwd, d)
        if not top or _git(cwd, "rev-parse", "--show-toplevel") != top:
            return
    msgs = []
    for branch in pushed_branches(cmd, _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")):
        sha = _git(cwd, "rev-parse", "--verify", "--quiet", branch + "^{commit}")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            continue
        msgs.append("Pushed %s (%s). Run %s once with run_in_background "
                    "and report its verdict line when it finishes; on FAIL list the failing tests and "
                    "fix through quick-fix (cause known) or sidereus-bugfix."
                    # ⚠Quoted: git ref names may hold `$(...)` or backticks, and the session runs this line in a shell.
                    % (_code(branch), sha[:8], _code("bash scripts/ci_wait.sh %s %s" % (sha, shlex.quote(branch)))))
    if not msgs:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": "\n".join(msgs)}}))


if __name__ == "__main__":
    main()
