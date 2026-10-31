# 훅

[English](HOOKS.md) · **한국어**

`hooks/` 의 Claude Code 훅은 메일박스 메일과 안내를 세션에 건넨다. `ext-hooks/` 의 외부 CLI 훅은 다른 CLI 의 상태를
알려, 그 세션이 Claude 세션 옆에 보이게 한다. 함께 보기: [CONFIG](CONFIG.ko.md),
[`ext-hooks/README.md`](../ext-hooks/README.md).

모든 훅은 혼자 도는 표준 라이브러리 Python 3.9 이고 두 규칙을 지킨다.

- ⚠세션을 가두지 않는다. 오류, 시간 초과, 예산 초과는 모두 빈 stdout 으로 0 종료한다.
- ⚠메타데이터만. 예외는 시데레우스 전달 하나다.

## Claude Code 훅

| 스크립트 | 이벤트(matcher), 시간 제한 | 하는 일 |
|---|---|---|
| `mailbox_stop.py` | `Stop`, 5초 | 턴이 끝날 때 새 메일과 전달을 건넨다 |
| `mailbox_wake.py` | `Stop`, `SessionStart` (`clear\|resume`), `asyncRewake`, 6시간 | 턴이 끝나면(그리고 `/clear`·재개 직후) 뒤에서 기다리다 새 메일이 오면 쉬고 있는 세션을 깨운다 (Monitor·watch.sh 불필요) |
| `invite_notice.py` | `SessionStart`, `UserPromptSubmit`, 10초 | 방 초대, 미등록 아이디, 깨우기 안내 |
| `pipelines_brief.py` | `SessionStart`, `UserPromptSubmit`, 5초 | 프로젝트의 파이프라인 목록 |
| `file_peers_notice.py` | `PreToolUse`(`Edit\|Write\|MultiEdit\|NotebookEdit`), 2초 | 다른 실행 중 세션이 이 파일을 고쳤음 |
| `pl_mark.py` | `PreToolUse`(`Task\|Agent\|SendMessage`, `Bash`), 5초 | 메인 에이전트의 파이프라인 단계 기록 |
| `pl_flow.py` | `PreToolUse`(`Task\|Agent\|SendMessage`, `Bash`, `Edit\|Write\|MultiEdit\|NotebookEdit`), `PostToolUse`(`Task\|Agent\|SendMessage`), 5초 | 태그 붙은 실행을 단계 순서대로 묶고 다음 단계를 넘겨준다 |
| `ev_hook.py` | `PreToolUse`, `PostToolUse`, `PostToolUseFailure`(모두 `Bash`), 3초 | 테스트·빌드·체크·린트 실행을 하네스 증거로 기록한다 |
| `perm_mark.py` | `PermissionRequest` + `Notification`(`permission_prompt`), 5초 | 세션이 권한 확인 창에서 기다리는 중임을 표시한다 |
| `room_auto.py` | `SessionStart` | `room-map.json` 의 경로별 방에 들어간다(선택. 플러그인에는 없다) |

플러그인(`scripts/build_plugin.py`)이 `room_auto.py` 를 뺀 9개를 모두 등록한다(`hooks/pyrun.sh` 경유라 Windows 에서는 Git Bash 가 필요하다). `python3 -m sidereus setup-claude`(Windows: `py -m sidereus setup-claude`)는 이 클론 경로로
같은 훅 9개를 출력만 하고, 설정 파일은 쓰지 않는다. ⚠플러그인과 수동 등록 중 하나만 쓴다(둘 다 하면 훅이 모두 두 번 돈다).

⚠도구 호출을 거부하는 훅은 `pl_mark.py`, `pl_flow.py` 뿐이고(플러그인·수동 모두), `.claude/pipelines/*.json` 이 있는 프로젝트에서만이다
(아래 참고). 나머지 훅은 문맥을 더하거나 표시 파일을 쓸 뿐이다.

### Claude Code Stop 훅

`mailbox_stop.py` 는 `watch.sh` 를 돌리지 않는 세션을 위한 것이다. 메일이 있으면 `{"decision":"block","reason":"..."}`
를 출력해서 모델이 쉬기 전에 편지함을 읽게 한다. reason 에는 개수와 보낸 사람(`bob(DM)`, `bob(방 r1)`)만 들어간다.

| 검사 | 규칙 |
|---|---|
| 아이디 | `identity.json[cwd]` 의 정확한 키만. 없으면 조용히 |
| 감시기 | `.watch-<id>.pid` 에 살아 있는 PID 가 있으면 조용히(Monitor 가 전한다) |
| 후보 | 그 아이디 앞 DM, 그 아이디가 속한 방의 남이 쓴 글 |
| 기준 시각 | max(`read-<id>.cursor`, 이 세션에 마지막으로 보여 준 t, 지금 − 6시간) |
| ack 안 됨 | `acks.jsonl` 에 그 아이디의 `kind:"ack"` 가 없음 |

- ⚠`last_t` 보다 새 메시지가 있을 때만 막으므로 `stop_hook_active` 재시도는 0 으로 끝난다.
- 입력에 `stop_hook_active` 가 있으면 두 단계다. 막을 때 `last_t`/`relay_t` 는 그대로 두고 새 값을 `pending` 에 둔다.
  다음 Stop 에서 `stop_hook_active` 가 참이면 확정하고(`hooked` 행도 이때 쓴다), 거짓이면 버린다 — 다른 Stop 훅의
  `continue:false` 가 `decision:block` 을 이겨 reason 이 모델에 닿지 않았으므로 같은 메일로 다시 막는다.
  최소 한 번 전달: 확정은 한 턴 늦고, Esc 로 끊으면 다시 갈 수 있다. 키가 없으면(다른 CLI) 바로 확정한다.
- ⚠`bus.jsonl` 끝 512 KB, `acks.jsonl` 끝 256 KB 만 읽고 0.25초를 넘으면 그만둔다. ★3 MB 버스에서 약 40 ms.
- 상태: `.stop-hook/<session_id>.json`(`last_t`, `relay_t`, 있으면 `pending` = `{last_t, relay_t, receipts, at}`). 7일 지나면 지운다.
- `mailbox_wake.py` 는 max(확정, `pending`) 보다 새 메일에만 깨운다. 깨울 때는 확정 커서 위 전부를 보여 주고 `pending` 을 지운다.

전달은 `kind:"relay"`, `idSrc:"viewer"` 인 버스 행, 곧 사람이 시데레우스에서 보낸 지시다. 본문째 건넨다.

| 검사 | 규칙 |
|---|---|
| 대상 | `to` 가 그 아이디, `sid` 가 없거나 이 `session_id` 와 같음 |
| 기준 시각 | max(`relay_t`, 지금 − 24시간) |
| 안 본 것 | 그 글의 `hooked` 나 `ack` 가 없음. ⚠`delivered` 는 치지 않는다. 감시기가 1초 안에 쓰고 알리기만 한다. |
| 상한 | 한 번에 오래된 것 3개, 합계 24000자. 나머지는 기다리고 자르지 않는다. 20000자(`DM_MAX`)를 넘는 본문은 «… (잘림 — mailbox_inbox 로 전문 확인, id N)» 로 끝난다. |

- 감시기가 살아 있어도 건넨다. 쓰는 순서는 `relay_t`(두 단계면 `pending`), stdout, 그다음 `acks.jsonl` 의 `hooked` 행이다(두 단계면 확정하는 Stop 에서).
- ⚠다른 출처의 `kind:"relay"` 행은 일반 메일이다.
- `POST /api/dm` 은 뷰어의 `Origin` 이 있어야 `relay:true` 를 받고, 아니면 403 이다. ⚠에이전트의 무심한 `curl` 은
  막지만, 같은 사용자로 도는 코드는 헤더를 꾸미거나 `bus.jsonl` 에 직접 쓸 수 있다.

```json
{ "hooks": { "Stop": [ { "hooks": [ { "type": "command", "timeout": 5,
  "command": "<PYTHON> <MAILBOX_CODE_DIR>/hooks/mailbox_stop.py" } ] } ] } }
```

이 예시와 `ext-hooks/*.json` 의 `<PYTHON>`: macOS 는 `/usr/bin/python3`, Windows 는 `py -3`(또는 `python.exe` 전체 경로).

테스트: `/usr/bin/python3 -m unittest tests.test_mailbox_stop -v`(Windows: `py -m unittest ...`).

### invite_notice.py

할 말이 있을 때만 출력한다. 새 방 초대, 미등록 아이디, 깨우기 안내(뒤의 둘은 `SessionStart` 에서만)다. 깨우기 안내는
한 줄 — 새 메일은 `mailbox_wake` 가 깨우니 Monitor·watch.sh 를 띄우지 말고 깨워지면 `mailbox_inbox` 로 읽으라고 한다.

- 설정은 `config.local.json` 의 `mailbox_watch = {"mode": "on"|"off", "projects": {"<절대 경로>": "on"|"off"}}`.
  없으면 켜짐이고, 맞는 프로젝트 경로 중 가장 긴 것이 이긴다.
- 꺼짐은 깨우기 안내만 뺀다. ⚠«감시가 꺼져 있습니다» 경고는 없다 — Monitor 가 정책상 꺼져 그 상태가 정상이다.
- `SessionStart` 에 세션 id -> Claude 설정 폴더를 `acct/<session_id>` 에 기록한다(메타데이터만, 30일 뒤 정리). 뷰어가 계정을 구분하는 데 쓴다.

### pipelines_brief.py

`SessionStart` 에 `<cwd>/.claude/pipelines/*.json` 마다 한 줄과 실행 방법을 붙인다. 최대 2048바이트. «적용» 설정
(`pipeline_apply`)이 자동·먼저 묻기를 고르거나 끈다. ⚠`task` 와 `rules` 내용은 넣지 않는다.
`UserPromptSubmit` 에서는 세션이 마지막으로 받은 뒤 파이프라인 이름이나 단계 제목이 바뀐 경우에만 다시 보낸다
(해시는 `plbrief/<session_id>`).
이 훅과 `pl_mark.py`·`pl_flow.py` 는 cwd 밖에서 세션이 작업하는 프로젝트의 파이프라인도 읽는다. cwd 에 파이프라인이 있으면 cwd 만 본다(대화 기록 끝부분의 Bash `cd`
대상·기록의 `cwd` 의 git 루트, 읽기만 한 경로는 제외, `plbrief/<session_id>.dirs` 에 캐시. 메일박스 폴더는 제외). `pl_flow.py` 는 cwd 에 파이프라인이 있어도 찾는다. 같은 이름 `<name>.json` 이 여럿이면 단계 제목·단계 에이전트(`subagent_type`)가 맞는 쪽을 골라 실행(`proj`)에 기억한다.

### file_peers_notice.py

다른 실행 중 세션이 최근 30분 안에 그 파일을 고쳤으면 `GET /api/agent/file` 로 얻은 sid8, 프로젝트, 몇 분 전, 커밋 안 됨
여부를 붙인다. (세션, 파일, 상대)마다 10분에 한 번. ⚠알리기만 한다. 뷰어가 꺼져 있으면 조용하다.

### pl_mark.py

Bash 설명이 `[pl:<name>/<stage>]` 로 시작하면 `plmark/<session_id>.json` 을 쓰고, `[pl:-]` 나 태그 붙은
Agent/Task/SendMessage 는 지운다. 파이프라인, 단계, 시각, cwd 만 저장한다. 파이프라인이 있는 프로젝트에서
`[pl:` 태그 없는 Agent/Task 는 매번 «태그를 붙이거나 `[pl:-]`» 이유로 거절된다.

### pl_flow.py

태그 붙은 파이프라인 실행을 `plmark/<session_id>.runs.json` 에 기록한다(현재 단계, 끝난 단계, 진행 중 조각 수, 반복 횟수,
시각. 설명·출력은 저장하지 않는다). ⚠`<session_id>.json` 은 `pl_mark.py` 것이라 쓰지 않는다.

- Pre: 태그가 실행을 연다(열린 실행이 없거나, 끝났거나, 6시간 넘게 멈춘 경우). 아직 안 돈 단계를 건너뛰는 앞쪽 점프는
  건너뛴 단계마다 한 번 거절된다(`onlyOnJump` 단계는 제외). 다시 보내면 통과한다. 앞 단계는 늘 통과하고, 현재 단계의
  `onFail.goto` 로 돌아가면 반복 한 번으로 세고 끝나면 그 단계(또는 `onFail.then`)로 돌아온다.
- Pre: 태그 붙은 Agent/Task 는 단계 에이전트를 `subagent_type` 으로, 단계 모델을 `model` 로 넘겨야 하고 아니면 거절된다
  (단계에 모델이 적혀 있으면 `model` 을 빼도 불일치로 본다. `inherit`, `main` 단계, 단계 에이전트가 설치되지 않아 `general-purpose` 를 받는 경우는 예외).
  Bash 설명 `[pl-model:<name>/<stage>=<model>]` · `[pl-agent:<name>/<stage>=<agent>]` 로 그 실행의 그 단계에만 다른
  모델·에이전트를 선언한다.
- Post: 단계의 마지막 조각이 돌아오면 `PASS → next: [pl:…] · agent · model · skill · gate` 를, `onFail` 이 있는 단계면
  FAIL 반복 줄을 붙인다. 백그라운드 호출은 «끝나면» 으로 말하고, 그 호출이 받는 유일한 Post 에서 진행 중 조각 수를
  하나 줄인다(단계를 끝냄으로 표시하지는 않는다). 마지막 단계 뒤엔 실행을 닫고 `after` 를 알린다.
- 실행이 열려 있는데 메인 세션의 Bash 에 태그가 없으면, 단계 작업엔 `[pl:<name>/<stage>]`, 그 밖의 일엔 `[pl:-]` 를
  붙이라는 알림(실행 이름·단계만)을 문맥에 더한다. 거부하지 않으며 실행마다 10분에 한 번.
- Bash 설명의 `[pl-none:<category>]`(`small-fix` · `no-fit` · `explore` · `other`)는 이 세션의 일이 파이프라인 밖이라고
  선언한다. `plmark/<session_id>.none.json` 에는 분류와 시각만 남고 이유 글은 남지 않는다. 모르는 분류는 목록과 함께 거부한다.
  선언마다 `plmark/none-log.jsonl` 에도 한 줄 붙는다(프로젝트 경로·분류·시각만). 90일 지난 줄은 지우고, 256 KB 를 넘으면
  최근 절반만 남긴다.
  선언도 열린 실행도 없으면, 파이프라인이 있는 프로젝트에서 메인 세션의 첫 Edit/Write 나 태그 없는 `git commit` 을 목록과 함께
  한 번 거부하고 다시 하면 통과한다. ⚠수동 등록이면 `pl_flow.py` 에 `Edit|Write|MultiEdit|NotebookEdit` 매처가 필요하다(`setup-claude` 다시 실행).
- 엄격 모드(프로젝트별 선택): `.claude/pipelines/_policy.json` 이 `{"enforce": "writes"}` 이면, 열린 실행이 없을 때
  Edit/Write/MultiEdit/NotebookEdit 와 태그 없는 `git commit` 을 매번 거부하고 파이프라인마다 이름과 `use` 한 줄을 보여 준다.
  서브에이전트는 세션에 끝나지 않은 실행이 하나도 없을 때만 거부한다. `[pl-none:explore]` 는 받지만 수정은 풀지 않고, 다른 분류는
  `[pl:quick-fix/수정]` 안내와 함께 거부한다. 파일이 없거나 다른 값이면 지금처럼 한 번만 거부하고, «Apply» 를 끄면 건너뛴다.
- 보안 수정 잠금(`_policy.json` 불필요): `<data dir>/plreq.json` 에 저장소 X 의 `security-fix` 요청이 24시간 안에 보내졌고
  `stop`/`closed` 도, 요청 뒤 시작해 리뷰 단계가 끝난 받는 세션의 실행도 없으면, X(파일 또는 cwd 의 git 루트) 안의 수정·`git commit`·셸 쓰기를 거부한다. 이 세션에 `security-fix`
  실행이 열려 있거나 끝난 지 15분이 안 됐으면 통과한다. 거부 문구에 저장소·요청 시각과 `[pl:security-fix/수정]` 안내가 있고,
  주인은 요청 줄의 «Stop» 으로 풀 수 있다. `[pl-none]`·«Apply» 끄기로는 풀리지 않는다. 읽기 도구는 통과, 읽기 오류는 통과(fail-open).
- 한 프로젝트에서 7일 안에 `[pl-none:no-fit]` 이 세 번째로 선언되면, 사용자에게 이 일에 맞는 파이프라인 초안을 제안하고 동의한 뒤에만
  `.claude/pipelines/<name>.json` 을 쓰라는 문맥을 더한다(횟수·프로젝트 경로만, 거부하지 않음). 프로젝트마다 7일에 한 번.
- 메인의 `git commit` 은 이 세션에서 그 프로젝트의 열린 실행을 닫는다. 설명이 `[pl:-]` 인 커밋은 아무것도 닫지 않고,
  `[pl:<name>/<stage>]` 태그가 붙은 커밋은 `<name>` 만 닫는다.
- 실행이 끝나면(마지막 단계 · `[pl-end:]` · 메인의 `git commit`) `<data dir>/eval/<repo key>/seeds.json` 이 있을 때만
  `scripts/pl_eval.py score --auto` 를 떼어 띄운다(기다리지 않고 출력 없음). 오류는 삼키고 호출을 막지 않는다.
- «적용» 이 꺼져 있거나, 파이프라인 파일이 없거나 깨졌거나, 단계 제목이 맞지 않으면 조용하다.

#### 가드 (`hooks/pl_guard.py`, Claude Code 만)

파이프라인 파일에 `"guards": {"requireGates": ["<단계>", …], "maxLoopBacks": 1..10}` 를 둘 수 있다(둘 다 선택.
검증기는 없는 단계, `gate` 가 채점되지 않는 단계, 범위 밖 max 를 거절한다).

- 채점되는 게이트 → 증거 모드: `check.sh --fast` → `fast`, `--full` → `full`, `arch_checks.py --verify
  --category security` → `checks-security`.
- 이 세션에 그 프로젝트의 열린 실행이 있고 `requireGates` 가 있으면 `git commit`(메인·서브에이전트)을 거절한다. 통과
  조건: 나열된 단계마다 완료(건너뜀 아님) + 그 단계의 마지막 회차 시작 이후 `evidence.jsonl` 에 그 모드의 `rc=0` 줄이
  있고 그 뒤에 실패 줄이 없을 것. 거절 이유에 빠진 단계가 나온다.
- `requireGates` 단계의 `[pl-skip:<name>/<stage>]` 는 거절한다.
- 되돌림이 `maxLoopBacks` 번에 닿으면 다음 되돌림 디스패치를 거절하고, FAIL 안내는
  «loop budget n reached: stop and report» 가 된다.
- ⚠실패 시 통과: 가드 모듈이 없거나, 파이프라인이 깨졌거나, 증거를 못 읽으면 막지 않는다. 읽는 것은 게이트·제목·rc·
  모드·시각뿐이다.

#### 실패 시 막기 (선택, Claude Code 2.1.295+)

가드도 다른 훅처럼 실패 시 통과한다. `pl_flow.py` 가 뜨지 못하거나 시간 초과(5초)되면 열린 실행의 `git commit` 이 가드
없이 통과한다. Claude Code 2.1.295+ 는 command·HTTP 훅 항목에 `"onFailure": "block"` 을 받는다. 그러면 훅이 뜨지 못하거나,
시간 초과되거나, 예상 밖 코드로 끝날 때 도구 호출을 통과시키지 않고 막는다.

플러그인에서는 꺼져 있다. `pl_flow.py` 는 `Task|Agent|SendMessage`·`Bash`·`Edit|Write|MultiEdit|NotebookEdit`
호출 앞(`PreToolUse`)에서 돌고, `Task|Agent|SendMessage` 뒤(`PostToolUse`)에서도 돈다. 켜려면 설정의 `pl_flow.py`
항목마다, 두 이벤트 모두에 이 키를 넣는다(플러그인 사용자는 `python3 -m sidereus setup-claude` 의 수동 블록을 자기
설정에 넣는다. ⚠플러그인과 수동 블록 중 하나만 쓴다).

```json
{ "type": "command", "command": "python3 /path/to/sidereus/hooks/pl_flow.py", "timeout": 5, "onFailure": "block" }
```

- ⚠대가: `pl_flow.py` 는 Task·Agent·SendMessage·Bash·Edit 계열 호출마다 앞에서 돈다(Task·Agent·SendMessage 는 뒤에서도).
  인터프리터가 깨지거나 훅이 시간 초과되면 커밋만이 아니라 그런 호출이 모두 막힌다.
- `pl_flow.py` 안의 오류는 지금처럼 잡아서 0 종료한다. `onFailure` 는 뜨지 못함·시간 초과·예상 밖 종료 코드만 다룬다.
- ★2026-10-29 실측(`claude -p`, `PreToolUse` Bash 시험 훅, 시간 제한 1초), 2.1.312: 시간 초과 → 막힘,
  `PreToolUse:Bash hook error: [<command>]: timed out; blocking because onFailure is "block"`. exit 1 → 막힘,
  `... failed; blocking because onFailure is "block"`. exit 2(정상 거부) → 전처럼 훅의 stderr 이유로 막힘. 키 없이 같은
  시간 초과 → 도구가 돌았다. 그래서 가드 실패는 게이트 거부와 다른 문구로 보인다.
- ★2.1.294(옵션 이전): 키를 무시하고 설정 오류도 없다. 시간 초과·exit 1 모두 도구가 돈다.

### ev_hook.py

걸린 Bash 실행마다 `evidence.jsonl` 에 한 줄을 붙인다. `scripts/check.sh` 가 없는 프로젝트에서도 하네스 «결과» 가 찬다.
한 줄: `mode`(`hook-<종류>` 또는 `gate-<종류>`), 저장소, 짧은 커밋, dirty, `rc`, 단계 하나(종류, rc, 초).

| 걸리는 명령(앞의 `cd X &&` 는 허용) | 종류 |
|---|---|
| `./gradlew`/`gradle` `test`·`build`·`check`, `mvn test`·`verify` | test · build · check |
| `npm`/`pnpm`/`yarn` (`run`) `test`·`build`·`lint` | test · build · lint |
| `pytest`, `python -m pytest`, `go test`, `cargo test`·`build` | test · build |
| `<repo>/.claude/pipelines/*.json` 의 `gate` 문자열(공백 정규화) | `gate-*`, 종류 단어가 없으면 단계 `gate` |
| `gh run watch`/`view` `<id> --exit-status`(`-R`/`--repo` 없이) | 종류 `ci` 줄: `rc`, 저장소, 짧은 커밋만 |

- 건너뜀: `|`, `;`, 명령 뒤의 `&&`, 끝의 `&`, `--watch*`, `--continuous`, `-t`, 모든 `check.sh`(자기 줄을 직접 쓴다),
  `run_in_background`, 중단된 실행.
- `rc`: `PostToolUse` 면 0, `PostToolUseFailure` 면 맨 앞 «Exit code N» 의 숫자, 없으면 1.
- ⚠메타데이터만: 명령·stdout/stderr·오류 문구는 저장하지 않는다. 초는 `PreToolUse` 가 쓴 `evstart/<tool_use_id>` 로
  잰다(없으면 0, 1시간 지난 것은 지운다).
- `SIDEREUS_EVIDENCE` 로 파일을 바꿀 수 있다(`check.sh` 와 같다). ★걸리지 않는 명령은 약 40ms.

### perm_mark.py

Claude Code 가 권한 확인 창을 띄우면 `permwait/<session_id>.json`(`sid`, 시각)을 쓴다. 이 시각이 세션의 마지막
트랜스크립트 활동보다 새로우면 시데레우스가 «승인 대기» 로 보여 준다. `PermissionRequest` 는 창이 뜰 때 바로 오고,
`Notification` 등록은 예비다. ⚠Claude Code 는 창이 뜨고 약 6초 뒤에 알림을
보낸다(그 전에 답하면 보내지 않는다). 메시지·제목·도구 입력은 남기지 않고, 아무것도 출력하지 않는다.

표시 파일 형식: 메인은 `permwait/<sid>.json` = `{sid, t[, tool]}`, 서브에이전트 이벤트(`agent_id` 있음)는
`permwait/<sid>.<agent_id>.json` = `{sid, t, k, aid[, tool]}`(`k` = `req` | `perm` | `elicit`). `tool` 은
`PermissionRequest` 의 `tool_name` 만 쓰고, 15초 안에 온 메인 `Notification` 은 그 값을 이어받는다. 서브 표시는 그
에이전트 자신의 활동과 비교하므로 메인 줄 상태와 관계없이 «서브에이전트 승인 대기» 가 뜬다. 7일 지난 서브 표시는
다음 기록 때 지운다. 예전 `{sid, t}` 표시도 그대로 읽는다.

## 다른 훅과 같이 쓸 때

Claude Code 는 한 이벤트의 훅을 모두 돌린다. 출력은 합쳐지고, `PreToolUse` 훅 하나라도 `deny` 하면 그것이 이긴다.

| 훅 | 할 수 있는 일 | 같은 이벤트의 다른 훅이 이기거나 같이 막을 때 | 끄는 법 |
|---|---|---|---|
| `mailbox_stop.py` | 멈춤 차단(메일 개수·보낸 사람, 전달은 본문) | 다른 훅의 `continue:false`: [두 단계](#claude-code-stop-훅) 참고, 다음 멈춤에 같은 메일이 다시 온다. 같이 막으면 두 reason 이 모두 모델에 간다 | 설정에서 뺀다(`identity.json` 에 아이디가 없는 cwd 에서는 조용) |
| `mailbox_wake.py` | 쉬는 세션 깨우기(exit 2) | 영향 없음. 뒤에서 기다린다(`claude -p`/SDK 는 이 훅을 기다리므로 바로 끝낸다. SDK 로 띄운 세션은 쉬는 중에 깨우지 않고 다음 멈춤에 `mailbox_stop.py` 로 받는다) | 설정에서 뺀다(cwd 규칙 같음) |
| `invite_notice.py` | 문맥 추가 | 프롬프트가 막히면 그 줄은 사라진다. 이미 보인 초대는 프롬프트마다 반복하지 않고 다음 `SessionStart` 에만 다시 보인다 | `mailbox_watch` off 는 깨우기 안내만 끈다. `identity-skip.json` 은 미등록 안내만 끈다 |
| `pipelines_brief.py` | 문맥 추가 | 프롬프트가 막히면 목록은 사라진다. 다음 `SessionStart` 나 파이프라인 변경 때 다시 보낸다 | `pipeline_apply` off |
| `file_peers_notice.py` | 문맥 추가 | 편집이 거부돼도 알린 것으로 친다(파일·상대별 10분) | 설정에서 뺀다(뷰어가 꺼져 있으면 조용) |
| `pl_mark.py` | 도구 거부(태그 없는 Agent/Task), 표시 기록 | 이 훅의 거부가 허용을 이긴다. 다른 훅이 거부해도 표시는 이미 쓰였거나 지워졌다 | `pipeline_apply` off 면 거부하지 않는다. 표시는 계속 기록한다 |
| `pl_flow.py` | 도구 거부(단계 순서·에이전트/모델·태그), 문맥 추가(Post) | 이 훅의 거부가 허용을 이긴다. 다른 훅이 디스패치를 거부해도 실행은 이미 그 단계로 넘어갔고, 다시 디스패치하면 통과한다 | `pipeline_apply` off |
| `ev_hook.py` | 없음, 기록만 | 거부된 실행은 행을 남기지 않는다(`evstart` 표시는 1시간 뒤 지운다) | 설정에서 뺀다(`SIDEREUS_EVIDENCE` 는 파일 위치만 바꾼다) |
| `perm_mark.py` | 없음, 기록만 | 영향 없음 | 설정에서 뺀다 |
| `room_auto.py`(선택) | 문맥 추가(새로 들어갈 때 한 줄) | 영향 없음 | `room-map.json` 에 그 경로를 두지 않는다 |

★ 충돌 없음을 실제로 확인(2026-10-11): oh-my-claudecode 5.6.2, superpowers 7.0.0, hookify 0.1.0, ralph-wiggum 1.0.0, security-guidance 2.0.0, claude-mem 13.35.0 — 날짜가 붙은 관찰이지 호환 보증이 아니다.

**충돌 신고.** 이슈에 붙일 것: `/plugin` 설치 목록, `~/.claude/settings.json` 과 프로젝트 `.claude/settings.json` 의 `hooks` 블록
(이벤트·matcher·명령만, `env` 값이나 비밀 정보는 빼고, 훅 명령 안의 토큰과 경로도 가린다), Claude Code 버전(`claude --version`), Sidereus 커밋(`git rev-parse --short HEAD`).

## 진단 (설정)

<details><summary>보여 주는 것과 «silent» 판정 기준</summary>

설정 › «진단»(`GET /api/diag`, 기능 `diag`)은 모든 계정의 설정·설치된 플러그인·알려진 프로젝트를 읽어 보여 준다:
Sidereus 훅과 같은 이벤트에 걸린 훅(출처 plugin/user/project·이름·계정·matcher·스크립트 이름) · 출력이 Claude Code 에
읽히지 않는 플러그인 훅 · 설치된 플러그인 버전 · `CLAUDE.md` 가 `AGENTS.md` 를 가리는 프로젝트(둘 다 있고, `CLAUDE.md` 가
`AGENTS.md` 로의 링크도 아니고 앞 4 KB 에 `@AGENTS.md` 도 없을 때). 읽기 전용이며 아무것도 고치지 않는다.

⚠«조용함»은 정적 추정이다: 스크립트(≤ 64 KB, 플러그인 `installPath` 아래만)는 읽기만 하고 실행하지 않는다.
stdout 으로 나가는 `JSON.stringify`/`json.dumps` 객체의 키를 아래 표와 비교한다.

| 이벤트 | Claude Code 가 읽는 필드 |
|---|---|
| 모든 이벤트 | `continue`, `stopReason`, `suppressOutput`, `systemMessage` |
| `PreToolUse` | `hookSpecificOutput.{permissionDecision, permissionDecisionReason, updatedInput, additionalContext}`, 예전 `decision`, `reason` |
| `PostToolUse` | `decision`, `reason`, `hookSpecificOutput.{additionalContext, updatedMCPToolOutput}` |
| `UserPromptSubmit` | `decision`, `reason`, `hookSpecificOutput.additionalContext` |
| `Stop`, `SubagentStop` | `decision`, `reason` |
| `SessionStart` | `hookSpecificOutput.additionalContext` |
| `PermissionRequest` | `hookSpecificOutput.decision.{behavior, updatedInput, message, interrupt}` |

판정: **silent** = JSON 을 내보내고, 읽히지 않는 키가 하나 이상이며, 나머지는 효과 없는 키(`continue:true`, `suppressOutput`)뿐이고
exit 2 경로가 없음 · **partial** = 읽히는 키와 안 읽히는 키가 섞임 · **ok** · **unknown** = 바이너리·경로를 못 찾음·JSON 출력 없음
(표에 없는 이벤트는 항상 unknown).

</details>

## 외부 CLI 훅

CLI 가 `ext-hooks/ext_hook.py --platform <key>` 를 실행하면, 스크립트가 stdin 의 이벤트를 표준 이름으로 바꿔 `/api/hook`
에 POST 한다. 뷰어는 `(platform, session_id)` 마다 마지막 이벤트를 행으로 보여 준다.

`--platform` 은 `EXT_PLAT`(`sidereus/ext_store.py`)의 키여야 한다. `gemini`, `codex`, `copilot`, `cursor`, `cline`,
`windsurf`, `warp`, `trae`, `zed`, `openrouter`, `grok`, `deepseek`, `qwen`, `kimi`, `mistral`, `ollama`, `perplexity`,
`huggingface`, `meta`. ⚠`claude` 는 없다. Claude 세션은 대화 기록에서 읽는다.

| 이벤트 | 상태 | Gemini 이름 | Codex 이름 | Cursor 이름 | Copilot 이름 |
|---|---|---|---|---|---|
| `SessionStart` | `wait` | 같음 | 같음 | `sessionStart` | 같음 |
| `UserPromptSubmit` | `think` | `BeforeAgent` | 같음 | `beforeSubmitPrompt` | 같음 |
| `PreToolUse` | `tool` | `BeforeTool` | 같음 | `preToolUse` | 같음 |
| `PostToolUse` | `think` | `AfterTool` | 같음 | `postToolUse`, `postToolUseFailure` | 같음 |
| `Stop` | `wait` | `AfterAgent` | `Stop`, `Interrupt` | `stop` | 같음 |
| `Notification` | `ask`(막힘) | 같음 | `PermissionRequest` | 없음 | `PermissionRequest` |
| `SessionEnd` | 행 삭제 | 같음 | 같음 | `sessionEnd` | 같음 |

- 나머지 플랫폼은 Codex 변환을 쓴다. ⚠Gemini, Codex, Cursor, Copilot 만 확인했다. 이름이 다르면 `--event <이름>` 을 넘긴다.
- 막힘 표시와 «나를 기다림» 배지는 CLI 의 다음 이벤트, `SessionEnd`, 프로세스 종료(pid)로만 사라진다. 시간으로는 지우지 않는다. 그 밖에 24시간(`EXT_TTL_S`) 조용한 행은 지운다.
  행은 재시작해도 남는다(`ext-sessions.json`).
- 훅 행에는 대화 기록, 비용, 컨텍스트, git 정보와 이어 하기 칩이 없다. 모델 이름은 20자에서 자른다.

`ext_hook.py` 옵션: `--platform`(필수), `--event`, `--url` 또는 `SIDEREUS_HOOK_URL`(기본 포트 `SIDEREUS_PORT` > 설정 `port` >
8799), `--dry-run`(본문을 stderr 로), `MAILBOX_DIR`(로그 위치). `session_id`, `cwd`, `transcript_path`, `model`,
`tool_name`, `turn_id` 는 비어 있지 않은 문자열일 때만 넘기고(`session_id` 가 없으면 `conversation_id`, `cwd` 가 없으면
`workspace_roots` 의 첫 절대 경로), `SIDEREUS_PARENT_SID` 나 `CLAUDE_CODE_SESSION_ID` 가 있으면
`parent` 로 넘긴다. 서버는 `session_id` 를 요구하고 본문을 1 MB 로 제한한다.
`--url`/`SIDEREUS_HOOK_URL` 의 스킴이 `http`·`https` 가 아니면 거절한다(로그만 남기고 보내지 않음).

⚠stdout 은 비워 둔다(CLI 가 제어 JSON 으로 읽는다). 종료 코드는 늘 0 이고 뷰어가 꺼져 있어도 최대 2초만 기다린다.
실패는 `ext-hooks/.ext-hook.log`(200 KB 상한)에 남긴다. `bash ext-hooks/demo.sh` 는 가짜 행 세 개를 만든다. 끝나면
반드시 `demo.sh clean` 을 돌린다.

### 자동 연결

설정 › «진단» › «CLI 훅» 과 첫 화면에, 설치돼 있지만 시데레우스 훅이 없는 CLI 마다 한 줄이 뜬다. 항목이 모두 있으면
아무것도 뜨지 않는다. «나중에» 는 CLI 마다 숨긴다.

- 찾는 것: Cursor(`cursor-agent`, 또는 `~/.cursor` 가 있을 때 `agent`) → `~/.cursor/hooks.json` · Codex(`codex`) →
  `$CODEX_HOME/hooks.json` · Gemini(`gemini`) → 그 `settings.json` · Copilot(`copilot`) →
  `$COPILOT_HOME/hooks/sidereus.json`(기본 `~/.copilot`, 시데레우스 전용 파일이라 없으면 만든다). 설치됨 = `PATH` 에 있거나 설정 폴더가 있다.
- «연결» 은 diff 를 보여 주고 확인한 뒤에만 쓴다. 예시 파일의 항목 중 없는 것만 더한다(`<PYTHON>`, `<MAILBOX_CODE_DIR>`
  는 채워 넣는다). 사용자 훅 항목은 순서 그대로 남는다(`hooks` 값은 다시 직렬화되므로 서식은 바뀔 수 있다).
  그 밖의 최상위 키는 한 바이트도 바뀌지 않는다. Codex·Gemini 는 이벤트마다 새 그룹 하나를 붙이고
  기존 그룹은 고치지 않는다. Gemini 는 `hooksConfig.enabled: true` 도 켠다.
- 쓰기 전에 원본을 `<DATA_DIR>/tool-trash/<ts>/<plat>-<file>` 로 복사한다. 실패하면 원본은 그대로다. 다시 «연결» 해도
  바뀌는 것이 없다.
- ⚠심볼릭 링크인 훅 파일은 거부한다. 손으로 고친다.
- ⚠이미 열려 있던 CLI 세션은 다시 시작해야 한다. 새로 시작한 세션부터 훅을 읽는다. Codex: 다시 시작한 뒤 `/hooks` 로 새 항목을 승인해야 한다. 승인 전에는 Codex 가 무시한다. 새로 켠 Codex 세션은 첫 메시지를 보낸 뒤에야 보인다(그 전엔 이벤트가 없다. ★Windows, 2026-10-31).
- 아래의 직접 설정도 그대로 쓸 수 있다. 손으로 고친 파일도 같은 방식으로 판정한다.

### Gemini CLI

`ext-hooks/gemini-settings-example.json` 을 `~/.gemini/settings.json`(또는 `$GEMINI_CLI_HOME/.gemini`)에 합치고
`<MAILBOX_CODE_DIR>` 를 바꾼다. 시간 단위는 ms 다. `AfterAgent` 는 `gemini_mail_stop.py` 도 부르는데, 위 Stop 훅과 같은
규칙이고 Gemini 는 `reason` 을 새 프롬프트로 보낸다. 메일박스 MCP 는 `gemini_mailbox_mcp.sh` 가 띄운다.

- 아이디: `identity.json["gemini:<물리 cwd>"]`, 없으면 `<폴더>-gemini`. ⚠`identity.json[cwd]` 는 쓰지 않는다. 같은
  폴더의 Claude 세션 것이라, 그 편지함을 읽으면 Claude 의 메일을 가져간다.
- ⚠아이디는 스크립트에서 정한다. Gemini 는 설정의 `$VAR` 를 불러올 때 펼쳐서 인라인 셸이 `anon` 이 됐다.
- ⚠대화형 `gemini`(와 `/auth`)는 `settings.json` 을 다시 쓰며 훅을 떨어뜨릴 수 있다. `hooks.AfterAgent` 를 다시 본다.
- 신뢰하지 않은 폴더의 `gemini -p` 는 55 로 끝난다(`--skip-trust`). 개인 Google 로그인은 거부된다
  (`IneligibleTierError`, 0.61.0). AI Studio 키를 쓴다.
- ★2026-09-24 끝까지 확인: 한 번 막힘, 편지함, "pong" 답장, ack.

<details><summary>일꾼 모드: 쉬는 Gemini·Codex 가 메일을 기다린다</summary>

일꾼 모드(폴더에 `touch .mail-worker`, 또는 `SIDEREUS_MAIL_WORKER=1`)는 쉬는 Gemini 를 메일 대기 상태로 둔다. 턴이
끝났는데 할 일이 없으면 «`mailbox_wait`, 일 하기, 같은 스레드로 답하기» 로 막는다.

- 라운드마다 `mailbox_wait(timeout_s=3540, round=N)`. `mcpServers.mailbox.timeout` 은 그보다 크게(예: 3600000 ms).
- ⚠사람 없이 돌리려면 `mcpServers.mailbox` 에 `"trust": true` 가 있어야 한다.
- ⚠반복 감지기는 같은 호출 5번에 멈추고(그래서 `round` 를 매번 바꾼다) 30턴 뒤부터 반복을 판단한다. 오래 돌리려면
  일꾼 폴더에 `{"model": {"disableLoopDetection": true}}` 를 둔다.
- ★빈 라운드 하나에 약 $0.024, 한 시간에 한 번. 빈 라운드가 `SIDEREUS_MAIL_WORKER_MAX_IDLE`(3)번 이어지면 쉰다.
- ⚠기다리는 동안 TUI 에 «도구 실행 중» 이 보인다. 멈춘 것이 아니다. ⚠일꾼 폴더가 읽을 수 있는 파일을 정한다.
- Codex(`Stop`, 켜는 법 같음): `[mcp_servers.mailbox]` 에 `tool_timeout_sec = 3600`. `codex exec` 는
  `-c 'mcp_servers.mailbox.default_tools_approval_mode="approve"'` 도 필요하다.
  ★0.163.0(2026-10-20): 연속 8번 막아도 받아들임, 반복 감지기 없음. 메일 → 답장 → 다시 막음 → 빈 라운드
  `MAX_IDLE` 번 뒤 멈춤, `codex exec` 는 0 으로 끝남. 라운드마다 맥락을 다시 보낸다(입력 약 3.3만 토큰, 대부분 캐시).

</details>

`ext-hooks/ask-gemini "task"` 는 Claude 의 Bash 에서 `gemini --skip-trust --approval-mode plan -p` 를 읽기 전용 하위
에이전트로 돌린다. `ASK_GEMINI_TIMEOUT`(600초, 종료 124)이나 `ASK_GEMINI_STALL`(대화 파일이 180초 안 자람, 종료 125)
뒤 끝낸다. 부른 세션의 하위 행으로 보인다(`ext-runs.json`: 200개, 7일).
⚠plan 모드는 `--policy` 로 허용하지 않으면 `web_fetch` 를 막는다. ⚠서브에이전트에서 띄운 실행은 메인 세션 아래에 보인다.

### Cursor CLI

`ext-hooks/cursor-hooks-example.json` 을 `~/.cursor/hooks.json` 또는 `<프로젝트>/.cursor/hooks.json` 으로 복사한다(형식
`{"version":1,"hooks":{"<event>":[{"command":"..."}]}}`). ★macOS, Cursor CLI 2026.10.22 로 확인했다(2026-10-24).

- 이벤트 이름은 camelCase 다. `afterAgentThought`·`afterAgentResponse` 는 모델 글을 담고 있어 보내지 않는다.
- Cursor 는 기본 `cwd` 를 보내지 않는다(도구 이벤트는 `""`). 그래서 폴더는 `workspace_roots` 의 첫 항목이다.
  `session_id` 는 `conversation_id` 와 같다. `user_email`, `tool_input` 은 버린다.
- `stop` 은 토큰 수만 보낸다(`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens` → `usage`)
  와 `generation_id`(→ `gen_id`). 그래서 «오늘»과 타임라인이 턴마다 한 번씩 센다. 데이터 폴더의 `ext-hooktok.json` 에
  7일 동안 남고 `sessionEnd` 뒤에도 유지된다. ⚠`agent -p` 는 훅을 보내지 않으니 헤드리스 실행에는 토큰이 없다.
- ⚠Cursor 는 `before*`/`preToolUse` 훅의 stdout 을 결정으로 읽는다. `ext_hook.py` 는 아무것도 출력하지 않는다.
- ⚠`cursor-agent -p` 는 `beforeSubmitPrompt`/`stop` 을 보내지 않는다. 헤드리스 행은 `sessionEnd` 까지 마지막 상태로 남는다.
- 대화형 순서: `sessionStart`, `beforeSubmitPrompt`, 도구 이벤트, `stop`. `/quit` 은 `sessionEnd` 를 보낸다.

### Copilot CLI

`ext-hooks/copilot-hooks-example.json` 을 `~/.copilot/hooks/sidereus.json`(또는 `$COPILOT_HOME/hooks/`)으로 복사하고
`<PYTHON>`, `<MAILBOX_CODE_DIR>` 를 바꾼다. ★macOS, Copilot CLI 1.0.105 로 확인했다(2026-10-31): 세션 목록과 상태
(`Stop` → 쉬는 중, `SessionEnd` → 끝남). `copilot -p` 는 `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PermissionRequest`, `PostToolUse`, `Stop`, `SessionEnd` 를 보낸다.

- ⚠이벤트 이름은 PascalCase 로만 등록한다. Copilot 은 camelCase 이름도 받는데, 둘 다 등록하면 모든 이벤트가 두 번 온다.
- `PermissionRequest` 는 PascalCase 로 등록해도 camelCase 키(`hookName`, `sessionId`, `toolName`)로 온다.
  `ext_hook.py` 가 그 키도 읽어 행을 막힘으로 표시한다.
- ⚠«연결» 은 `sidereus.json` 만 쓴다. 다른 `~/.copilot/hooks/*.json`, 저장소의 `.github/hooks`, `~/.copilot/settings.json`
  안의 인라인 훅은 보지 않는다. 거기에 같은 훅을 이미 넣었다면 이벤트가 두 번 온다.
- `COPILOT_HOME` 은 뷰어의 환경에서 읽는다. launchd 에는 보통 없으므로 `~/.copilot` 을 쓴다.
- 파이프라인 단계 표시: `PreToolUse` 가 `hooks/pl_mark.py` 와 `hooks/pl_flow.py --platform copilot` 을, `PostToolUse` 가
  `pl_flow.py` 를 실행한다. ★macOS, Copilot CLI 1.0.105 에서 확인(2026-10-31): 셸 도구는 `bash` 이고 인자는 `command`,
  `description`, `mode`, `initial_wait` 이다. `command` 맨 앞이나 `description` 에 `[pl:<파이프라인>/<단계>]` 태그가 있으면
  그 단계에 불이 들어온다.
  - ⚠선언하지 않은 건너뛰기는 막지 않고 건너뜀으로 기록만 한다. 도구 실행 뒤 `[pl-end:]` 인계 문구는 없다.
  - 이전에 이미 연결했다면 «연결» 을 다시 누른다. 빠진 항목 세 개만 덧붙는다.
- 아직 안 한 것: Windows 확인.

### Codex CLI

`ext-hooks/codex-hooks-example.json` 을 `~/.codex/hooks.json` 으로 복사한다. Codex 0.156.1 로 확인했고 시간 단위는 초다.

- ⚠Codex 는 `/hooks` 로 승인하기 전까지 항목을 무시하고, 고칠 때마다 다시 승인해야 한다(해시를 저장한다).
  `--dangerously-bypass-hook-trust` 를 기본으로 쓰지 않는다.
- `PermissionRequest` 는 행을 막힘으로 표시한다. 스크립트가 아무것도 출력하지 않으므로 Codex 는 평소처럼 묻는다.
- 기본: 예시의 `Stop` 은 `gemini_mail_stop.py --platform codex` 를 돌린다 — 메일은 다음 턴이 끝날 때 전달된다.
- 메일 깨우기(`--wake`, **선택 사항**, timeout 5): `~/.codex/hooks.json` 의 그 `Stop` 명령 끝에 `--wake` 를 붙이고
  `/hooks` 로 다시 승인한다. `Stop` 이 분리된 대기 프로세스(`ext-hooks/codex_wake.py`)를 띄우고
  바로 끝난다. 메일이 오면 로컬 Codex app-server 소켓으로 그 세션의 스레드에 턴 하나를 시작한다. 턴 문구는
  «[mailbox] N new mail …» 한 줄(아이디와 개수만)이다. 사람이 먼저 입력하면 대기 프로세스는 끝난다. 데몬이 없거나,
  스레드가 데몬에 없거나, `codex exec` 면 아무 일도 없고 «메일 대기» 표시가 대신한다.
  `[mcp_servers.mailbox]` 에 `default_tools_approval_mode = "approve"` 를 둔다(`ext-hooks/codex-config-example.toml`).
  메일박스 도구만 자동 승인되고 셸과 다른 승인은 그대로다. 고친 뒤 세션을 다시 시작한다.
  쓰는 메서드(`thread/loaded/list`, `thread/resume`, `turn/start`)는 문서화된 app-server 메서드이고 실험 표시가 없어서
  실험 API 권한 없이 호출한다. ⚠다만 데몬 소켓 경로는 문서에 없는 구현 세부이고 WebSocket 전송은 실험 기능이다(기본은
  stdio). 그래서 Codex 업데이트로 깨질 수 있다 — 그때는 조용히 끝나고 «메일 대기» 표시가 대신한다.
  ★0.163.0, 2026-10-21: 17초 만에 턴 실행, 훅 전부 실행, TUI 에 표시; ★0.164.0, 2026-10-24: 실험 플래그 없이도 같은
  호출이 동작.
  ⚠macOS/Linux 만. Windows 에서는 아무것도 띄우지 않는다.
- 막고 기다리기(`--wait`, timeout 3600)는 사람 없이 도는 세션 전용이다. 입력이 메일·시간 초과·Esc 까지 대기열에 쌓인다.
- 훅이 없어도(승인 전) 최근 10분 안에 rollout 이 바뀐 Codex 세션은 «훅 미연결» 표시가 붙은 행으로 나온다. 폴더와
  모델만 보이고 상태는 알 수 없다. 훅 이벤트가 들어오면 훅 행으로 바뀐다.
- Cursor CLI 와 Copilot CLI 도 자기 폴더에서 같은 «훅 미연결» 행을 얻는다. Cursor 는 `~/.cursor/chats/*/<id>/` 파일이
  최근 10분 안에 바뀐 대화, Copilot 은 `~/.copilot/session-state/<id>/inuse.<pid>.lock` 의 프로세스가 살아 있는 세션.
  폴더, 시작, 마지막 활동만 보인다. 훅 행이 이긴다(같은 아이디, 또는 같은 폴더의 그 CLI 훅 행).
- 선택 `SessionStart` 안내: `<PYTHON> <MAILBOX_CODE_DIR>/hooks/invite_notice.py --platform codex`(timeout 10) 와
  `<PYTHON> <MAILBOX_CODE_DIR>/hooks/pipelines_brief.py --platform codex`(timeout 5). Codex 문구는 새 메일이 턴 끝에
  `Stop` 훅으로 온다(아이디 `codex:<cwd>` 키 또는 `<폴더>-codex`)는 것과, 단계를 세션이 직접 순서대로 돌리며
  `echo "[pl:<name>/<stage>]"` / `[pl-end:...]` 셸 표시를 남긴다는 것이다. ⚠플래그가 없으면 Claude 문구(`mailbox_wake`,
  Agent 도구)가 나간다. 플래그만 보고, 페이로드로 추측하지 않는다. 0.163 에서는 `SessionStart` 가 첫 턴과 함께 실행된다.
- `sidereus/plat_codex.py` 가 `$CODEX_HOME/sessions/**/rollout-*.jsonl` 과 `archived_sessions/` 에서 토큰, 모델, 비용, 사용
  한도를 읽는다. 메시지 내용은 읽지 않는다.
  ⚠`input_tokens` 에는 캐시가 들어 있어 따로 뺀다. 요청은 누적값이 아니라 `last_token_usage` 로 더한다.
  ⚠`.jsonl.zst` 는 건너뛴다. ⚠비용은 API 정가로 낸 추정치다. ⚠한도 비율은 `rate_limits` 가 있어야 보이는데 자주
  null 이다(#14880).
- Codex 토큰과 비용은 Claude 합계에 넣지 않는다.

그 밖의 플랫폼: `ext-hooks/generic-hooks-example.json` 의 `<PLATFORM>` 을 바꿔 그 CLI 가 훅을 읽는 곳에 둔다(CLI 마다
확인하지는 않았다).
