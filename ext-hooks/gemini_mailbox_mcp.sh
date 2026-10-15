#!/bin/sh
# Mailbox MCP launcher for Gemini CLI (~/.gemini/settings.json mcpServers.mailbox.command).
# Gives the Gemini session in a folder its own mailbox id, never the folder's Claude id:
#   identity key = "gemini:<physical cwd>" (mailbox_login saves there), default id = "<basename>-gemini".
# ext-hooks/gemini_mail_stop.py resolves the same id; keep the two in step.
# ⚠ This lives in a file, not inline in settings.json: Gemini expands $VAR in settings strings at load
#   time, which blanked the inline shell variables and left the server as "anon" (seen 2026-09-24).
# ⚠ Overrides CLAUDE_PROJECT_DIR / MAILBOX_ME inherited from a Claude Code shell.
# MAILBOX_MCP_DIR = checkout of the mailbox-mcp server (default ~/projects/mailbox-mcp).
# Optional $1 = platform key (codex, ...; default gemini) -> "<key>:<cwd>" / "<basename>-<key>", as gemini_mail_stop.py --platform.
p="${1:-gemini}"
case "$p" in *[!a-z0-9]*|""|claude) echo "gemini_mailbox_mcp.sh: bad platform '$p'" >&2; exit 2 ;; esac
d="$(pwd -P)"
CLAUDE_PROJECT_DIR="$p:$d"
MAILBOX_ME="$(basename "$d")-$p"
export CLAUDE_PROJECT_DIR MAILBOX_ME
UV="$(command -v uv || echo /opt/homebrew/bin/uv)"
exec "$UV" --directory "${MAILBOX_MCP_DIR:-$HOME/projects/mailbox-mcp}" run mailbox-mcp
