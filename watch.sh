#!/usr/bin/env bash
# watch.sh — starts the mailbox watcher **the same way for everyone**.
#
#   Why a script: everyone used to start it their own way, and only one session had it on (measured 2026-08-13:
#   1 of 3 had a `watch` heartbeat). Without it you see new posts **only when you call a tool yourself**,
#   and peers see `○감시없음` — nobody can tell offline from quiet.
#
#   Usage: <repo>/watch.sh <my-id>
#          MAILBOX_NAG_S=600 <repo>/watch.sh advocate     # adjust nag interval (default 300s)
#
#   Optional. Claude Code sessions do NOT need this: the Stop async hook hooks/mailbox_wake.py (asyncRewake)
#   wakes an idle session on new mail. Monitor is off by company policy — do not start this via Monitor or
#   a background shell from a session. Use it only to watch the bus from a plain terminal.
set -euo pipefail

HOME_DIR="${MAILBOX_DIR:-${MAILBOX_HOME:-$HOME/.mailbox-mcp}}"   # data dir
CODE_DIR="$(cd "$(dirname "$0")" && pwd)"
ME="${1:-${MAILBOX_ME:-}}"

if [ -z "$ME" ]; then
  echo "⛔ 아이디가 필요합니다:  $0 <내아이디>" >&2
  echo "   지금 버스에 있는 아이디: $(python3 - "$HOME_DIR" <<'PY' 2>/dev/null || echo '(못 읽음)'
import json,sys,pathlib
bus = pathlib.Path(sys.argv[1]) / "bus.jsonl"
ids = {json.loads(l).get("from") for l in bus.open() if l.strip()} if bus.exists() else set()
print(", ".join(sorted(i for i in ids if i)))
PY
)" >&2
  exit 2
fi

# ★Set `MAILBOX_SELF` too — measured incident (2026-08-07): ME set without SELF
#   **misread posts as someone else's and swallowed them forever**. The two always go together.
export MAILBOX_ME="$ME"
export MAILBOX_SELF="${MAILBOX_SELF:-$ME}"

# ★**Never start twice** with the same id (2026-09-04). Measured: 3 monitor_stream processes were running,
#   one on 4-hour-old code. Two watchers with one id wake twice per post, doubling requests.
#   `exec` keeps the PID, so the $$ written here is the watcher's PID.
#   If it dies, kill -0 fails, so a stale lock is ignored automatically (no cleanup needed).
LOCK="$HOME_DIR/.watch-$ME.pid"
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "이미 감시 중입니다 — PID $(cat "$LOCK"). 새로 띄우지 않습니다."
  echo "바꿔 띄우려면:  kill $(cat "$LOCK") && $0 $ME"
  exit 0
fi
echo $$ > "$LOCK"

echo "메일박스 감시 — $ME (SELF=$MAILBOX_SELF · 재촉 ${MAILBOX_NAG_S:-300}초)"
exec python3 "$CODE_DIR/monitor_stream.py"
