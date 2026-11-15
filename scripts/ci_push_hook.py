"""PostToolUse hook (Bash): after a branch push, tell the session to wait for that commit's CI.

Registered in the project's own `.claude/settings.local.json`, so it fires only in this repo.
It never waits itself (a hook has a timeout and blocks the turn); it only injects one line asking
the session to run `scripts/ci_wait.sh` in the background, which notifies when CI concludes.
Tag-only pushes are skipped: the release pipeline's «CI check» stage covers them.
"""
import json
import re
import shlex
import subprocess
import sys

# Only at a command position: `git push` quoted inside a commit message must not match.
_PUSH = re.compile(r"(?:^|[;&|(\n])\s*git\s+(?:-C\s+\S+\s+)?push\b")


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
    pos = [a for a in args if not a.startswith("-")]
    if len(pos) < 2:  # `git push` or `git push origin` sends the current branch
        return current
    ref = pos[1].split(":")[-1].lstrip("+")
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    if ref == "HEAD":
        return current
    if ref.startswith("refs/tags/") or re.match(r"^v\d", ref):
        return None
    return ref or None


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
    branch = pushed_branch(cmd, _git(cwd, "rev-parse", "--abbrev-ref", "HEAD"))
    if not branch:
        return
    sha = _git(cwd, "rev-parse", "--verify", "--quiet", branch + "^{commit}")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return
    msg = ("Pushed %s (%s). Run `bash scripts/ci_wait.sh %s %s` once with run_in_background "
           "and report its verdict line when it finishes; on FAIL list the failing tests and "
           "fix through quick-fix (cause known) or sidereus-bugfix." % (branch, sha[:8], sha, branch))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": msg}}))


if __name__ == "__main__":
    main()
