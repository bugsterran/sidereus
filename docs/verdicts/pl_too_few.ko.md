# pl_too_few

## Meaning
이 파이프라인은 최근 30일 동안 5번보다 적게 실행되어 통과가 버티는지 판단하기에 부족합니다.

## Why it matters
실행이 이렇게 적으면 통과 하나가 결과를 크게 흔들어 어떤 판정도 믿기 어렵습니다.

## Who acts
owner

## Next step
30일에 5번이 될 때까지 변경을 이 파이프라인으로 돌리거나(`[pl:<name>/<stage>]` 태그), 더 쓰지 않으면 정리합니다.

## Safe to ignore when
릴리스처럼 드물게 쓰는 파이프라인일 때.
