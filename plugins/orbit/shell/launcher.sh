# Orbit launcher: picks a Claude config dir per folder, then runs the real `claude`.
# Sourced by zsh and bash (macOS ships bash 3.2). FA_PY = path to accounts.py (set by `shell install`).
claude() {
  local acc= tty=1 out name dir tail si=
  local -a rest
  rest=()
  while [ $# -gt 0 ]; do
    case "$1" in
      -A|--account)
        # ⚠ `shift 2` with one arg left does not shift in bash and would loop forever
        [ $# -ge 2 ] || { printf 'claude: %s needs an account name\n' "$1" >&2; return 2; }
        acc="$2"; shift 2 ;;
      --account=*) acc="${1#*=}"; shift ;;
      --) rest+=("$@"); break ;;
      -p|--print) tty=0; rest+=("$1"); shift ;;
      *) rest+=("$1"); shift ;;
    esac
  done
  # ⚠ ${rest[@]+...} keeps an empty array from tripping `set -u` in bash 3.2
  # Explicit CLAUDE_CONFIG_DIR wins unless -A was given.
  if [ -z "$acc" ] && [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then command claude ${rest[@]+"${rest[@]}"}; return; fi
  # Not set up (no registry, no accounts.py, no python3): behave like plain claude.
  if [ -z "${FA_PY:-}" ] || [ ! -f "$FA_PY" ] || [ ! -f "$HOME/.claude-accounts" ] || ! command -v python3 >/dev/null 2>&1; then
    command claude ${rest[@]+"${rest[@]}"}; return
  fi
  { [ -t 0 ] && [ -t 2 ]; } || tty=0
  # Array, not ${acc:+--account "$acc"}: zsh would pass that as one word.
  local -a aa
  aa=()
  [ -n "$acc" ] && aa=(--account "$acc")
  local rc=0
  out=$(FA_RESOLVE_FIELDS=3 python3 "$FA_PY" resolve --cwd "$PWD" ${aa[@]+"${aa[@]}"} --tty "$tty") || rc=$?
  # Exit 2 = unknown account: stop. Any other failure or malformed output: start plain claude anyway.
  [ "$rc" -eq 2 ] && return 2
  case "$out" in
    *$'\t'*) [ "$rc" -eq 0 ] || { command claude ${rest[@]+"${rest[@]}"}; return; } ;;
    *) command claude ${rest[@]+"${rest[@]}"}; return ;;
  esac
  # name<TAB>dir[<TAB>signed-in 0|1]; an older accounts.py prints two fields.
  name=${out%%$'\t'*}; tail=${out#*$'\t'}; dir=${tail%%$'\t'*}
  case "$tail" in *$'\t'*) si=${tail#*$'\t'} ;; esac
  if [ "$si" = "0" ]; then printf '→ %s (not signed in yet: type /login)\n' "$name" >&2
  else printf '→ %s\n' "$name" >&2; fi
  if [ "$dir" = "-" ]; then
    # Subshell instead of `env -u`: keeps the caller's env and avoids non-portable flags.
    (unset CLAUDE_CONFIG_DIR; command claude ${rest[@]+"${rest[@]}"})
  else
    CLAUDE_CONFIG_DIR="$dir" command claude ${rest[@]+"${rest[@]}"}
  fi
}
orbit() { python3 "$FA_PY" "$@"; }
claude-account() { orbit "$@"; }   # pre-rename command name
