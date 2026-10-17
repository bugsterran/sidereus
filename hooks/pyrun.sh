#!/bin/sh
# Run a Python 3.9+ script for the plugin hooks (shell form: sh -c on macOS/Linux, Git Bash on Windows).
# Not Windows: plain python3, the same process the hooks always ran.
if [ "${OS:-}" != "Windows_NT" ]; then exec python3 "$@"; fi
# ⚠Windows: python3 may be the Microsoft Store stub and python.org ships no python3.exe, so probe each
# candidate with a version check (stdin closed so the hook's JSON stays for the real run); $c is split on purpose.
for c in python3 "py -3" python; do
  if $c -c 'import sys; sys.exit(sys.version_info < (3, 9))' </dev/null >/dev/null 2>&1; then exec $c "$@"; fi
done
echo "sidereus: no Python 3.9+ found (tried python3, py -3, python)" >&2
exit 127
