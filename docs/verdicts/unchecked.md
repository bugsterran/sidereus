# unchecked

## Meaning
The PASS was recorded with uncommitted changes, or git did not answer.

## Why it matters
Without a commit there is no way to tell whether the fix is still in the code.

## Who acts
self

## Next step
Commit the change (`git status` shows what is open), then run the same check again.
