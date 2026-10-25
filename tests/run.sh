#!/bin/bash
# Run all unit tests with the interpreter launchd uses (3.9.6); CI overrides it via PYTHON.
# Default: parallel groups (tests/run_parallel.py, TESTS_JOBS=N). TESTS_SERIAL=1 or any argument = one serial unittest run.
cd "$(dirname "$0")/.." || exit 1
# Defaults only (a caller's TZ/LC_ALL wins); run_parallel.py children inherit this environment.
export TZ="${TZ-UTC}" LC_ALL="${LC_ALL-C.UTF-8}" PYTHONIOENCODING=utf-8
if [ -z "$TESTS_SERIAL" ] && [ $# -eq 0 ]; then
  exec "${PYTHON:-/usr/bin/python3}" tests/run_parallel.py
fi
exec "${PYTHON:-/usr/bin/python3}" -m unittest discover -s tests -t . -v "$@"
