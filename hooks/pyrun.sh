#!/bin/sh
# Run a Python 3.9+ script for the plugin hooks (shell form: sh -c on macOS/Linux, Git Bash on Windows).
# SIDEREUS_PYTHON (one executable) overrides; the plugin MCP server reads the same variable.
# Not Windows: plain python3, the same process the hooks always ran.
if [ "${OS:-}" != "Windows_NT" ]; then exec "${SIDEREUS_PYTHON:-python3}" "$@"; fi
if [ -n "${SIDEREUS_PYTHON:-}" ]; then exec "$SIDEREUS_PYTHON" "$@"; fi
# ⚠Windows: each Python start costs ~0.5-1.5 s and the old probe ran up to three before the hook, which overran the
# 10 s UserPromptSubmit timeout. The resolved exe is cached with the PATH it was found on (shell builtins only on a hit).
f="${CLAUDE_PLUGIN_DATA:-${TMP:-${TEMP:-/tmp}}}/sidereus-pyrun.cache"
if [ -r "$f" ] && { IFS= read -r cp; IFS= read -r ce; } <"$f" && [ "$cp" = "$PATH" ] && [ -n "$ce" ] && [ -f "$ce" ]; then
  exec "$ce" "$@"
fi
# ⚠python3 on PATH is often the Microsoft Store alias (WindowsApps): never run it, it can open the Store.
# py -3 first (python.org default). stdin closed so the hook's JSON stays for the real run; $c is split on purpose.
probe='import sys; sys.version_info >= (3, 9) or sys.exit(1); sys.stdout.write(sys.executable.replace("\\", "/"))'
for c in "py -3" python3 python; do
  w=$(command -v "${c%% *}") || continue
  case "$w" in *[Ww]indows[Aa]pps*) continue;; esac
  e=$($c -c "$probe" </dev/null 2>/dev/null) || continue
  [ -n "$e" ] || continue
  { printf '%s\n%s\n' "$PATH" "$e" >"$f.$$" && mv -f "$f.$$" "$f"; } 2>/dev/null || rm -f "$f.$$" 2>/dev/null
  exec "$e" "$@"
done
echo "sidereus: no Python 3.9+ found (tried py -3, python3, python; Store aliases skipped). Set SIDEREUS_PYTHON." >&2
exit 127
