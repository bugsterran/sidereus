# dup

## Meaning
The same hook command is registered twice on one event and matcher.

## Why it matters
It runs twice per event: double output, double blocking, double time.

## Who acts
self

## Next step
Remove one copy with `/hooks`.
