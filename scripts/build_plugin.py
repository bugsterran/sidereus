#!/usr/bin/python3
"""Build plugin/ (Claude Code plugin) + .claude-plugin/marketplace.json from an explicit allow-list.

Usage: build_plugin.py [--check]   (--check: exit 1 if plugin/ or the marketplace file is out of date)
⚠The plugin source is plugin/, never the repo root: the repo root holds live data (bus.jsonl, identity.json ...)
that would be copied into every user's plugin cache.
Copies are byte-for-byte; manifests are generated here. Deterministic (no clock), stdlib only, Python 3.9.
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "plugin")
MARKET = os.path.join(ROOT, ".claude-plugin", "marketplace.json")

NAME = "sidereus"   # plugin + marketplace name (public)
MCP_NAME = "sidereus"   # tools are mcp__sidereus__* in configs and hooks
VERSION = "0.1.0"
AUTHOR = "bugsterran"
DESC = ("Sidereus for Claude Code: mailbox invites and stop-hook relay, pipeline brief, shared-file edit notice, "
        "pipeline stage marks and hand-offs, and the read-only Sidereus MCP server. Needs the local Sidereus viewer.")

# Hand-written second plugin (plugins/orbit/): listed in the marketplace only, never copied by this build.
FA_ENTRY = {"name": "orbit", "source": "./plugins/orbit",
            "description": "Pick a Claude Code config folder (CLAUDE_CONFIG_DIR) per project folder; never copies "
                           "or swaps credentials."}

# Repo file -> same relative path inside plugin/. mailbox_config.py sits at the plugin root because
# hooks/invite_notice.py and mcp/sidereus_mcp.py import it from their parent folder.
COPY = ("LICENSE", "mailbox_config.py", "mcp/sidereus_mcp.py",
        "hooks/invite_notice.py", "hooks/mailbox_stop.py", "hooks/mailbox_wake.py", "hooks/pipelines_brief.py",
        "hooks/file_peers_notice.py", "hooks/pl_mark.py", "hooks/pl_flow.py", "hooks/pl_guard.py",
        "hooks/perm_mark.py", "hooks/ev_hook.py", "hooks/pyrun.sh")

# Source of the hook set: `sidereus_cli.py setup-claude` prints plugin/hooks/hooks.json with the clone's real paths.
# (event, matcher or None, script, timeout s)
HOOKS = (("SessionStart", None, "invite_notice.py", 10),
         ("SessionStart", None, "pipelines_brief.py", 5),
         ("UserPromptSubmit", None, "invite_notice.py", 10),
         ("UserPromptSubmit", None, "pipelines_brief.py", 5),
         ("Stop", None, "mailbox_stop.py", 5),
         # asyncRewake: runs in the background after each turn; exit 2 wakes the idle session (no Monitor needed).
         ("Stop", None, "mailbox_wake.py", 6 * 3600 + 120, {"asyncRewake": True}),
         ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "file_peers_notice.py", 2),
         ("PreToolUse", "Task|Agent|SendMessage", "pl_mark.py", 5),
         ("PreToolUse", "Bash", "pl_mark.py", 5),
         ("PreToolUse", "Task|Agent|SendMessage", "pl_flow.py", 5),
         ("PreToolUse", "Bash", "pl_flow.py", 5),
         ("PostToolUse", "Task|Agent|SendMessage", "pl_flow.py", 5),
         ("Notification", "permission_prompt|elicitation_dialog", "perm_mark.py", 5),
         # Harness evidence: test/build/check/lint Bash runs -> evidence.jsonl rows (metadata only).
         ("PreToolUse", "Bash", "ev_hook.py", 3),
         ("PostToolUse", "Bash", "ev_hook.py", 3),
         ("PostToolUseFailure", "Bash", "ev_hook.py", 3))


def _json(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _license_id():
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as f:
        head = f.readline().strip()
    return "MIT" if head == "MIT License" else "SEE LICENSE"


def hooks_json():
    ev = {}
    for event, matcher, script, timeout, *extra in HOOKS:
        # ⚠${CLAUDE_PLUGIN_ROOT} stays quoted: the plugin cache path may contain spaces.
        # pyrun.sh picks a real Python on Windows (python3 there may be the Store stub); elsewhere it execs python3.
        cmd = {"type": "command", "command": 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/pyrun.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/%s"'
               % script, "timeout": timeout}
        cmd.update(extra[0] if extra else {})
        groups = ev.setdefault(event, [])
        grp = next((g for g in groups if g.get("matcher") == matcher), None)
        if grp is None:
            grp = {"matcher": matcher} if matcher else {}
            grp["hooks"] = []
            groups.append(grp)
        grp["hooks"].append(cmd)
    return {"hooks": ev}


def expected():
    """{path relative to ROOT: bytes} for every file the build owns."""
    out = {}
    for rel in COPY:
        with open(os.path.join(ROOT, rel), "rb") as f:
            out["plugin/" + rel] = f.read()
    out["plugin/.claude-plugin/plugin.json"] = _json({
        "name": NAME, "version": VERSION, "description": DESC,
        "author": {"name": AUTHOR}, "license": _license_id()})
    out["plugin/hooks/hooks.json"] = _json(hooks_json())
    out["plugin/.mcp.json"] = _json({"mcpServers": {MCP_NAME: {
        "command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/mcp/sidereus_mcp.py"]}}})
    out[".claude-plugin/marketplace.json"] = _json({
        "name": NAME, "owner": {"name": AUTHOR},
        "metadata": {"description": "Sidereus: local session control viewer for Claude Code."},
        "plugins": [{"name": NAME, "source": "./plugin", "description": DESC}, FA_ENTRY]})
    return out


def plugin_files():
    """Relative (to ROOT) paths currently under plugin/, ignoring __pycache__."""
    got = []
    for d, dirs, files in os.walk(OUT):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        got += [os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, "/") for f in files]   # keys of expected() use "/"
    return sorted(got)


def stale():
    """Paths that differ from what build() would write (missing, changed or not allow-listed)."""
    exp = expected()
    bad = [p for p in plugin_files() if p not in exp]
    for rel, data in exp.items():
        p = os.path.join(ROOT, rel)
        try:
            with open(p, "rb") as f:
                same = f.read() == data
        except OSError:
            same = False
        if not same:
            bad.append(rel)
    return sorted(bad)


def build():
    exp = expected()
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)   # generated folder only; nothing else is removed
    for rel, data in sorted(exp.items()):
        p = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        if rel.endswith((".py", ".sh")):
            shutil.copymode(os.path.join(ROOT, rel[len("plugin/"):]), p)
    return sorted(exp)


def main(argv):
    if "--check" in argv:
        bad = stale()
        for p in bad:
            print("stale: " + p)
        return 1 if bad else 0
    for p in build():
        print("wrote " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
