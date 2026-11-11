# pl_broke

## Meaning
A commit that passed this pipeline's gates in the last 30 days broke later: a later check of the same step failed, or the commit was reverted or is gone.

## Why it matters
The pipeline's gates let a defect through, so its PASS does not prove the change held.

## Who acts
ai

## Next step
Hand the broken passes listed in the weekly report to a session to find which gate missed the defect and add a test or gate that catches it.

## Safe to ignore when
The break came from a later change outside this pipeline's work.
