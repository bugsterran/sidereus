#!/bin/bash
# Single gate runner: check.sh [--fast|--full]  (default --full). Fail-fast; last line is PASS or FAIL.
# --fast skips the unit tests and the screen check (pre-commit hook).
set -u
MODE=full
case "${1:-}" in
  --fast) MODE=fast ;;
  --full|"") MODE=full ;;
  *) echo "usage: $0 [--fast|--full]" >&2; exit 2 ;;
esac
cd "$(dirname "$0")/.." || exit 2
PY=/usr/bin/python3            # ⚠launchd runs 3.9.6; another python lets newer syntax slip through
TMP=$(mktemp -d "${TMPDIR:-/tmp}/sidereus-check.XXXXXX")
T0=$(date +%s)
S0=$T0; nf=0
# Evidence: one JSON line per run (scripts/evidence_rec.py). ⚠ bash $HOME is the user's home, not Sidereus's HOME.
EV="${SIDEREUS_EVIDENCE:-${MAILBOX_DIR:-$HOME/.mailbox-mcp}/evidence.jsonl}"
export SIDEREUS_EV_SCREEN="$TMP/screen.json"
finish() {
  local rc=$? head dirty=0
  head=$(git rev-parse --short HEAD 2>/dev/null)
  [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ] && dirty=1
  local a=("$EV" "$MODE" "$rc" "$PWD" "$head" "$dirty" "$TMP/steps.tsv")
  [ -f "$TMP/screen.json" ] && a+=("$TMP/screen.json")
  "$PY" scripts/evidence_rec.py "${a[@]}" >/dev/null 2>&1 || true
  [ "$rc" -eq 0 ] && rm -rf "$TMP"   # logs stay on FAIL
  exit "$rc"
}
trap finish EXIT
# rec <name> <rc>: step row from $n / $nf, timed since the previous step
rec()  { printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "${n:-0}" "${nf:-0}" "$(( $(date +%s) - S0 ))" >>"$TMP/steps.tsv"; S0=$(date +%s); n=0; nf=0; }
ok()   { rec "$1" 0; printf '  ok    %-10s %s\n' "$1" "$2"; }
fail() { [ "${nf:-0}" -gt 0 ] || nf=1; rec "$1" 1; printf '  FAIL  %-10s %s\n' "$1" "$2"; echo "FAIL ($MODE) at $1 — $(( $(date +%s) - T0 ))s; logs: $TMP"; exit 1; }
# need <step> <what> <count>: a 0 (or non-numeric) count means nothing was checked — never read it as 0 problems
need() { case "$3" in ''|*[!0-9]*) fail "$1" "EMPTY: $2 — nothing was checked" ;; esac; [ "$3" -gt 0 ] || fail "$1" "EMPTY: $2 — nothing was checked"; }

# 1. py_compile — one interpreter for all files (one process per file cost ~6s); temp cache keeps repo __pycache__ untouched
pyf=(); for f in chat_server.py sidereus/*.py mcp/*.py hooks/*.py mailbox_config.py sidereus_cli.py plugins/*/scripts/*.py; do [ -f "$f" ] && pyf+=("$f"); done
n=${#pyf[@]}; need py_compile py_compile "$n"
PYTHONPYCACHEPREFIX="$TMP/pyc" "$PY" - "${pyf[@]}" >"$TMP/py.log" 2>&1 <<'EOF' || fail py_compile "$(tail -1 "$TMP/py.log")"
import sys, py_compile
bad = 0
for f in sys.argv[1:]:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        bad += 1; print("%s:%s %s" % (f, getattr(e.exc_value, "lineno", "?"), e.msg.strip().splitlines()[-1]))
sys.exit(1 if bad else 0)
EOF
ok py_compile "$n files"

# 2. JS syntax — one node process; vm.Script compiles without running (same parse as a browser classic script)
jsf=(); for f in web/*.js web/js/*.js; do [ -f "$f" ] && jsf+=("$f"); done
n=${#jsf[@]}; need node "node files" "$n"
node -e '
const fs = require("fs"), vm = require("vm"); let bad = 0;
for (const f of process.argv.slice(1)) {
  try { new vm.Script(fs.readFileSync(f, "utf8"), { filename: f }); }
  catch (e) { bad++; const at = (e.stack || "").split("\n")[0]; console.log(at + " " + e.name + ": " + e.message); }
}
process.exit(bad ? 1 : 0);' "${jsf[@]}" >"$TMP/js.log" 2>&1 || fail node "$(tail -1 "$TMP/js.log")"
ok node "$n files"

# 3. bash -n
n=0; for f in *.sh scripts/*.sh .githooks/*; do
  [ -f "$f" ] || continue; case "$f" in *.sh|.githooks/*) ;; *) continue ;; esac; n=$((n+1))
  bash -n "$f" 2>>"$TMP/sh.log" || fail bash-n "$f ($(tail -1 "$TMP/sh.log"))"
done; need bash-n "bash -n files" "$n"; ok bash-n "$n files"

# 3b. pipeline JSON vs the fixed runner (schema + stage titles == runner meta.phases)
node scripts/pipeline_check.mjs >"$TMP/pipe.log" 2>&1 || { grep '^FAIL' "$TMP/pipe.log" | head -15; fail pipeline "$(tail -1 "$TMP/pipe.log")"; }
need pipeline pipelines "$(tail -1 "$TMP/pipe.log" | grep -oE '[0-9]+ pipeline' | grep -oE '^[0-9]+')"
ok pipeline "$(tail -1 "$TMP/pipe.log" | sed 's/^pipeline_check: //')"

# 3c. i18n: every T()/U() literal has its dictionary entry (a missing ko entry falls back to English silently).
#   ⚠--stage follows the English-source migration (A bridge · B web literals · D bridge removed); raise it when a stage lands.
node scripts/i18n_check.mjs --stage=D >"$TMP/i18n.log" 2>&1 || { grep '^FAIL' "$TMP/i18n.log" | head -15; fail i18n "$(tail -1 "$TMP/i18n.log")"; }
need i18n "T() literals" "$(tail -1 "$TMP/i18n.log" | grep -oE '[0-9]+ T literals' | grep -oE '^[0-9]+')"
need i18n "ko keys" "$(tail -1 "$TMP/i18n.log" | grep -oE '[0-9]+ ko keys' | grep -oE '^[0-9]+')"
ok i18n "$(tail -1 "$TMP/i18n.log" | sed 's/^i18n_check: //')"

# 4. PAGE assembly smoke
PYTHONPYCACHEPREFIX="$TMP/pyc" "$PY" - >"$TMP/page.log" 2>&1 <<'EOF' || fail page "$(tail -1 "$TMP/page.log")"
import sys; sys.path.insert(0, "tests"); sys.path.insert(0, ".")
from tests._load import load
cs = load()
p = cs.PAGE
assert isinstance(p, str) and len(p) > 10000, "PAGE too small"
assert "@@INCLUDE" not in p, "unresolved @@INCLUDE"
assert "__PAGE_BUILD__" not in p, "unreplaced __PAGE_BUILD__"
print("%d chars" % len(p))
EOF
ok page "$(tail -1 "$TMP/page.log")"

# 5. leak scan over shipped files
PYTHONPYCACHEPREFIX="$TMP/pyc" "$PY" scripts/leakscan.py >"$TMP/leak.log" 2>&1
rc=$?
if [ $rc -ne 0 ]; then grep -v '^leakscan:' "$TMP/leak.log" | head -30; fail leakscan "$(tail -1 "$TMP/leak.log")"; fi
need leakscan "shipped files" "$(tail -1 "$TMP/leak.log" | grep -oE '[0-9]+ shipped files' | grep -oE '^[0-9]+')"
ok leakscan "$(tail -1 "$TMP/leak.log" | sed 's/^leakscan: //')"

# 6a. screen check before the unit tests — the most frequent --full failure, so it surfaces in seconds, not after ~200s
if [ $MODE = full ] && [ -f scripts/screen_check.mjs ]; then
  node scripts/screen_check.mjs >"$TMP/screen.log" 2>&1
  rc=$?
  n=$(grep -cE '^(PASS|FAIL) [0-9]+-' "$TMP/screen.log"); nf=$(grep -cE '^FAIL [0-9]+-' "$TMP/screen.log")
  [ $rc -eq 0 ] || { tail -15 "$TMP/screen.log"; fail screen "exit $rc (log $TMP/screen.log)"; }
  need screen "screen PASS/FAIL lines" "$n"
  ok screen "$(tail -1 "$TMP/screen.log")"
fi

# 6b. performance budgets on an own --demo server (scripts/perf_budget.py; RSS · warm/cold /api/state · agents spawns)
if [ $MODE = full ] && [ -f scripts/perf_budget.py ]; then
  PYTHONPYCACHEPREFIX="$TMP/pyc" "$PY" scripts/perf_budget.py >"$TMP/perf.log" 2>&1
  rc=$?
  n=$(tail -1 "$TMP/perf.log" | grep -oE '^perf_budget: [0-9]+ budgets' | grep -oE '[0-9]+')
  nf=$(tail -1 "$TMP/perf.log" | grep -oE '[0-9]+ over' | grep -oE '^[0-9]+')
  [ $rc -eq 0 ] || fail perf "$(tail -1 "$TMP/perf.log")"
  need perf "perf budgets measured" "$n"
  ok perf "$(tail -1 "$TMP/perf.log" | sed 's/^perf_budget: //')"
fi

# 6. unit tests
if [ $MODE = full ]; then
  PYTHONPYCACHEPREFIX="$TMP/pyc" bash tests/run.sh >"$TMP/tests.log" 2>&1
  rc=$?
  sum=$(grep -E '^(Ran [0-9]+ tests|OK|FAILED)' "$TMP/tests.log" | tail -2 | tr '\n' ' ')   # parallel run: last two = combined
  n=$(sed -n 's/^Ran \([0-9][0-9]*\) tests\{0,1\}.*/\1/p' "$TMP/tests.log" | tail -1)
  nf=$(( $(sed -n 's/^FAILED (.*failures=\([0-9][0-9]*\).*/\1/p' "$TMP/tests.log" | tail -1) + $(sed -n 's/^FAILED (.*errors=\([0-9][0-9]*\).*/\1/p' "$TMP/tests.log" | tail -1) + 0 ))
  if [ $rc -ne 0 ]; then
    grep -E '^(FAIL|ERROR): ' "$TMP/tests.log" | sort -u | head -30
    fail tests "$sum(log $TMP/tests.log)"
  fi
  need tests "unit tests (Ran N)" "$n"
  ok tests "$sum"
fi

echo "PASS ($MODE) — $(( $(date +%s) - T0 ))s"
