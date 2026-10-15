#!/bin/bash
# Always-on watch loop — watch_bus.py **exits on new mail** by design (that is how it notifies), so exiting is normal.
#   This wrapper keeps restarting it. Harness background jobs get reaped (measured: killed·exit 144), so launchd runs it.
#   The cursor (.watch-cursor) prevents loss.
cd "$(dirname "$0")" || exit 1   # code dir; watch_bus.py finds data via MAILBOX_DIR
while true; do
  WATCH_TIMEOUT=3600 WATCH_FORCE=1 /usr/bin/python3 watch_bus.py
  sleep 5
done
