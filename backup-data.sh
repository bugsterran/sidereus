#!/bin/bash
# Data snapshot — **protects the source of truth.**
#
#   Why a separate script: `backup.sh` holds **code only** by design (data excluded — size/privacy).
#   But `bus.jsonl` is the conversation record that rooms and decisions are read back from.
#   Measured 2026-08-19: the record was 1.8MB and the only backup was `bus.jsonl.bak` (Aug 6 · 784KB) —
#   **13 days ran without a backup.** Code can be fixed if broken (decided), but a conversation cannot be rewritten.
#
#   Scope: append-only logs (bus·acks·cards) + small configs whose loss breaks rooms (rooms·profiles·identity).
#          Cursors·PIDs·presence are **excluded** — restoring them rewinds to an old point and breaks loss prevention.
#   Retention: last 7. ★No new snapshot if nothing changed (7 identical files in a quiet week = 1 day, not 7).
#   Stays local: only on this machine (`backup/data/`). Same exposure as the originals.
#
#   Manual: bash ~/.mailbox-mcp/backup-data.sh
#   Auto:   launchd `<launchd_label_prefix>.databackup` (daily 09:05 · runs on wake if asleep)
set -u
HOME_DIR="${MAILBOX_DIR:-$HOME/.mailbox-mcp}"   # data dir
OUT="$HOME_DIR/backup/data"
mkdir -p "$OUT"

SRC="bus.jsonl acks.jsonl cards.jsonl rooms.json room-admin.json room-tags.json profiles.json identity.json"
HAVE=$(cd "$HOME_DIR" && ls $SRC 2>/dev/null | tr '\n' ' ')
if [ -z "$HAVE" ]; then
  echo "⛔ 백업할 데이터가 없습니다 — 경로를 확인하세요($HOME_DIR)"; exit 1
fi

# Fingerprint of current state (hash of per-file hashes) — skip if identical to the previous snapshot
SUM=$(cd "$HOME_DIR" && shasum -a 256 $HAVE | shasum -a 256 | cut -c1-16)
LAST=$(ls -1t "$OUT"/mailbox-data-*.sha 2>/dev/null | head -1)
if [ -n "$LAST" ] && [ "$(cat "$LAST" 2>/dev/null)" = "$SUM" ]; then
  echo "= $(date '+%Y-%m-%d %H:%M') 변경 없음($SUM) — 생략: $(basename "${LAST%.sha}").tar.gz"
  exit 0
fi

BASE="$OUT/mailbox-data-$(date +%Y%m%d-%H%M%S)"
if ! tar -czf "$BASE.tar.gz" -C "$HOME_DIR" $HAVE 2>/dev/null; then
  echo "⛔ $(date '+%Y-%m-%d %H:%M') 스냅샷 실패 — 대상: $HAVE"; exit 1
fi
echo "$SUM" > "$BASE.sha"
echo "✅ $(date '+%Y-%m-%d %H:%M') 스냅샷: $(basename "$BASE").tar.gz ($(du -h "$BASE.tar.gz" | cut -f1) · $HAVE)"

# Prune old ones (keep last 7) — report what was deleted (never shrink silently)
COUNT=$(ls -1 "$OUT"/mailbox-data-*.tar.gz 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" -gt 7 ]; then
  ls -1t "$OUT"/mailbox-data-*.tar.gz | tail -n +8 | while read -r f; do
    echo "   (정리) $(basename "$f")"; rm -f "$f" "${f%.tar.gz}.sha"
  done
fi
echo "   보관 $(ls -1 "$OUT"/mailbox-data-*.tar.gz | wc -l | tr -d ' ')개 · $(du -sh "$OUT" | cut -f1)"
