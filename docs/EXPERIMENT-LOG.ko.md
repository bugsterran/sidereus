# 실험 기록

Sidereus 는 한 사람이 한 대의 컴퓨터에서 돌리는 실험이다(n=1). 이 기록은 동작 방식에 대한 생각 하나마다 무엇을 해 봤는지, 무엇을 쟀는지, 어떻게 결정했는지를 함께 남긴다. 버린 생각도 지우지 않고 여기 둔다.

CI 는 푸시된 결과를 검사하고, Sidereus 는 그 결과에 이른 과정을 검사한다. 단계 순서, 게이트, 리뷰를 편집 시점과 커밋 시점에, CLI 를 가리지 않고 본다. 아래 항목 대부분은 이 두 번째 검사가 제값을 하는지를 시험한다.

판정 읽는 법: 유지는 변경이 남아 있고 아래 숫자가 그 근거라는 뜻이다. 폐기는 그 변경을 빼거나 그 측정 방식을 버렸다는 뜻이다. 미정은 아직 데이터가 모자라다는 뜻이고, 다음 칸에 무엇이 결론을 낼지 적었다. 숫자마다 출처 커밋이나 이슈를 걸고 기간을 적었다. 표본이 작으면 작다고 적었다.

## 1. 뷰어 메모리는 페이지가 아니라 서버에 있다

가설: 뷰어의 메모리 비용은 브라우저 페이지가 아니라 Python 서버의 캐시에서 나온다.

해 본 것: 둘을 따로 잰 뒤, 도구 사용 색인을 파일별 압축 배열로 바꾸고 구조 캐시에 상한을 뒀다([9ed37819](https://github.com/bugsterran/sidereus/commit/9ed37819), [80674309](https://github.com/bugsterran/sidereus/commit/80674309), [#17](https://github.com/bugsterran/sidereus/issues/17)).

측정: 2026-10-21 에 서버 RSS 423 MB, 페이지 JS 힙 28 MB. 수정 전에는 재시작 36분 뒤 715 MB 이고 계속 올랐다. 수정 후에는 26분부터 4시간까지 282-304 MB, 8시간까지 310-338 MB 로 평탄했다. 표본은 한 번이다([#17](https://github.com/bugsterran/sidereus/issues/17)).

판정: 유지.

다음: 정상 상태 200 MB 예산이 이제 `check.sh --full` 에서 돈다([#24](https://github.com/bugsterran/sidereus/issues/24)). 2026-10-26 에 4시간 가동 후 74 MB 였다([#26](https://github.com/bugsterran/sidereus/issues/26)).

## 2. 기동 후 30초 RSS 를 메모리 예산으로 쓰기

가설: "기동 후 30초 동안 매초 RSS 200 MB 이하" 는 안정된 예산이다.

해 본 것: 도구 색인 저장과 꼬리 읽기를 스트리밍으로 바꾸고([083e305d](https://github.com/bugsterran/sidereus/commit/083e305d), [283eb2db](https://github.com/bugsterran/sidereus/commit/283eb2db)) macOS 에서 기동 구간을 표본으로 쟀다([#30](https://github.com/bugsterran/sidereus/issues/30)).

측정: 스트리밍 저장으로 기동 최고치 291 에서 226 MB(같은 데이터로 A/B). 10초 시점 75 MB 라는 값은 페이지 압축 때문이었다. 기동 8분 뒤 footprint 199 MB, 압축 81 MB, RSS 131 MB 였고, 얼마나 압축되는지는 시스템 메모리 압박에 따라 달라진다(2026-10-26 ~ 10-29, [#30](https://github.com/bugsterran/sidereus/issues/30)).

판정: 측정 방식으로서는 폐기. 예산을 30초 시점 물리 footprint 로 다시 정했고, 두 커밋 뒤 169-180 MB 였다. 처음 몇 초의 196-218 MB 최고치는 알려진 스파이크로 남긴다.

다음: 계획 없음. 30초 footprint 가 200 MB 를 넘으면 다시 연다.

## 3. 보안 검사 옆의 린트 검사

가설: 프로젝트 린트 검사를 보안 검사 옆에서 뷰어로 돌리는 것은 탭 하나, 배지 하나, 파이프라인 하나를 들일 만하다.

해 본 것: `project-checks` 파이프라인, 린트 실행기, Quality 탭, "Checks n" 배지.

측정: 잰 것이 없다. 제거 커밋에는 범위만 적혀 있다([954038ff](https://github.com/bugsterran/sidereus/commit/954038ff), 2026-10-16).

판정: 폐기. 검사 종류는 보안 검사 하나만 남았다.

다음: 없음.

## 4. 가드가 잡아야 할 것과 통과시켜야 할 것을 재생하기

가설: Harness 리포트가 하는 주장(가드가 막았다, 게이트가 빨강에서 초록이 됐다, 통과가 유지됐다)은 실제 훅을 고정된 사례로 재생해 확인할 수 있다. 사례마다 통과해야 하는 대조군을 둔다.

해 본 것: 잡을 사례와 대조군을 실제 기록기로 재생하는 세트([9fbf2cb8](https://github.com/bugsterran/sidereus/commit/9fbf2cb8)), 사례 수는 [62226d42](https://github.com/bugsterran/sidereus/commit/62226d42) 기준 11개, 이후 "Guard self-check" 표로 화면에 보였다([62226d42](https://github.com/bugsterran/sidereus/commit/62226d42), [#27](https://github.com/bugsterran/sidereus/issues/27)).

측정: 세트가 실제 결함 하나를 찾았다. 필수 게이트 전 커밋을 가드가 막고도 기록하지 않아 화면이 "Blocked 0" 이었다. 수정 후 라이브에서 11개 중 11개 통과(2026-10-30, [62226d42](https://github.com/bugsterran/sidereus/commit/62226d42)).

판정: 유지.

다음: 새 가드마다 잡을 사례와 대조군을 함께 넣는다.

## 5. 레드 체크: 게이트가 실패할 수는 있나

가설: 실패하는 것을 한 번도 본 적 없는 게이트는 실패할 수 없을 수도 있다. 임시 복제본에 알려진 결함을 넣어 보면 알 수 있다.

해 본 것: 게이트마다 일부러 깨뜨린 복제본에서 게이트를 돌리는 레드 체크.

측정: 이 저장소에서 보안 게이트의 레드 체크가 실패했다. 스캐너는 `git archive HEAD` 내보내기를 읽기 때문에 커밋되지 않은 가짜 키 파일은 검사되지 않았다. 복제본 안에서 주입을 커밋하게 바꾼 뒤 `check.sh --fast`, `--full`, 보안 게이트 모두 레드 체크를 통과한다(2026-10-24, [352d5a65](https://github.com/bugsterran/sidereus/commit/352d5a65)).

판정: 유지.

다음: 아직 확인되지 않은 게이트에도 돌린다. 2026-10-25 주간 리포트(로컬, 6번 항목 참고) 기준 `sidereus-change` 파이프라인 게이트 8개 중 3개만 실패할 수 있음이 확인됐다.

## 6. 게이트 통과가 그 뒤에도 유지됐나

가설: 통과가 유지됐는지는 git 만으로 읽을 수 있다. 14일 안에 같은 파일을 건드린 커밋이 오면 "수정이 뒤따름" 으로 센다([ab8c87de](https://github.com/bugsterran/sidereus/commit/ab8c87de), [#1](https://github.com/bugsterran/sidereus/issues/1)).

해 본 것: 실행이 끝날 때 파이프라인별로 쓰는 주간 리포트(리포트는 로컬에만 있고 `eval/` 은 커밋하지 않는다).

측정: `sidereus-change` 의 2026-10-25 로컬 리포트: 실행 33회, 순서 위반 14건 차단, 통과 22건 중 나중에 깨진 것 0건, 22건 모두 수정이 뒤따름, 최근 30일 실행의 70% 에서 리뷰 되돌림. 통과 22건은 커밋 4개에서 나왔다: [cc9cbbd9](https://github.com/bugsterran/sidereus/commit/cc9cbbd9), [90a8c734](https://github.com/bugsterran/sidereus/commit/90a8c734), [1667ab35](https://github.com/bugsterran/sidereus/commit/1667ab35), [88bea14d](https://github.com/bugsterran/sidereus/commit/88bea14d).

판정: 미정. 모든 통과에 켜지는 신호로는 아직 통과끼리 구분이 안 된다.

다음: 리포트가 같은 커밋을 반복해 세고(22줄 = 커밋 4개) 모든 통과가 "수정이 뒤따름" 이라 아직 통과끼리 구분되지 않는다. 다음 시도는 게이트 통과가 아니라 커밋 단위로 세어 이를 고치는 것이다. 14일 창을 바꾸기 전에 주간 리포트를 두 번 더 본다.

## 7. 파이프라인 밖에서 한 일을 선언하기

가설: 세션이 파이프라인 밖 작업을 종류별로 선언하게 하면, 반복되는 "no-fit" 선언이 어떤 파이프라인이 빠졌는지 보여 준다.

해 본 것: `[pl-none:<category>]` 선언, 선언 없으면 한 번 거부([baa40276](https://github.com/bugsterran/sidereus/commit/baa40276)), 프로젝트별 기록([0279017c](https://github.com/bugsterran/sidereus/commit/0279017c)), 7일 안에 세 번째 "no-fit" 이 오면 파이프라인 초안 제안([ceee702d](https://github.com/bugsterran/sidereus/commit/ceee702d), [#16](https://github.com/bugsterran/sidereus/issues/16)).

측정: 이슈가 답하려던 질문, 즉 잊어서 안 쓴 경우와 맞는 파이프라인이 정말 없는 경우의 비율은 아직 세지 않았다.

판정: 미정.

다음: 실제 선언이 몇 주 쌓이면 프로젝트별 수를 보고 초안 제안을 남길지 정한다.

## 8. 강제 게이트는 잡는 것보다 비용이 더 큰가

가설: 강제 게이트(strict 모드, 커밋 전 필수 게이트)는 더하는 시간과 막는 작업만큼 충분히 잡아낸다.

해 본 것: Caught, Blocked, Overridden 카운터와 게이트 시간 집계를 [c4b44c59](https://github.com/bugsterran/sidereus/commit/c4b44c59) 에서 넣었다.

측정: 2026-10-31 기준 7일간 첫 라이브 수치(n=1): Caught 10, Blocked 14, Overridden 5, unknown 9. Paused 는 아직 재지 않았다. 재개 기록은 그 커밋부터 남는다.

판정: 미정.

다음: 4~8주 동안 Caught 와 Blocked·Overridden 을 비교하고 게이트 총 시간을 센다.
