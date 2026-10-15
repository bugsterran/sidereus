#!/bin/bash
# card.sh — a task-completion card **written by the session itself**. Replaces external messenger notifications (removed 2026-08-19).
#   Write: ~/.mailbox-mcp/card.sh "title" "one-line summary"
#   Read:  🔔 in the viewer header (config `port`, default 8799) — 5s toast, then stacks in the bell until confirmed (history is kept).
#   ⚠Unlike automatic cards (session turn end), this one is **hand-picked**, so use it for milestones only (external messenger notifications already taught us about noise).
set -u
[ $# -lt 1 ] && { echo "사용: card.sh \"제목\" [\"요약\"]" >&2; exit 2; }
python3 - "$1" "${2:-}" "$(basename "$PWD")" "$PWD" "${MAILBOX_DIR:-$HOME/.mailbox-mcp}" <<'PY'
import json, sys, os
from datetime import datetime
title, text, proj, cwd, data = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
row = {"at": datetime.now().isoformat(timespec="seconds"), "kind": "done",
       "project": proj, "title": title, "text": text, "cwd": cwd}
with open(os.path.join(os.path.expanduser(data), "cards.jsonl"), "a") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"✅ 카드: [{proj}] {title}")
PY
