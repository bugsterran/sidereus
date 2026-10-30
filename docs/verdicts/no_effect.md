# no_effect

## Meaning
The hook ran 50 or more times and never blocked and never printed anything, measured by OTel.

## Why it matters
A hook with no visible effect may be leftover load. Side effects such as file writes are not visible here, so it may still be doing its job.

## Who acts
owner

## Next step
Check what the script is meant to do; if it only logs or writes files you still use, keep it, otherwise remove it with `/hooks`.

## Safe to ignore when
The hook works through side effects such as writing files or sending metrics.
