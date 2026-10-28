#!/bin/bash
# Mailbox code snapshot — **for reference, not rollback** (use git for history; this keeps a recent copy viewable).
# Scope: code in this dir (*.py, sidereus/*.py, *.sh, web/* page files) + MCP server source. Data like bus.jsonl excluded (size/privacy).
# Retention: last 10. Run: bash <repo>/backup.sh
set -u
umask 077    # archives include config.local.json — private (0600 files, 0700 dir)
CODE_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${MAILBOX_DIR:-$HOME/.mailbox-mcp}"
MCP_SRC="${MAILBOX_MCP_SRC:-$HOME/projects/mailbox-mcp}"   # mailbox MCP server checkout (set MAILBOX_MCP_SRC to yours)
OUT="$DATA_DIR/backup"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"

# ⚠ls -d: plain `ls web/*` expands web/js and web/css into «web/js:» headers plus bare names, which tar cannot find.
ARC="$OUT/mailbox-$STAMP.tar.gz"
ARGS=(-C "$CODE_DIR" $(cd "$CODE_DIR" && ls -d *.py sidereus/*.py *.sh config.example.json features/*.json web/* hooks/*.py ext-hooks/*.py ext-hooks/*.sh ext-hooks/*.json ext-hooks/*.md 2>/dev/null | grep -v '^backup.sh$'))
[ -f "$DATA_DIR/config.local.json" ] && ARGS+=(-C "$DATA_DIR" config.local.json)
# ⚠The MCP checkout is optional: a missing one made tar fail into a 0-byte archive reported as success, and the keep-10 prune then deleted real backups.
if [ -d "$MCP_SRC/src" ]; then ARGS+=(-C "$MCP_SRC" src); [ -f "$MCP_SRC/pyproject.toml" ] && ARGS+=(pyproject.toml)
else echo "   (skip) MCP source not found: $MCP_SRC — set MAILBOX_MCP_SRC"; fi

if tar -czf "$ARC" "${ARGS[@]}" && [ -s "$ARC" ]; then
  SZ=$(du -h "$OUT/mailbox-$STAMP.tar.gz" | cut -f1)
  echo "✅ 백업: $OUT/mailbox-$STAMP.tar.gz ($SZ)"
else
  rm -f "$ARC"    # never leave a partial archive for the prune to count
  echo "⛔ 백업 실패 — 대상 파일을 확인하세요"; exit 1
fi

# Prune old ones (keep last 10) — report what was deleted (never shrink silently)
COUNT=$(ls -1 "$OUT"/mailbox-*.tar.gz 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" -gt 10 ]; then
  ls -1t "$OUT"/mailbox-*.tar.gz | tail -n +11 | while read -r f; do
    echo "   (정리) $(basename "$f")"; rm -f "$f"
  done
fi
echo "   보관 $(ls -1 "$OUT"/mailbox-*.tar.gz | wc -l | tr -d ' ')개"
