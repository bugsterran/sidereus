// Korean for the pipeline tab «Harness» view (47b-harness.js).
Object.assign(I18N.ko, {
  'Tool runs': '도구 실행', 'no hooks': '훅 없음', 'No rule files': '규칙 파일이 없습니다',
  'No agents': '에이전트가 없습니다', 'not in a pipeline': '파이프라인에 없음', 'Show in the tools list': '도구 목록에서 보기',
  'Could not read the harness': '하네스를 읽지 못했습니다', 'Counting runs…': '실행 횟수 집계 중…', 'Hook flow': '훅 흐름',
  'Rule files': '규칙 파일', 'load order': '읽는 순서', 'Agents ↔ pipelines': '에이전트 ↔ 파이프라인', 'Harness map': '하네스 지도',
  'Estimate — guessed from the hook event and its config': '추정 — 훅 종류와 설정으로 어림한 값',
  'adds a note to the conversation context': '대화 맥락에 안내문을 끼워 넣음', 'stops the tool call when its condition matches': '조건이 맞으면 도구 실행을 막음',
  'writes a file or updates state only': '파일에 기록하거나 상태만 갱신', 'not read, so the effect is unknown': '내용을 읽지 않아 효과를 모름',
  'Hooks run left to right: session start → prompt submit → before the tool → tool run → after the tool → response end': '왼쪽부터 세션 시작 → 요청 입력 → 도구 실행 전 → 도구 실행 → 실행 후 → 응답 종료 순서로 훅이 돈다',
  'No file to open.': '열 수 있는 파일이 없습니다.', 'The file is too large.': '파일이 너무 큽니다.', 'Not a text file.': '텍스트 파일이 아닙니다.',
  'Check': '점검 결과', 'Go to the next one': '다음 항목으로 이동',
  'Results': '결과', 'Config map': '구성 지도', 'uncommitted changes': '변경 있음',
  'No records yet — running scripts/check.sh adds them': '아직 기록이 없습니다 — scripts/check.sh 를 실행하면 쌓입니다',
  'unchanged': '그대로',
  'No FAIL→PASS transition yet': 'FAIL→PASS 전환 기록이 없습니다', 'No PASS records yet': 'PASS 기록이 없습니다',
  'A check that went from FAIL to PASS. Shows the commits in between and the steps that flipped FAIL→PASS.': '같은 점검이 FAIL 뒤 PASS 로 바뀐 기록. 사이 커밋 수와 FAIL→PASS 로 바뀐 단계를 보여 줍니다.',
  'Whether the latest PASS stayed green. Regressed = same step FAIL again · Re-fixed = PASS again after a regression · Reverted = that commit was reverted · Dropped = not in the current branch history · Unverified = PASS taken with uncommitted changes.': '최근 PASS 가 이후에도 유지됐는지. Regressed = 같은 단계가 다시 FAIL · Re-fixed = 회귀 뒤 다시 PASS · Reverted = 그 커밋이 리버트됨 · Dropped = 현재 브랜치 이력에 없음 · Unverified = 미커밋 변경 상태의 PASS.',
  '{n} files': '파일 {n}개', '{n} file': '파일 {n}개',
  // ⚠Unused since the gate report; kept only because tests/fixtures/i18n_legacy_en.json pins them (test_i18n_flip).
  'n/a': '해당 없음', 'Details': '상세', '{n} declared skip(s)': '건너뜀 선언 {n}', '{n} loop-back(s)': '되돌림 {n}', 'Blocked {n}': '차단 {n}',
  'File not found.': '파일이 없습니다.', 'Unknown project': '알 수 없는 프로젝트', 'Invalid period': '잘못된 기간', 'Invalid file reference': '잘못된 파일 참조', 'Unknown platform': '알 수 없는 플랫폼', 'Platform': '플랫폼', 'Runs without output are not recorded, so the count is unknown': '출력 없는 실행은 기록되지 않아 횟수를 알 수 없음', 'Counts only runs that printed output': '출력을 남긴 실행만 집계',
  "Created room '{name}' (waiting for invites).": "'{name}' 방을 만들었습니다 (초대 대기).",
  "Created '{room}' and invited {n}": "'{room}' 방을 만들고 {n}건 초대", "Invited {n} to '{room}'": "'{room}' {n}건 초대",
  "Created '{room}' and invited {n} · {m} already there": "'{room}' 방을 만들고 {n}건 초대 · {m}건은 이미 있음",
  "Invited {n} to '{room}' · {m} already there": "'{room}' {n}건 초대 · {m}건은 이미 있음",
  'Quota lookup is turned off in settings (quota_lookup)': '할당량 조회를 설정에서 껐습니다(quota_lookup)',
  'Could not read the token from the keychain (access may need to be allowed)': '키체인에서 토큰을 못 읽었습니다(권한 허용이 필요할 수 있습니다)',
  'No Claude Code login found': 'Claude Code 로그인 정보를 찾지 못했습니다',
  'Could not reach the usage API': '사용량 API 에 연결하지 못했습니다',
});
// Room admin server errors (sidereus/room_admin.py, sidereus/routes_post.py) — raw `error`/`msg` go through T().
Object.assign(I18N.ko, {
  'A room name is required.': '방 이름이 필요합니다.', "'dm' cannot be used as a room name.": 'dm 은 방 이름으로 쓸 수 없습니다.',
  'Room names cannot contain control characters.': '방 이름에 제어 문자를 쓸 수 없습니다.',
  'A list of rooms is required.': '방 목록이 필요합니다.', 'This room cannot be hidden.': '숨길 수 없는 방입니다.',
  'This room already exists.': '이미 있는 방입니다.', 'Bad request.': '잘못된 요청입니다.',
  'The room changed since the preview — check again.': '미리보기 이후 방 정보가 바뀌었습니다 — 다시 확인하세요.',
});
// Room tag server errors (sidereus/room_tags.py).
Object.assign(I18N.ko, {
  'A tag list is required.': '태그 목록이 필요합니다.', 'Tags must be strings.': '태그는 문자열이어야 합니다.',
  'Tags cannot contain # or control characters.': '태그에 # 나 제어 문자를 쓸 수 없습니다.', 'No such room.': '없는 방입니다.',
});
// Pipeline tab hint for a run launched outside its project (48b plOrphHtml).
Object.assign(I18N.ko, {
  'Pipeline running from another folder': '다른 폴더에서 실행 중인 파이프라인', 'pipeline file not found': '파이프라인 파일을 찾지 못했습니다', 'Use «Add project» on the folder that holds its pipeline file to see its stages.': '단계를 보려면 «프로젝트 불러오기»로 이 파이프라인 파일이 있는 폴더를 추가하세요.',
});
// Korean for the diff window scope labels (sidereus/git_view.py DIFF_SCOPES).
Object.assign(I18N.ko, {
  'Unpushed + working tree': '미푸시 + 작업트리', 'Committed (unpushed)': '커밋됨(미푸시)', 'Working tree (uncommitted)': '작업트리(미커밋)',
});
// Korean for the timeline pipeline strip (74c-timeline-plrun.js).
Object.assign(I18N.ko, {
  'Finished run': '끝난 실행', 'Click to open it in the pipeline view': '누르면 파이프라인 화면에서 엽니다',
  'Other pipelines running in the same session': '같은 세션에서 진행 중인 다른 파이프라인',
  '+{n} finished runs': '+{n} 끝난 실행',   // ended-runs chip; «Collapse» reuses the shared entry
});
