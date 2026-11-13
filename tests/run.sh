#!/bin/bash
# Run all unit tests with the interpreter launchd uses (3.9.6); CI overrides it via PYTHON.
# Default: parallel groups (tests/run_parallel.py, TESTS_JOBS=N). TESTS_SERIAL=1 or any argument = one serial unittest run.
cd "$(dirname "$0")/.." || exit 1
# Defaults only (a caller's TZ/LC_ALL wins); run_parallel.py children inherit this environment.
export TZ="${TZ-UTC}" LC_ALL="${LC_ALL-C.UTF-8}" PYTHONIOENCODING=utf-8
if [ -z "$TESTS_SERIAL" ] && [ $# -eq 0 ]; then
  exec "${PYTHON:-/usr/bin/python3}" tests/run_parallel.py
fi
# File arguments (tests/test_x.py) are run as modules: passed to discover they became its start
# directory and failed with «Start directory is not importable». Other arguments (-p, -k ...) still go to discover.
# An absolute path passes [ -f ] but would become a module name like «.Users.x.tests.y», so the
# repo root (logical and physical, after the cd above) is stripped first; one outside the repo is refused.
mods=()
root_l="$PWD/"; root_p="$(pwd -P)/"
for a in "$@"; do
  case "$a" in
    *.py) [ -f "$a" ] || { echo "no such test file: $a" >&2; exit 2; }
          m="${a#"$root_l"}"; m="${m#"$root_p"}"; m="${m#./}"
          case "$m" in /*) echo "test file outside the repo: $a" >&2; exit 2 ;; esac
          m="${m%.py}"; mods+=("${m//\//.}") ;;
    *) mods=(); break ;;
  esac
done
if [ ${#mods[@]} -gt 0 ]; then
  exec "${PYTHON:-/usr/bin/python3}" -m unittest -v "${mods[@]}"
fi
exec "${PYTHON:-/usr/bin/python3}" -m unittest discover -s tests -t . -v "$@"
