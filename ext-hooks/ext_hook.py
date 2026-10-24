#!/usr/bin/env python3
"""External AI CLI hook -> Sidereus (/api/hook) adapter. Supported platforms: see README (20).

  python3 ext_hook.py --platform gemini   < hook.json
  python3 ext_hook.py --platform codex    < hook.json
  python3 ext_hook.py --platform cursor   < hook.json

# Must hold
#  - stdout always stays empty. Both CLIs read hook stdout as «control directives (JSON)».
#  - exit 0 no matter what. A non-zero hook makes the CLI block the tool/turn.
#  - stdlib only. Passes silently within 2s even when Sidereus is down.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request


def sidereus_port():
    """Viewer port: env SIDEREUS_PORT > config `port` > 8799. Mirrors mailbox_config.port() but reads the JSON directly
    (⚠standalone and fast: no repo import). Config: $MAILBOX_CONFIG, else ($MAILBOX_DIR or ~/.mailbox-mcp)/config.local.json."""
    raw = (os.environ.get("SIDEREUS_PORT") or "").strip()
    if raw.isdigit() and 1 <= int(raw) <= 65535:
        return int(raw)
    path = os.environ.get("MAILBOX_CONFIG") or os.path.join(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp",
                                                          "config.local.json")
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            v = json.load(f).get("port")
        if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 65535:
            return v
    except Exception:
        pass
    return 8799


DEFAULT_URL = "http://127.0.0.1:%d/api/hook" % sidereus_port()
TIMEOUT = 2.0
LOG_PATH = os.path.join(os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp"),
                        "ext-hooks", ".ext-hook.log")   # data dir; ⚠ stays standalone (copied into other CLIs)
LOG_MAX = 200 * 1024

# The 7 events of the Sidereus wire protocol. Events not listed here are never sent.
EVENTS = {
    "gemini": {
        "SessionStart": "SessionStart",
        "SessionEnd": "SessionEnd",
        "BeforeTool": "PreToolUse",
        "AfterTool": "PostToolUse",
        "Notification": "Notification",
        # ★Gemini has no UserPromptSubmit/Stop - the agent hooks fill that role.
        "BeforeAgent": "UserPromptSubmit",
        "AfterAgent": "Stop",
    },
    "codex": {
        "SessionStart": "SessionStart",
        "SessionEnd": "SessionEnd",
        "PreToolUse": "PreToolUse",
        "PostToolUse": "PostToolUse",
        "UserPromptSubmit": "UserPromptSubmit",
        "Stop": "Stop",
        # ★Codex 0.156.1 has no Notification: a permission prompt is the «waiting for a person» signal.
        #   ⚠stdout stays empty here, so Codex sees no decision and asks the user as usual.
        "PermissionRequest": "Notification",
        "Interrupt": "Stop",
        # Codex itself never sends this; kept so `--event Notification` reaches the viewer's `ask` state.
        "Notification": "Notification",
    },
}
# ⚠The codex map mirrors sidereus/plat_codex.EVENTS (tests/test_codex.py checks they match).
#   The other platforms below copy it, so their standard names are unaffected by the two Codex-only keys.
# ★Cursor CLI 2026.10.22 (macOS, 2026-10-24): camelCase names; afterAgentThought/afterAgentResponse carry text, so unmapped.
#   ⚠`cursor-agent -p` sends no beforeSubmitPrompt/stop - a headless row stays in its last state until sessionEnd.
#   ⚠Built on the codex map: older configs pass `--event <standard name>`, which goes through this same lookup.
EVENTS["cursor"] = dict(EVENTS["codex"], **{
    "sessionStart": "SessionStart",
    "sessionEnd": "SessionEnd",
    "beforeSubmitPrompt": "UserPromptSubmit",
    "stop": "Stop",
    "preToolUse": "PreToolUse",
    "postToolUse": "PostToolUse",
    "postToolUseFailure": "PostToolUse",
})

# ★Accept every platform Sidereus knows (2026-09-22: commonly used AI platforms must be supported).
#   ⚠CLIs with different event names must pass the standard name via `--event` - the default mapping is the standard 7, same as Codex.
for _p in ("copilot", "cursor", "cline", "windsurf", "warp", "trae", "zed", "grok",
           "deepseek", "qwen", "kimi", "mistral", "ollama", "perplexity",
           "huggingface", "meta", "openrouter"):   # ⚠exclude Claude - Sidereus already sees it via transcripts
    EVENTS.setdefault(_p, dict(EVENTS["codex"]))


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX:
            with open(LOG_PATH, "rb") as f:
                f.seek(-LOG_MAX // 2, os.SEEK_END)
                tail = f.read()
            with open(LOG_PATH, "wb") as f:
                f.write(tail[tail.find(b"\n") + 1:])
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), msg))
    except Exception:
        pass


def arg(name):
    a = sys.argv
    for i, v in enumerate(a):
        if v == name and i + 1 < len(a):
            return a[i + 1]
        if v.startswith(name + "="):
            return v.split("=", 1)[1]
    return None


def build(platform, data, event_override=None):
    raw = event_override or data.get("hook_event_name") or data.get("hookEventName") or data.get("event")
    event = EVENTS.get(platform, {}).get(raw)
    if not event:
        return None, raw
    out = {"platform": platform, "event": event, "ts": time.time()}
    # ⚠Never guess missing fields - omit the key entirely.
    #   Gemini-based payloads lack model·turn_id; Codex has both.
    for key in ("session_id", "cwd", "transcript_path", "model", "tool_name", "turn_id"):
        val = data.get(key)
        if isinstance(val, str) and val:
            out[key] = val
    # Cursor: no base cwd (tool events send ""), session id lives in conversation_id too.
    if "session_id" not in out and isinstance(data.get("conversation_id"), str) and data["conversation_id"]:
        out["session_id"] = data["conversation_id"]
    if "cwd" not in out:
        roots = data.get("workspace_roots")
        for r in roots if isinstance(roots, list) else ():
            if isinstance(r, str) and os.path.isabs(r):
                out["cwd"] = r
                break
    par = parent_sid()
    if par:
        out["parent"] = par
    pid, start = cli_pid()
    if pid:
        out["pid"] = pid
        out["host"] = socket.gethostname()
        if start:
            out["pstart"] = start
    return out, raw


# Wrappers between the CLI and this script (the hook command usually runs under `sh -c`).
SKIP_COMM = ("sh", "bash", "zsh", "dash", "fish", "env", "timeout", "gtimeout", "nice", "nohup")


def _ps(pid):
    """(ppid, lstart, comm basename) of one process, or None. ⚠LC_ALL=C: lstart is localized otherwise
    and the server compares it byte for byte."""
    try:
        out = subprocess.run(["/bin/ps", "-o", "ppid=,lstart=,comm=", "-p", str(pid)],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=1,
                             env={"LC_ALL": "C", "PATH": "/bin:/usr/bin"}).stdout.decode("utf-8", "replace")
    except Exception:
        return None
    f = out.split()
    if len(f) < 7 or not f[0].isdigit():
        return None
    return int(f[0]), " ".join(f[1:6]), os.path.basename(" ".join(f[6:]))


def cli_pid():
    """pid + start time of the CLI that ran this hook: walk up past shell/python wrappers.
    ★Not os.getppid() alone — that is usually the short-lived `sh -c`, which would read as dead at once."""
    if os.environ.get("SIDEREUS_HOOK_NO_PID"):      # tests (tests/_load.py): never run ps
        return 0, ""
    pid = os.getppid()
    for _ in range(6):
        if pid <= 1:
            return 0, ""
        p = _ps(pid)
        if p is None:
            return 0, ""
        name = p[2].lower()
        if name not in SKIP_COMM and not name.startswith("python"):
            return pid, p[1]
        pid = p[0]
    return 0, ""


def parent_sid(env=None):
    """Claude session that launched this CLI: `SIDEREUS_PARENT_SID` (ask-gemini), else Claude Code's own env.
    ⚠Hooks inherit the CLI's env, so a `gemini -p` run from a Claude Bash tool call carries it."""
    env = os.environ if env is None else env
    v = str(env.get("SIDEREUS_PARENT_SID") or env.get("CLAUDE_CODE_SESSION_ID") or "").strip()
    ok = 0 < len(v) <= 64 and all(c.isalnum() or c in "-_" for c in v)
    return v if ok else ""


def main():
    platform = (arg("--platform") or "").strip().lower()
    if platform not in EVENTS:
        log("bad --platform %r" % platform)
        return
    url = arg("--url") or os.environ.get("SIDEREUS_HOOK_URL") or DEFAULT_URL
    dry = "--dry-run" in sys.argv

    try:
        stdin = sys.stdin.read()
    except Exception as e:
        log("stdin read failed: %s" % e)
        return
    try:
        data = json.loads(stdin or "{}")
        if not isinstance(data, dict):
            raise ValueError("payload is not an object")
    except Exception as e:
        log("bad json (%s): %.200s" % (e, stdin))
        return

    payload, raw = build(platform, data, arg("--event"))
    if payload is None:
        return  # unknown event - silently 0

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if dry:
        sys.stderr.write(body.decode("utf-8") + "\n")  # ⚠stderr, not stdout
        return
    # --url/env may name another host (a CLI in a VM), so only the scheme is restricted.
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        log("bad url scheme: %.200s" % url)
        return
    try:
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=TIMEOUT).read()  # nosec B310 -- scheme checked above
    except Exception as e:
        log("post %s %s/%s failed: %s" % (url, platform, raw, e))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # swallow anything that leaks this far - never blocking the CLI comes first
        log("unhandled: %s" % e)
    sys.exit(0)
