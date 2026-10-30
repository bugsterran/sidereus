# slow_block

## Meaning
A hook on an event the session waits for has a timeout over 30 seconds.

## Why it matters
A hung script stalls the session for that long.

## Who acts
owner

## Next step
Lower the timeout with `/hooks`, or keep it if the work needs the time.

## Safe to ignore when
The hook does real work that needs the time and has never hung.
