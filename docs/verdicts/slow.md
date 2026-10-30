# slow

## Meaning
Firings of this hook's event and subject averaged 1000 ms or more over the covered days, measured by OTel.

## Why it matters
The session waits for the hooks of a firing, so every run pays this time. When several hooks match the same firing, the time is theirs combined.

## Who acts
owner

## Next step
Find which script is slow (time it by hand), then make it faster, narrow its matcher, or remove it with `/hooks`.

## Safe to ignore when
The hook does work that needs the time, or it runs on an event the session does not wait for.
