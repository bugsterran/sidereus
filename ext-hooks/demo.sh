#!/bin/bash
# demo.sh — synthetic hook that previews how external CLIs look on the Sidereus screen before installing them.
# ★All session ids start with `demo-` so they never mix with real sessions. cwd is just a string — nothing is written there.
#   bash demo.sh        start 3      bash demo.sh clean   remove all (SessionEnd)
set -u

CODE_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # repo root, wherever it is checked out
PORT="$(/usr/bin/python3 "$CODE_DIR/mailbox_config.py" --port 2>/dev/null || echo 8799)"   # env SIDEREUS_PORT > config port > 8799
URL="${SIDEREUS_HOOK_URL:-http://127.0.0.1:$PORT/api/hook}"
CS="$CODE_DIR/sidereus/ext_store.py"   # EXT_PLAT/EXT_STATE live here since the ext -> ext_store split
EXT_JSON="${MAILBOX_DIR:-$HOME/.mailbox-mcp}/ext-sessions.json"   # data dir

# ⚠Never invent platforms/events — read them from EXT_PLAT·EXT_STATE in sidereus/ext_store.py, the source of truth.
PLATS="$(sed -n '/^EXT_PLAT = {/,/}/p' "$CS" | grep -o '"[a-z][a-z]*": "[a-z][a-z]"' | sed 's/":.*//;s/"//')"
EVENTS="$(sed -n '/^EXT_STATE = {/,/}/p' "$CS" | grep -o '"[A-Za-z][A-Za-z]*": "[a-z][a-z]*"' | sed 's/":.*//;s/"//')"
if [ -z "$PLATS" ] || [ -z "$EVENTS" ]; then
  echo "sidereus/ext_store.py 에서 EXT_PLAT/EXT_STATE 를 읽지 못했습니다 — 데모를 건너뜁니다."; exit 0
fi
ok_plat() { printf '%s\n' "$PLATS" | grep -qx "$1"; }
ok_ev()   { printf '%s\n' "$EVENTS" | grep -qx "$1" || [ "$1" = "SessionEnd" ]; }   # SessionEnd means «remove», so it is not in EXT_STATE

DOWN=0
post() {   # post <platform> <sid> <event> [cwd] [model] [tool]
  ok_plat "$1" || { echo "모르는 플랫폼 $1 — 건너뜁니다"; return 0; }
  ok_ev "$3"   || { echo "모르는 이벤트 $3 — 건너뜁니다"; return 0; }
  body="{\"platform\":\"$1\",\"session_id\":\"$2\",\"event\":\"$3\""
  [ -n "${4:-}" ] && body="$body,\"cwd\":\"$4\""
  [ -n "${5:-}" ] && body="$body,\"model\":\"$5\""
  [ -n "${6:-}" ] && body="$body,\"tool_name\":\"$6\""
  body="$body}"
  curl -s -f --max-time 2 -X POST -H 'Content-Type: application/json' -d "$body" "$URL" >/dev/null 2>&1 \
    || { DOWN=1; return 1; }
  return 0
}

G_SID="demo-gemini-0001"; G_CWD="$HOME/work/repo-A"
C_SID="demo-codex-0002";  C_CWD="$HOME/work/repo-B"
U_SID="demo-cursor-0003"; U_CWD="$CODE_DIR"

if [ "${1:-}" = "clean" ]; then
  post gemini "$G_SID" SessionEnd || true
  if [ "$DOWN" = "1" ]; then
    echo "아고라(${URL})가 응답하지 않습니다 — 지울 것도 없습니다. 켜져 있는지 확인해 주세요."; exit 0
  fi
  post codex  "$C_SID" SessionEnd
  post cursor "$U_SID" SessionEnd
  # ★Also sweep any other `demo-` rows left on screen (leftovers from runs with changed ids).
  /usr/bin/python3 - "$EXT_JSON" 2>/dev/null <<'PY' | while read -r p s; do post "$p" "$s" SessionEnd; done
import json, sys
try: recs = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception: recs = []
for r in recs if isinstance(recs, list) else []:
    sid = str(r.get("session_id") or "")
    if sid.startswith("demo-"):
        print(str(r.get("platform") or ""), sid)
PY
  left="$(/usr/bin/python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(sum(1 for r in d if str(r.get("session_id","")).startswith("demo-")))' "$EXT_JSON" 2>/dev/null || echo '?')"
  echo "데모 세션을 지웠습니다 (남은 demo- 행: ${left}). 화면 http://127.0.0.1:$PORT 을 새로고침하세요."
  exit 0
fi

# ① gemini — running (think)
post gemini "$G_SID" SessionStart "$G_CWD" "gemini-2.5-pro" || true
if [ "$DOWN" = "1" ]; then
  echo "아고라(${URL})가 응답하지 않습니다 — 데모를 건너뜁니다."
  LABEL="$(/usr/bin/python3 "$CODE_DIR/mailbox_config.py" --label viewer 2>/dev/null || echo io.sidereus.viewer)"
  echo "  띄우기: launchctl kickstart -k gui/$(id -u)/$LABEL"
  exit 0
fi
post gemini "$G_SID" UserPromptSubmit "$G_CWD" "gemini-2.5-pro"

# ② codex — running a tool (tool)
post codex "$C_SID" SessionStart      "$C_CWD" "gpt-5-codex"
post codex "$C_SID" UserPromptSubmit  "$C_CWD" "gpt-5-codex"
post codex "$C_SID" PreToolUse        "$C_CWD" "gpt-5-codex" "Shell"

# ③ cursor — waiting on a human (ask · blocked)
post cursor "$U_SID" SessionStart     "$U_CWD" "composer-1"
post cursor "$U_SID" UserPromptSubmit "$U_CWD" "composer-1"
post cursor "$U_SID" Notification     "$U_CWD" "composer-1"

echo "가짜 외부 세션 3개를 띄웠습니다 — gemini(도는 중) · codex(도구 실행 중) · cursor(사람 대기). 화면 http://127.0.0.1:$PORT 을 새로고침하세요. 지울 때: bash ext-hooks/demo.sh clean"
exit 0
