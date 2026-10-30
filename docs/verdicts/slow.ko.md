# slow

## Meaning
OTel 로 잰 이 훅의 이벤트·대상 실행이 기간 동안 평균 1000 ms 이상 걸렸습니다.

## Why it matters
세션은 실행마다 훅을 기다리므로 실행할 때마다 이 시간이 듭니다. 같은 실행에 훅이 여럿 걸리면 그 훅들을 합친 시간입니다.

## Who acts
owner

## Next step
어느 스크립트가 느린지 직접 재 보고, 빠르게 고치거나 matcher 를 좁히거나 `/hooks` 에서 지웁니다.

## Safe to ignore when
그만큼 걸리는 일을 하는 훅이거나, 세션이 기다리지 않는 이벤트일 때.
