#!/bin/bash
# Point this repo's git hooks at .githooks/ (idempotent).
cd "$(dirname "$0")/.." || exit 1
chmod +x .githooks/* scripts/check.sh
cur=$(git config --get core.hooksPath)
if [ "$cur" = ".githooks" ]; then
  echo "core.hooksPath already .githooks — nothing to do"
else
  git config core.hooksPath .githooks
  echo "core.hooksPath: '${cur:-<unset>}' -> '.githooks' (pre-commit runs scripts/check.sh --fast)"
fi
