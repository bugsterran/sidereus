#!/usr/bin/env bash
# Wait for the CI run of one pushed commit and print a short verdict.
#   usage: bash scripts/ci_wait.sh [sha] [branch]      (defaults: HEAD, current branch)
#   exit:  0 = success on the first attempt · 1 = failed / re-run · 2 = no run found or no gh
# ⚠A green re-run (attempt > 1) is reported as FAIL: it hides a flaky test.
# ⚠Local check.sh runs one OS and one Python; Windows and 3.9 only run here.
set -u
sha=${1:-$(git rev-parse HEAD)}
branch=${2:-$(git rev-parse --abbrev-ref HEAD)}
command -v gh >/dev/null 2>&1 || { echo "CI: gh not installed"; exit 2; }

# The push event takes a few seconds to minutes to create the run.
id=""
for _ in $(seq 1 30); do
  id=$(gh run list --branch "$branch" --commit "$sha" --workflow ci.yml --limit 1 \
         --json databaseId --jq '.[0].databaseId // empty' 2>/dev/null)
  [ -n "$id" ] && break
  sleep 10
done
[ -z "$id" ] && { echo "CI: no run for ${sha:0:8} on $branch after 5 min"; exit 2; }

gh run watch "$id" --exit-status --interval 30 >/dev/null 2>&1
read -r concl attempt url < <(gh run view "$id" --json conclusion,attempt,url \
                                --jq '"\(.conclusion) \(.attempt) \(.url)"')

if [ "$concl" = "success" ] && [ "$attempt" = "1" ]; then
  echo "CI PASS ${sha:0:8} on $branch · $url"
  exit 0
fi

echo "CI FAIL ${sha:0:8} on $branch · conclusion=$concl attempt=$attempt · $url"
gh run view "$id" --json jobs \
  --jq '.jobs[] | select(.conclusion != "success" and .conclusion != "skipped")
        | "  job \(.name): \(.conclusion) at \([.steps[] | select(.conclusion == "failure") | .name] | join(", "))"'
# Failing test names and their first error line, de-duplicated across the OS matrix.
gh run view "$id" --log-failed 2>/dev/null \
  | awk -F'\t' '{ sub(/^[^ ]+Z /, "", $3); print $3 }' \
  | grep -E '^(FAIL|ERROR): |^[A-Za-z]*Error: |^  File "[^"]*tests/' \
  | sed -E 's#^  File "[^"]*(tests/[^"]*)", line ([0-9]+).*#  at \1:\2#' \
  | sort | uniq -c | sort -rn | head -15
exit 1
