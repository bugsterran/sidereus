# pl_too_few

## Meaning
This pipeline ran fewer than 5 times in the last 30 days, too few to judge whether its passes hold.

## Why it matters
With so few runs, one broken or clean pass swings the result, so no verdict would be trustworthy.

## Who acts
owner

## Next step
Run changes through this pipeline (`[pl:<name>/<stage>]` tags) until it has 5 runs in 30 days, or retire it if it is no longer used.

## Safe to ignore when
The pipeline is meant for rare work, such as releases.
